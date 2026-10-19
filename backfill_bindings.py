"""旧文档绑定回填：只在 Dify 确认该文档属于所选数据集后写入。"""
import argparse
from database import init_db, get_db_session
from models import OAFileInfo, ProcessingStatus, KnowledgeBase
from services.dify_service import dify_service, multi_kb_manager
from services.ai_analyzer import ai_analyzer


def backfill(db, dataset_id=None, limit=2000):
    stats = dict(bound=0, unresolved=0)
    files = db.query(OAFileInfo).filter(
        OAFileInfo.document_id.isnot(None), OAFileInfo.dify_dataset_id.is_(None),
        OAFileInfo.processing_status == ProcessingStatus.COMPLETED,
    ).order_by(OAFileInfo.id).limit(limit).all()
    for file_info in files:
        if dataset_id:
            kb = db.query(KnowledgeBase).filter_by(dify_dataset_id=dataset_id).first()
        else:
            kb = ai_analyzer.get_target_knowledge_base(file_info.business_category, db)
        service = multi_kb_manager.get_service_for_knowledge_base(kb) if kb else dify_service
        if dataset_id and service.dataset_id != dataset_id:
            stats['unresolved'] += 1
            continue
        result = service.get_document_detail(file_info.document_id)
        if result.get('success') and result['document'].get('id') == file_info.document_id:
            file_info.dify_dataset_id = service.dataset_id
            file_info.knowledge_base_id = kb.id if kb else None
            db.commit()
            stats['bound'] += 1
        else:
            stats['unresolved'] += 1
    return stats


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dataset-id', help='可选：明确指定旧数据集，必须存在对应知识库配置')
    parser.add_argument('--limit', type=int, default=2000)
    args = parser.parse_args()
    init_db()
    db = get_db_session()
    try:
        print(backfill(db, args.dataset_id, args.limit))
    finally:
        db.close()
