"""持久化清理建议、审批及幂等执行。所有删除必须经过此服务。"""
import hashlib
import json
from datetime import datetime

from sqlalchemy.exc import IntegrityError
from config import settings
from models import CleanupCandidate, OAFileInfo, KnowledgeBase, ProcessingStatus, ProcessingLog
from services.dify_service import dify_service, multi_kb_manager


class CleanupService:
    def service_for_file(self, file_info, db):
        if not file_info.dify_dataset_id:
            raise ValueError("旧文档缺少入库数据集绑定，请先运行 backfill_bindings.py")
        kb = db.query(KnowledgeBase).filter(
            KnowledgeBase.dify_dataset_id == file_info.dify_dataset_id
        ).first()
        if kb:
            return multi_kb_manager.get_service_for_knowledge_base(kb)
        if file_info.dify_dataset_id == settings.dify_dataset_id:
            return dify_service
        raise ValueError("找不到文档入库时的数据集配置，停止清理")

    def propose(self, db, file_info, kind, evidence, replacement=None):
        if not file_info.document_id or not file_info.dify_dataset_id:
            raise ValueError("清理候选必须有确定的文档ID和入库数据集")
        if replacement and (
            replacement.imagefileid == file_info.imagefileid
            or replacement.document_id == file_info.document_id
            or replacement.dify_dataset_id != file_info.dify_dataset_id
            or replacement.business_category != file_info.business_category
        ):
            raise ValueError("替代文档必须是同数据集、同业务分类的另一文档")
        key = hashlib.sha256(json.dumps([
            file_info.imagefileid, file_info.document_id, file_info.dify_dataset_id, kind,
            replacement.document_id if replacement else None,
            file_info.content_sha256,
            replacement.content_sha256 if replacement else None,
        ], ensure_ascii=False).encode()).hexdigest()
        candidate = db.query(CleanupCandidate).filter_by(unique_key=key).first()
        if candidate:
            return candidate
        candidate = CleanupCandidate(
            unique_key=key, file_id=file_info.imagefileid,
            document_id=file_info.document_id, dataset_id=file_info.dify_dataset_id,
            replacement_file_id=replacement.imagefileid if replacement else None,
            replacement_document_id=replacement.document_id if replacement else None,
            kind=kind, evidence=json.dumps({
                **evidence, "target_content_sha256": file_info.content_sha256,
                "replacement_content_sha256": replacement.content_sha256 if replacement else None,
            }, ensure_ascii=False), status="pending",
        )
        try:
            with db.begin_nested():
                db.add(candidate)
                db.flush()
        except IntegrityError:
            return db.query(CleanupCandidate).filter_by(unique_key=key).one()
        return candidate

    def execute(self, db, candidate_id):
        candidate = db.query(CleanupCandidate).filter_by(id=candidate_id).with_for_update().one()
        if candidate.status == "deleted":
            return {"success": True, "already_deleted": True}
        if candidate.status not in ("approved", "failed") or not candidate.reviewed_at:
            return {"success": False, "error": "清理建议尚未批准"}
        file_info = db.query(OAFileInfo).filter_by(imagefileid=candidate.file_id).with_for_update().first()
        if not file_info or (
            file_info.document_id != candidate.document_id
            or file_info.dify_dataset_id != candidate.dataset_id
            or file_info.processing_status != ProcessingStatus.COMPLETED
        ):
            candidate.status = "stale"
            candidate.last_error = "文档已变化或已被其他清理任务删除"
            db.commit()
            return {"success": False, "error": candidate.last_error}
        candidate.attempts += 1
        try:
            evidence = json.loads(candidate.evidence)
            target_hash = evidence.get("target_content_sha256")
            if target_hash and (file_info.content_sha256 != target_hash
                or not file_info.parsed_content
                or hashlib.sha256(file_info.parsed_content.encode()).hexdigest() != target_hash):
                raise ValueError("待删除文档内容已变化，请重新扫描")
            if candidate.kind == "expiration":
                from services.version_manager import version_manager
                expiry = version_manager.parse_date(evidence.get("expiration_date"))
                if not expiry or expiry >= version_manager.today():
                    raise ValueError("失效日期无效或尚未过期")
            service = self.service_for_file(file_info, db)
            if candidate.replacement_file_id:
                replacement = db.query(OAFileInfo).filter_by(
                    imagefileid=candidate.replacement_file_id
                ).with_for_update().first()
                if not replacement or (
                    replacement.document_id != candidate.replacement_document_id
                    or replacement.dify_dataset_id != candidate.dataset_id
                    or replacement.processing_status != ProcessingStatus.COMPLETED
                    or replacement.business_category != file_info.business_category
                ):
                    raise ValueError("替代文档已变化或不在相同知识库和业务分类")
                replacement_hash = evidence.get("replacement_content_sha256")
                if replacement_hash and (replacement.content_sha256 != replacement_hash
                    or not replacement.parsed_content
                    or hashlib.sha256(replacement.parsed_content.encode()).hexdigest() != replacement_hash):
                    raise ValueError("替代文档内容已变化，请重新扫描")
                if candidate.kind == "duplicate" and (
                    not file_info.content_sha256
                    or file_info.content_sha256 != replacement.content_sha256
                    or file_info.content_sha256 != evidence.get("content_sha256")
                ):
                    raise ValueError("文档内容已变化，不能按完全重复删除")
                # 不能将上传成功等同于索引可用；失败、禁用、归档时保留旧文档。
                state = service.get_document_detail(replacement.document_id)
                if not state.get("success"):
                    raise ValueError("无法确认替代文档的 Dify 索引状态")
                detail = state["document"]
                if (detail.get("id") != replacement.document_id
                    or detail.get("indexing_status") != "completed"
                    or detail.get("enabled") is not True
                    or detail.get("archived") is not False):
                    raise ValueError("替代文档尚未完成索引、已停用或已归档")
            result = service.delete_document_from_knowledge_base(candidate.document_id)
            if not result.get("success"):
                raise RuntimeError(result.get("error", "Dify 删除失败"))
            file_info.document_id = None
            file_info.processing_status = ProcessingStatus.SKIPPED
            file_info.should_add_to_kb = False
            file_info.processing_message = f"清理已执行 [{candidate.kind}]，审计编号 {candidate.id}"
            candidate.status = "deleted"
            candidate.executed_at = datetime.now()
            candidate.last_error = None
            db.add(ProcessingLog(file_id=file_info.imagefileid, step="cleanup", status="success",
                                 message=f"候选 {candidate.id}: {candidate.evidence}"))
            db.commit()
            return {"success": True, "candidate_id": candidate.id}
        except Exception as exc:
            # 远端调用失败时保留本地文档ID，下次可以重试。
            db.rollback()
            candidate = db.query(CleanupCandidate).filter_by(id=candidate_id).with_for_update().one()
            if candidate.status == "deleted":
                return {"success": True, "already_deleted": True}
            candidate.status = "failed"
            candidate.attempts += 1
            candidate.last_error = str(exc)
            db.commit()
            return {"success": False, "error": str(exc)}


cleanup_service = CleanupService()
