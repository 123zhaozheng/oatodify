"""Configuration and knowledge-base APIs for the Chinese operations console."""
from __future__ import annotations

from urllib.parse import urlsplit, urlunsplit

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from database import get_db
from models import (
    BusinessCategory,
    DocumentCategoryMapping,
    KnowledgeBase,
    KnowledgeBaseStatus,
    OAFileInfo,
)
from services.runtime_config import (
    RuntimeConfigError,
    VersionConflict,
    bump_runtime_revision,
    get_runtime_config,
    patch_runtime_config,
    refresh_runtime_settings,
)

router = APIRouter()


async def _json_object(request: Request):
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=422, detail="请求体必须是 JSON 对象") from None
    if not isinstance(body, dict):
        raise HTTPException(status_code=422, detail="请求体必须是 JSON 对象")
    return body


def _validate_keys(body, allowed, *, required=()):
    if set(body) - set(allowed) or set(required) - set(body):
        raise HTTPException(status_code=422, detail="请求字段无效")


@router.get("/console/config", summary="获取运行配置")
async def get_console_config():
    refresh_runtime_settings()
    try:
        return get_runtime_config()
    except RuntimeConfigError:
        raise HTTPException(status_code=500, detail="读取配置失败") from None


@router.patch("/console/config", summary="保存运行配置")
async def patch_console_config(request: Request):
    body = await _json_object(request)
    _validate_keys(body, {"version", "values", "clear_secrets", "operator"}, required={"version", "values"})
    if type(body["version"]) is not int or body["version"] < 0:
        raise HTTPException(status_code=422, detail="配置版本无效")
    if not isinstance(body["values"], dict):
        raise HTTPException(status_code=422, detail="values 必须是对象")
    if "operator" in body and (not isinstance(body["operator"], str) or len(body["operator"]) > 200):
        raise HTTPException(status_code=422, detail="operator 无效")
    try:
        updated = patch_runtime_config(body["version"], body["values"], body.get("clear_secrets", []))
    except VersionConflict:
        raise HTTPException(status_code=409, detail="配置已被其他操作更新，请刷新后重试") from None
    except ValueError:
        raise HTTPException(status_code=422, detail="配置字段或类型无效") from None
    except RuntimeConfigError:
        raise HTTPException(status_code=500, detail="配置保存失败") from None

    refresh_runtime_settings()
    restart_keys = set(get_runtime_config()["restart_required"])
    submitted_keys = set(body["values"]) | set(body.get("clear_secrets", []))
    hot_applied = sorted(
        key for key in submitted_keys
        if key not in restart_keys and not (key in body["values"] and body["values"][key] in ("", None)
                                             and key in get_runtime_config()["secrets"])
    )
    return {
        "success": True,
        "version": updated["version"],
        "message": "配置已保存；即时配置将用于后续请求和任务。",
        "hot_applied": hot_applied,
        "restart_required": sorted(restart_keys),
    }


def _safe_base_url(value):
    if not value:
        return value
    if not _valid_http_url(value):
        return ""
    try:
        parsed = urlsplit(value)
        # Avoid returning embedded user/password, query tokens, or fragments.
        host = parsed.netloc.rsplit("@", 1)[-1]
        return urlunsplit((parsed.scheme, host, parsed.path, "", ""))
    except (ValueError, TypeError):
        return ""


def _valid_http_url(value):
    if not isinstance(value, str) or not value or value != value.strip() or any(char.isspace() for char in value):
        return False
    try:
        parsed = urlsplit(value)
        _ = parsed.port
        return parsed.scheme.lower() in {"http", "https"} and bool(parsed.hostname)
    except (ValueError, TypeError):
        return False


def _knowledge_base_dict(row):
    return {
        "id": row.id,
        "name": row.name,
        "description": row.description,
        "dify_dataset_id": row.dify_dataset_id,
        "base_url": _safe_base_url(row.base_url),
        "status": row.status.value if hasattr(row.status, "value") else row.status,
        "api_key_configured": bool(row.api_key),
    }


