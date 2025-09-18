import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from botocore.exceptions import BotoCoreError, ClientError
from redis import Redis
from redis.exceptions import RedisError
from sqlalchemy import func, text
from sqlalchemy.exc import SQLAlchemyError

from config import settings
from database import SessionLocal, engine
from models import OAFileInfo, ProcessingLog, ProcessingStatus
from services.dify_service import dify_service
from services.s3_service import s3_service

logger = logging.getLogger(__name__)


def _normalize_exception(exc: Exception) -> str:
    return str(exc)


def check_database_connection() -> Dict[str, Any]:
    """Run a lightweight database connectivity check."""
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        return {"connected": True}
    except SQLAlchemyError as exc:
        logger.warning("Database connection check failed: %s", exc)
        return {"connected": False, "error": _normalize_exception(exc)}


def check_redis_connection() -> Dict[str, Any]:
    """Ping Redis and return basic metrics."""
    client: Optional[Redis] = None
    try:
        client = Redis.from_url(
            settings.redis_url,
            socket_connect_timeout=3,
            socket_timeout=3,
            decode_responses=True,
        )
        client.ping()
        server_info = client.info(section="server")
        memory_info = client.info(section="memory")
        return {
            "connected": True,
            "version": server_info.get("redis_version"),
            "uptime": server_info.get("uptime_in_seconds"),
            "used_memory_human": memory_info.get("used_memory_human"),
        }
    except RedisError as exc:
        logger.warning("Redis connection check failed: %s", exc)
        return {"connected": False, "error": _normalize_exception(exc)}
    finally:
        if client:
            try:
                client.close()
            except Exception:
                pass


def _ensure_s3_client() -> None:
    if s3_service.client is None:
        try:
            s3_service._init_client()
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("Failed to initialise S3 client: %s", exc)


def check_s3_connection() -> Dict[str, Any]:
    """Verify S3 connectivity by running head_bucket."""
    _ensure_s3_client()
    if not s3_service.client:
        return {"connected": False, "error": "S3客户端未初始化"}
    try:
        s3_service.client.head_bucket(Bucket=settings.s3_bucket_name)
        return {
            "connected": True,
            "bucket": settings.s3_bucket_name,
            "region": settings.s3_region,
        }
    except ClientError as exc:
        error = exc.response.get("Error", {})
        message = f"{error.get('Code')}: {error.get('Message')}" if error else str(exc)
        return {"connected": False, "error": message}
    except BotoCoreError as exc:
        return {"connected": False, "error": _normalize_exception(exc)}


def run_s3_diagnostics(max_keys: int = 5) -> Dict[str, Any]:
    """Fetch a small sample to confirm object level access."""
    _ensure_s3_client()
    if not s3_service.client:
        return {"success": False, "error": "S3客户端未初始化"}
    try:
        response = s3_service.client.list_objects_v2(
            Bucket=settings.s3_bucket_name,
            MaxKeys=max_keys,
        )
        keys = [obj.get("Key") for obj in response.get("Contents", [])]
        inspected = None
        if keys:
            head = s3_service.client.head_object(
                Bucket=settings.s3_bucket_name,
                Key=keys[0],
            )
            inspected = {
                "key": keys[0],
                "size": head.get("ContentLength"),
                "last_modified": head.get("LastModified").isoformat()
                if head.get("LastModified")
                else None,
            }
        return {
            "success": True,
            "bucket": settings.s3_bucket_name,
            "object_keys": keys,
            "inspected_object": inspected,
        }
    except ClientError as exc:
        error = exc.response.get("Error", {})
        message = f"{error.get('Code')}: {error.get('Message')}" if error else str(exc)
        return {"success": False, "error": message}
    except BotoCoreError as exc:
        return {"success": False, "error": _normalize_exception(exc)}