def _validate_knowledge_base_patch(data, *, creating):
    allowed = {"name", "description", "dify_dataset_id", "base_url", "status", "api_key", "clear_api_key"}
    _validate_keys(data, allowed, required={"name", "dify_dataset_id"} if creating else ())
    if "name" in data and (not isinstance(data["name"], str) or not data["name"].strip() or len(data["name"]) > 200):
        raise HTTPException(status_code=422, detail="知识库名称无效")
    if "description" in data and data["description"] is not None and not isinstance(data["description"], str):
        raise HTTPException(status_code=422, detail="知识库描述无效")
    if "dify_dataset_id" in data and (not isinstance(data["dify_dataset_id"], str)
                                      or not data["dify_dataset_id"].strip()
                                      or len(data["dify_dataset_id"]) > 100):
        raise HTTPException(status_code=422, detail="数据集 ID 无效")
    if "base_url" in data and data["base_url"] is not None and (not _valid_http_url(data["base_url"]) or len(data["base_url"]) > 500):
        raise HTTPException(status_code=422, detail="Dify 地址必须是带主机名的 HTTP/HTTPS 地址")
    if "status" in data and data["status"] not in {status.value for status in KnowledgeBaseStatus}:
        raise HTTPException(status_code=422, detail="知识库状态无效")
    if "api_key" in data and (not isinstance(data["api_key"], str) or len(data["api_key"]) > 500):
        raise HTTPException(status_code=422, detail="API Key 无效")
    if "clear_api_key" in data and type(data["clear_api_key"]) is not bool:
        raise HTTPException(status_code=422, detail="密钥清除标记无效")
    if data.get("clear_api_key") and data.get("api_key") not in (None, ""):
        raise HTTPException(status_code=422, detail="不能同时设置并清除 API Key")


def _after_database_config_change():
    try:
        bump_runtime_revision()
        refresh_runtime_settings()
    except RuntimeConfigError:
        raise HTTPException(status_code=503, detail="配置已写入数据库，但共享缓存版本更新失败") from None


@router.get("/console/knowledge-bases", summary="获取知识库配置")
async def list_knowledge_bases(db: Session = Depends(get_db)):
    rows = db.query(KnowledgeBase).order_by(KnowledgeBase.id).all()
    return {"items": [_knowledge_base_dict(row) for row in rows]}


@router.post("/console/knowledge-bases", summary="新增知识库配置")
async def create_knowledge_base(request: Request, db: Session = Depends(get_db)):
    data = await _json_object(request)
    _validate_knowledge_base_patch(data, creating=True)
    row = KnowledgeBase(
        name=data["name"].strip(),
        description=data.get("description"),
        dify_dataset_id=data["dify_dataset_id"].strip(),
        base_url=data.get("base_url"),
        status=KnowledgeBaseStatus(data.get("status", KnowledgeBaseStatus.ACTIVE.value)),
        api_key=data.get("api_key") or None,
    )
    db.add(row)
    try:
        db.commit()
        db.refresh(row)
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="数据集 ID 已存在") from None
    except Exception:
        db.rollback()
        raise HTTPException(status_code=500, detail="知识库保存失败") from None
    _after_database_config_change()
    return _knowledge_base_dict(row)


@router.patch("/console/knowledge-bases/{knowledge_base_id}", summary="修改知识库配置")
async def patch_knowledge_base(knowledge_base_id: int, request: Request, db: Session = Depends(get_db)):
    data = await _json_object(request)
    _validate_knowledge_base_patch(data, creating=False)
    row = db.query(KnowledgeBase).filter(KnowledgeBase.id == knowledge_base_id).first()
    if row is None:
        raise HTTPException(status_code=404, detail="知识库不存在")

    if "dify_dataset_id" in data and data["dify_dataset_id"] != row.dify_dataset_id:
        linked_document = db.query(OAFileInfo.id).filter(
            OAFileInfo.document_id.isnot(None),
            or_(OAFileInfo.knowledge_base_id == row.id,
                OAFileInfo.dify_dataset_id == row.dify_dataset_id),
        ).first()
        if linked_document:
            raise HTTPException(status_code=409, detail="已有入库文档绑定此数据集，不能更改数据集身份")

    for key in ("name", "description", "dify_dataset_id", "status"):
        if key in data:
            value = data[key]
            if key == "name":
                value = value.strip()
            elif key == "dify_dataset_id":
                value = value.strip()
            elif key == "status":
                value = KnowledgeBaseStatus(value)
            setattr(row, key, value)
    if "base_url" in data:
        proposed = data["base_url"]
        # A UI that sends the sanitized URL back unchanged must not erase hidden
        # credentials embedded in the stored URI.
        if proposed != _safe_base_url(row.base_url):
            row.base_url = proposed or None
    if data.get("clear_api_key"):
        row.api_key = None
    elif data.get("api_key"):
        row.api_key = data["api_key"]
    try:
        db.commit()
        db.refresh(row)
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="数据集 ID 已存在") from None
    except Exception:
        db.rollback()
        raise HTTPException(status_code=500, detail="知识库保存失败") from None
    _after_database_config_change()
    return _knowledge_base_dict(row)


def _category_mapping_dict(row):
    return {
        "business_category": row.business_category.value,
        "knowledge_base_id": row.knowledge_base_id,
        "min_confidence_score": row.min_confidence_score,
        "auto_approve_threshold": row.auto_approve_threshold,
        "ai_prompt_template": row.ai_prompt_template,
        "is_active": row.is_active,
    }


@router.get("/console/category-mappings", summary="获取分类映射")
async def list_category_mappings(db: Session = Depends(get_db)):
    rows = db.query(DocumentCategoryMapping).order_by(DocumentCategoryMapping.business_category).all()
    return {"items": [_category_mapping_dict(row) for row in rows]}


@router.put("/console/category-mappings", summary="保存分类映射")
async def replace_category_mappings(request: Request, db: Session = Depends(get_db)):
    body = await _json_object(request)
    _validate_keys(body, {"items"}, required={"items"})
    items = body["items"]
    if not isinstance(items, list):
        raise HTTPException(status_code=422, detail="items 必须是数组")
    known_categories = {item.value for item in BusinessCategory}
    seen_categories = set()
    valid_items = []
    for item in items:
        if not isinstance(item, dict):
            raise HTTPException(status_code=422, detail="分类映射项无效")
        allowed = {"business_category", "knowledge_base_id", "min_confidence_score",
                   "auto_approve_threshold", "ai_prompt_template", "is_active"}
        required = allowed
        _validate_keys(item, allowed, required=required)
        category = item["business_category"]
        if not isinstance(category, str) or category not in known_categories or category in seen_categories:
            raise HTTPException(status_code=422, detail="业务分类无效或重复")
        seen_categories.add(category)
        kb_id = item["knowledge_base_id"]
        if type(kb_id) is not int or kb_id <= 0:
            raise HTTPException(status_code=422, detail="知识库 ID 无效")
        for key in ("min_confidence_score", "auto_approve_threshold"):
            value = item[key]
            if type(value) is not int or value < 0 or value > 100:
                raise HTTPException(status_code=422, detail="置信度阈值必须是 0 到 100 的整数")
        if item["auto_approve_threshold"] < item["min_confidence_score"]:
            raise HTTPException(status_code=422, detail="自动审核阈值不能低于最低置信度")
        if item["ai_prompt_template"] is not None and not isinstance(item["ai_prompt_template"], str):
            raise HTTPException(status_code=422, detail="提示词模板无效")
        if type(item["is_active"]) is not bool:
            raise HTTPException(status_code=422, detail="启用状态必须是布尔值")
        valid_items.append({
            "business_category": BusinessCategory(category),
            "knowledge_base_id": kb_id,
            "min_confidence_score": item["min_confidence_score"],
            "auto_approve_threshold": item["auto_approve_threshold"],
            "ai_prompt_template": item["ai_prompt_template"],
            "is_active": item["is_active"],
        })

    kb_ids = {item["knowledge_base_id"] for item in valid_items}
    existing_ids = {row[0] for row in db.query(KnowledgeBase.id).filter(KnowledgeBase.id.in_(kb_ids)).all()} if kb_ids else set()
    if existing_ids != kb_ids:
        raise HTTPException(status_code=422, detail="映射引用了不存在的知识库")
    try:
        retained_categories = [item["business_category"] for item in valid_items]
        if retained_categories:
            db.query(DocumentCategoryMapping).filter(
                DocumentCategoryMapping.business_category.notin_(retained_categories)
            ).delete(synchronize_session=False)
        else:
            db.query(DocumentCategoryMapping).delete(synchronize_session=False)
        for item in valid_items:
            row = db.query(DocumentCategoryMapping).filter_by(
                business_category=item["business_category"]
            ).order_by(DocumentCategoryMapping.id).first()
            if row is None:
                db.add(DocumentCategoryMapping(**item))
            else:
                # 页面未编辑的输出 schema、处理优先级和创建记录必须保留。
                for key, value in item.items():
                    setattr(row, key, value)
        db.commit()
    except Exception:
        db.rollback()
        raise HTTPException(status_code=500, detail="分类映射保存失败") from None
    _after_database_config_change()
    rows = db.query(DocumentCategoryMapping).order_by(DocumentCategoryMapping.business_category).all()
    return {"items": [_category_mapping_dict(row) for row in rows]}