def get_s3_storage_stats(sample_size: int = 1000) -> Dict[str, Any]:
    """Aggregate object counts and size for a sample window."""
    _ensure_s3_client()
    if not s3_service.client:
        return {"success": False, "error": "S3客户端未初始化"}
    total_size = 0
    total_objects = 0
    scanned = 0
    continuation: Optional[str] = None
    last_response: Optional[Dict[str, Any]] = None
    try:
        while scanned < sample_size:
            params: Dict[str, Any] = {
                "Bucket": settings.s3_bucket_name,
                "MaxKeys": min(1000, sample_size - scanned),
            }
            if continuation:
                params["ContinuationToken"] = continuation
            response = s3_service.client.list_objects_v2(**params)
            last_response = response
            contents = response.get("Contents", [])
            batch_count = len(contents)
            total_objects += batch_count
            scanned += batch_count
            total_size += sum(obj.get("Size", 0) for obj in contents)
            if not response.get("IsTruncated"):
                break
            continuation = response.get("NextContinuationToken")
        return {
            "success": True,
            "bucket": settings.s3_bucket_name,
            "object_count_sample": total_objects,
            "total_size_bytes_sample": total_size,
            "sample_complete": bool(last_response and not last_response.get("IsTruncated")),
            "scanned_objects": scanned,
            "has_more": bool(last_response and last_response.get("IsTruncated")),
        }
    except ClientError as exc:
        error = exc.response.get("Error", {})
        message = f"{error.get('Code')}: {error.get('Message')}" if error else str(exc)
        return {"success": False, "error": message}
    except BotoCoreError as exc:
        return {"success": False, "error": _normalize_exception(exc)}


def check_celery_health(timeout: int = 2) -> Dict[str, Any]:
    """Inspect Celery workers using control API."""
    try:
        from tasks.document_processor import app as celery_app

        inspect = celery_app.control.inspect(timeout=timeout)
        if not inspect:
            return {"connected": False, "error": "无法连接到Celery"}

        stats = inspect.stats() or {}
        active = inspect.active() or {}
        reserved = inspect.reserved() or {}
        scheduled = inspect.scheduled() or {}

        workers = list(stats.keys())
        if not workers:
            return {"connected": False, "error": "未检测到Celery工作进程"}

        def _total(tasks_map: Dict[str, List[Any]]) -> int:
            return sum(len(items) for items in tasks_map.values()) if tasks_map else 0

        return {
            "connected": True,
            "workers": workers,
            "active_tasks": _total(active),
            "reserved_tasks": _total(reserved),
            "scheduled_tasks": _total(scheduled),
        }
    except Exception as exc:
        logger.warning("Celery health check failed: %s", exc)
        return {"connected": False, "error": _normalize_exception(exc)}


def get_queue_statistics() -> Dict[str, int]:
    """Summarise pipeline status from OAFileInfo."""
    session = SessionLocal()
    try:
        rows = session.query(
            OAFileInfo.processing_status,
            func.count(OAFileInfo.id),
        ).group_by(OAFileInfo.processing_status).all()
        counts = {status.value if status else "unknown": count for status, count in rows}
        in_progress = sum(
            counts.get(state.value, 0)
            for state in [
                ProcessingStatus.DOWNLOADING,
                ProcessingStatus.DECRYPTING,
                ProcessingStatus.PARSING,
                ProcessingStatus.ANALYZING,
            ]
        )
        return {
            "total": sum(counts.values()),
            "pending": counts.get(ProcessingStatus.PENDING.value, 0),
            "in_progress": in_progress,
            "awaiting_approval": counts.get(ProcessingStatus.AWAITING_APPROVAL.value, 0),
            "completed": counts.get(ProcessingStatus.COMPLETED.value, 0),
            "failed": counts.get(ProcessingStatus.FAILED.value, 0),
            "skipped": counts.get(ProcessingStatus.SKIPPED.value, 0),
        }
    except SQLAlchemyError as exc:
        logger.warning("Queue statistics query failed: %s", exc)
        return {
            "total": 0,
            "pending": 0,
            "in_progress": 0,
            "awaiting_approval": 0,
            "completed": 0,
            "failed": 0,
            "skipped": 0,
            "error": _normalize_exception(exc),
        }
    finally:
        session.close()


def _format_log_entry(log: ProcessingLog) -> Dict[str, Any]:
    return {
        "id": log.id,
        "file_id": log.file_id,
        "step": log.step,
        "status": log.status,
        "message": log.message,
        "duration_seconds": log.duration_seconds,
        "created_at": log.created_at.isoformat() if isinstance(log.created_at, datetime) else None,
    }


def get_recent_errors(limit: int = 5) -> List[Dict[str, Any]]:
    session = SessionLocal()
    try:
        logs = (
            session.query(ProcessingLog)
            .filter(ProcessingLog.status == "failed")
            .order_by(ProcessingLog.created_at.desc())
            .limit(limit)
            .all()
        )
        if logs:
            return [_format_log_entry(log) for log in logs]
        files = (
            session.query(OAFileInfo)
            .filter(OAFileInfo.error_count > 0)
            .order_by(OAFileInfo.updated_at.desc())
            .limit(limit)
            .all()
        )
        results: List[Dict[str, Any]] = []
        for item in files:
            results.append(
                {
                    "file_id": item.imagefileid,
                    "status": "failed",
                    "message": item.last_error,
                    "created_at": item.updated_at.isoformat() if isinstance(item.updated_at, datetime) else None,
                }
            )
        return results
    except SQLAlchemyError as exc:
        logger.warning("Recent errors query failed: %s", exc)
        return []
    finally:
        session.close()


def get_recent_activity(limit: int = 10) -> List[Dict[str, Any]]:
    session = SessionLocal()
    try:
        logs = (
            session.query(ProcessingLog)
            .order_by(ProcessingLog.created_at.desc())
            .limit(limit)
            .all()
        )
        return [_format_log_entry(log) for log in logs]
    except SQLAlchemyError as exc:
        logger.warning("Recent activity query failed: %s", exc)
        return []
    finally:
        session.close()


def get_dify_overview() -> Dict[str, Any]:
    try:
        connection = dify_service.check_api_connection()
        dataset_info = dify_service.get_dataset_overview()
        return {
            "connection": connection,
            "dataset": dataset_info,
            "document_total": dataset_info.get("total_documents") if dataset_info else None,
            "pagination": dataset_info.get("pagination") if dataset_info else None,
        }
    except Exception as e:
        logger.error(f"获取Dify概览失败: {e}")
        return {
            "connection": {"success": False, "error": str(e)},
            "dataset": None,
            "document_total": None,
            "pagination": None,
        }


def get_system_snapshot() -> Dict[str, Any]:
    """Aggregate subsystem checks for API consumption."""
    db_status = check_database_connection()
    redis_status = check_redis_connection()
    s3_status = check_s3_connection()
    celery_status = check_celery_health()

    healthy_count = sum(1 for item in [db_status, redis_status, s3_status, celery_status] if item.get("connected"))
    if healthy_count >= 3:
        overall = "healthy"
    elif healthy_count >= 1:
        overall = "warning"
    else:
        overall = "error"

    return {
        "overall": overall,
        "database": db_status,
        "redis": redis_status,
        "s3": s3_status,
        "celery": celery_status,
        "queue": get_queue_statistics(),
        "recent_errors": get_recent_errors(),
        "recent_activity": get_recent_activity(),
    }


def get_s3_overview(include_stats: bool = True) -> Dict[str, Any]:
    status = check_s3_connection()
    diagnostics = None
    stats = None
    if include_stats and status.get("connected"):
        stats = get_s3_storage_stats()
    return {
        "status": status,
        "stats": stats,
        "diagnostics": diagnostics,
        "config": {
            "bucket": settings.s3_bucket_name,
            "region": settings.s3_region,
            "endpoint": settings.s3_endpoint_url,
        },
    }


def run_s3_full_diagnostics() -> Dict[str, Any]:
    status = check_s3_connection()
    if not status.get("connected"):
        return {"success": False, "error": status.get("error")}
    diagnostics = run_s3_diagnostics()
    stats = get_s3_storage_stats()
    return {
        "success": diagnostics.get("success", False) and stats.get("success", False),
        "status": status,
        "diagnostics": diagnostics,
        "stats": stats,
    }


def get_ai_pipeline_summary() -> Dict[str, Any]:
    queue = get_queue_statistics()
    return {
        "queue": queue,
    }