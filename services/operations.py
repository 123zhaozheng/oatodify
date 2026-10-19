"""Daily operations queries and durable Celery run tracking."""

from datetime import date, datetime, time, timedelta, timezone
import logging
from zoneinfo import ZoneInfo

from sqlalchemy import and_, func, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from database import get_db_session
from models import (
    BusinessCategory,
    CleanupCandidate,
    OAFileInfo,
    ProcessingLog,
    ProcessingStatus,
)
from models_operations import JobRun


logger = logging.getLogger(__name__)
SHANGHAI = ZoneInfo("Asia/Shanghai")
UTC = timezone.utc

TASK_KINDS = {
    "import_dat_file_task": ("import", "DAT导入"),
    "batch_process_documents": ("batch", "批量处理"),
    "process_document": ("document", "单文件处理"),
    "approve_document": ("approval", "人工审核"),
    "clean_headquarters_version_duplicates": ("version_scan", "版本扫描"),
    "clean_expired_documents": ("cleanup_scan", "过期及重复扫描"),
    "execute_cleanup_candidate": ("cleanup_execution", "清理执行"),
}

STATUS_LABELS = {
    "queued": "排队中",
    "running": "运行中",
    "retrying": "等待重试",
    "success": "已完成",
    "warning": "部分异常",
    "failed": "执行失败",
}

PROCESSING_STATUS_LABELS = {
    ProcessingStatus.PENDING.value: "待处理",
    ProcessingStatus.DOWNLOADING.value: "读取中",
    ProcessingStatus.DECRYPTING.value: "解密中",
    ProcessingStatus.PARSING.value: "解析中",
    ProcessingStatus.ANALYZING.value: "分析中",
    ProcessingStatus.AWAITING_APPROVAL.value: "待人工审核",
    ProcessingStatus.COMPLETED.value: "已入库",
    ProcessingStatus.FAILED.value: "处理失败",
    ProcessingStatus.SKIPPED.value: "已跳过",
}

CATEGORY_LABELS = {
    BusinessCategory.HEADQUARTERS_ISSUE.value: "总行发文",
    BusinessCategory.RETAIL_ANNOUNCEMENT.value: "零售条线公告",
    BusinessCategory.PUBLICATION_RELEASE.value: "刊物发布",
    BusinessCategory.BRANCH_ISSUE.value: "支行发文",
    BusinessCategory.BRANCH_RECEIVE.value: "支行收文",
    BusinessCategory.PUBLIC_STANDARD.value: "公共发布及规范文件",
    BusinessCategory.HEADQUARTERS_RECEIVE.value: "总行收文",
    BusinessCategory.CORPORATE_ANNOUNCEMENT.value: "公司条线公告",
}

PROCESS_PROGRESS = {
    ProcessingStatus.PENDING.value: 0,
    ProcessingStatus.DOWNLOADING.value: 15,
    ProcessingStatus.DECRYPTING.value: 30,
    ProcessingStatus.PARSING.value: 50,
    ProcessingStatus.ANALYZING.value: 70,
    ProcessingStatus.AWAITING_APPROVAL.value: 85,
    ProcessingStatus.COMPLETED.value: 100,
    ProcessingStatus.FAILED.value: 0,
    ProcessingStatus.SKIPPED.value: 100,
}

_FATAL_LOG_STEPS = (
    "download", "decrypt", "parse", "add_to_kb", "manual_approve", "cleanup",
)
_COMPLETION_LOG_STEPS = ("add_to_kb", "manual_approve")
_SKIP_LOG_STEPS = ("skip", "manual_reject", "batch_filter")


def utcnow_naive() -> datetime:
    """Return a naive UTC datetime for the project's existing DB convention."""
    return datetime.now(UTC).replace(tzinfo=None)


def to_utc_naive(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        # Existing naive rows are interpreted with the project's UTC deployment semantics.
        return value
    return value.astimezone(UTC).replace(tzinfo=None)


def to_shanghai_iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    utc_value = value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
    return utc_value.astimezone(SHANGHAI).isoformat(timespec="seconds")


def resolve_day(value: date | str | None = None) -> date:
    if value is None or value == "":
        return datetime.now(SHANGHAI).date()
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value))
    except (TypeError, ValueError) as exc:
        raise ValueError("日期必须符合 YYYY-MM-DD 格式") from exc


def day_bounds_utc(day: date | str | None = None) -> tuple[date, datetime, datetime]:
    """Return the requested Shanghai calendar day as half-open naive UTC bounds."""
    resolved = resolve_day(day)
    start_local = datetime.combine(resolved, time.min, tzinfo=SHANGHAI)
    end_local = start_local + timedelta(days=1)
    return (
        resolved,
        start_local.astimezone(UTC).replace(tzinfo=None),
        end_local.astimezone(UTC).replace(tzinfo=None),
    )


def _task_identity(task_name: str | None) -> tuple[str, str] | None:
    short_name = (task_name or "").rsplit(".", 1)[-1]
    return TASK_KINDS.get(short_name)


def _ensure_job(db: Session, task_id: str, task_name: str | None) -> JobRun | None:
    identity = _task_identity(task_name)
    if not task_id or not identity:
        return None
    kind, label = identity
    row = db.query(JobRun).filter(JobRun.task_id == str(task_id)).first()
    if row:
        row.task_name = task_name or row.task_name
        row.kind = kind
        row.label = label
        return row

    row = JobRun(
        task_id=str(task_id),
        task_name=task_name or (task_name or "").rsplit(".", 1)[-1],
        kind=kind,
        label=label,
        status="queued",
        counts={},
        attempt_count=0,
        retry_count=0,
        created_at=utcnow_naive(),
        updated_at=utcnow_naive(),
    )
    db.add(row)
    try:
        db.flush()
        return row
    except IntegrityError:
        # A worker may receive the task before the producer finishes its publish signal.
        db.rollback()
        return db.query(JobRun).filter(JobRun.task_id == str(task_id)).first()


def _persist(task_id: str, task_name: str | None, update) -> None:
    """Persist a signal update without ever making Celery execution depend on it."""
    if not task_id or not _task_identity(task_name):
        return
    db = None
    try:
        db = get_db_session()
        row = _ensure_job(db, str(task_id), task_name)
        if row is None:
            return
        update(row)
        row.updated_at = utcnow_naive()
        db.commit()
    except Exception as exc:  # Signal handlers must not break task publication/execution.
        if db is not None:
            db.rollback()
        logger.warning("JobRun记录失败（%s）", type(exc).__name__)
    finally:
        if db is not None:
            db.close()


def record_job_published(task_id: str, task_name: str) -> None:
    def update(row):
        if row.status in ("queued", "retrying"):
            row.status = "queued"
            row.message = "任务已提交，等待Worker执行"
            row.error = None
            row.finished_at = None
    _persist(task_id, task_name, update)


def record_job_started(task_id: str, task_name: str) -> None:
    def update(row):
        row.status = "running"
        if row.started_at is None:
            row.started_at = utcnow_naive()
        row.attempt_count = (row.attempt_count or 0) + 1
        row.message = "任务正在执行"
        row.error = None
        row.finished_at = None
    _persist(task_id, task_name, update)


def record_job_retry(task_id: str, task_name: str) -> None:
    def update(row):
        row.status = "retrying"
        row.retry_count = (row.retry_count or 0) + 1
        row.message = "任务将自动重试"
        row.error = "执行异常，任务已安排自动重试"
        row.finished_at = None
    _persist(task_id, task_name, update)


def record_job_failure(task_id: str, task_name: str, error_type: str | None = None) -> None:
    safe_type = error_type if error_type and error_type.isidentifier() else "任务异常"
    def update(row):
        row.status = "failed"
        row.error = f"任务执行失败（{safe_type}）"
        row.message = "任务执行失败；未保存异常正文或密钥"
        row.finished_at = utcnow_naive()
    _persist(task_id, task_name, update)


def _number(value) -> int | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return max(0, int(value))


def _curated_counts(kind: str, result) -> dict:
    if not isinstance(result, dict):
        return {}

    if kind == "batch":
        results = result.get("results")
        if isinstance(results, list):
            failed = sum(1 for item in results if isinstance(item, dict) and item.get("error"))
            submitted = sum(1 for item in results if isinstance(item, dict) and not item.get("error"))
            return {"submitted": submitted, "submission_errors": failed}
        count = _number(result.get("processed_count"))
        return {"submitted": count or 0, "submission_errors": 0}

    if kind == "import":
        stats = result.get("stats") if isinstance(result.get("stats"), dict) else result
        errors = stats.get("errors")
        return {
            "imported": _number(stats.get("new_records")) or 0,
            "updated": _number(stats.get("updated_records")) or 0,
            "skipped": _number(stats.get("skipped_records")) or 0,
            "errors": _number(stats.get("error_records")) or (len(errors) if isinstance(errors, list) else 0),
        }

    if kind == "cleanup_scan":
        summary = result.get("summary") if isinstance(result.get("summary"), dict) else {}
        expiration = result.get("expiration_cleanup") if isinstance(result.get("expiration_cleanup"), dict) else {}
        duplicate = result.get("duplicate_cleanup") if isinstance(result.get("duplicate_cleanup"), dict) else {}
        return {
            "processed": _number(summary.get("total_processed")) or 0,
            "candidates": (_number(expiration.get("candidates")) or 0) + (_number(duplicate.get("candidates")) or 0),
            "deleted": _number(summary.get("total_deleted")) or 0,
            "errors": _number(summary.get("total_errors")) or 0,
        }

    # Only known numeric result fields are persisted. Detail objects, messages,
    # document excerpts, task arguments, and credentials are never copied.
    allowed = ("processed", "candidates", "deleted", "errors", "duplicates_found")
    counts = {key: _number(result.get(key)) for key in allowed}
    counts = {key: value for key, value in counts.items() if value is not None}
    if kind == "document":
        counts["processed"] = 1
        status = result.get("status")
        if status == ProcessingStatus.COMPLETED.value:
            counts["completed"] = 1
        elif status == ProcessingStatus.FAILED.value:
            counts["failed"] = 1
        elif status == ProcessingStatus.SKIPPED.value:
            counts["skipped"] = 1
        elif status == ProcessingStatus.AWAITING_APPROVAL.value:
            counts["awaiting_approval"] = 1
    elif kind == "approval":
        counts["approved"] = int(result.get("approved") is True)
        counts["rejected"] = int(result.get("approved") is False)
    elif kind == "cleanup_execution" and result.get("success") is True:
        counts["deleted"] = 0 if result.get("already_deleted") else 1
    return counts


def _outcome(kind: str, state: str, result) -> tuple[str, dict, str | None, str]:
    normalized_state = str(state or "").upper()
    if normalized_state == "RETRY":
        return "retrying", {}, "执行异常，任务已安排自动重试", "任务将自动重试"
    if normalized_state != "SUCCESS":
        return "failed", {}, "任务执行失败", "任务执行失败；未保存异常正文或密钥"

    counts = _curated_counts(kind, result)
    if isinstance(result, dict) and result.get("success") is False:
        return "failed", counts, "任务返回失败", "任务返回失败；未保存异常正文或密钥"

    warning = False
    if kind == "batch":
        warning = counts.get("submission_errors", 0) > 0
        message = f"已提交{counts.get('submitted', 0)}个单文件任务；入库结果由单文件任务记录"
    elif kind == "import":
        warning = counts.get("errors", 0) > 0
        message = "DAT导入任务已完成"
    elif kind in ("cleanup_scan", "version_scan"):
        warning = counts.get("errors", 0) > 0
        message = "扫描完成，清理操作仅按任务参数执行"
    elif kind == "document" and isinstance(result, dict):
        warning = result.get("status") == ProcessingStatus.FAILED.value
        status = result.get("status")
        if status == ProcessingStatus.AWAITING_APPROVAL.value:
            message = "处理完成，等待人工审核"
        elif status == ProcessingStatus.SKIPPED.value:
            message = "处理完成，文件已跳过"
        elif status == ProcessingStatus.COMPLETED.value:
            message = "文档已入库"
        elif warning:
            message = "任务已执行，但文档处理失败"
        else:
            message = "单文件处理任务已完成"
    elif kind == "approval":
        message = "人工审核任务已完成"
    elif kind == "cleanup_execution":
        message = "清理执行任务已完成"
    else:
        message = "任务已完成"

    if warning:
        error = "部分记录处理失败，请查看文档状态或清理建议"
        return "warning", counts, error, message
    return "success", counts, None, message


def record_job_finished(task_id: str, task_name: str, state: str, result=None) -> None:
    identity = _task_identity(task_name)
    if not identity:
        return
    kind, _ = identity
    status, counts, error, message = _outcome(kind, state, result)

    def update(row):
        row.status = status
        row.counts = counts
        row.error = error
        row.message = message
        if status == "retrying":
            row.finished_at = None
        else:
            row.finished_at = utcnow_naive()
    _persist(task_id, task_name, update)


def _range(column, start: datetime, end: datetime):
    return and_(column >= start, column < end)


def _log_file_ids(db: Session, start: datetime, end: datetime, *, steps=None, statuses=None):
    query = db.query(ProcessingLog.file_id).join(
        OAFileInfo, OAFileInfo.imagefileid == ProcessingLog.file_id
    ).filter(
        OAFileInfo.is_zw.is_(True),
        _range(ProcessingLog.created_at, start, end),
    )
    if steps:
        query = query.filter(ProcessingLog.step.in_(steps))
    if statuses:
        query = query.filter(ProcessingLog.status.in_(statuses))
    return {file_id for (file_id,) in query.distinct().all()}


def _file_ids_by_status_time(db: Session, status: ProcessingStatus, column, start, end):
    return {
        file_id for (file_id,) in db.query(OAFileInfo.imagefileid).filter(
            OAFileInfo.is_zw.is_(True),
            OAFileInfo.processing_status == status,
            _range(column, start, end),
        ).all()
    }


def _daily_counts(db: Session, start: datetime, end: datetime) -> dict:
    """Count a Shanghai day using UTC half-open bounds.

    ``imported`` counts rows created that day; ``processed`` counts distinct
   正文 rows with a start time or processing log that day. Terminal counts
    use that day's terminal timestamp or matching stage logs. Approval is the
    live pending-review backlog; cleanup candidates and deletions use their
    creation and execution timestamps respectively.
    """
    imported = db.query(OAFileInfo.id).filter(_range(OAFileInfo.created_at, start, end)).count()
    started_ids = {
        file_id for (file_id,) in db.query(OAFileInfo.imagefileid).filter(
            OAFileInfo.is_zw.is_(True), _range(OAFileInfo.processing_started_at, start, end)
        ).all()
    }
    all_log_ids = _log_file_ids(db, start, end)
    completed_ids = _log_file_ids(db, start, end, steps=_COMPLETION_LOG_STEPS, statuses=("success",))
    completed_ids |= _file_ids_by_status_time(db, ProcessingStatus.COMPLETED, OAFileInfo.processing_completed_at, start, end)
    failed_ids = _log_file_ids(db, start, end, steps=_FATAL_LOG_STEPS, statuses=("failed",))
    failed_ids |= _file_ids_by_status_time(db, ProcessingStatus.FAILED, OAFileInfo.processing_completed_at, start, end)
    skipped_ids = _log_file_ids(db, start, end, steps=_SKIP_LOG_STEPS)
    skipped_ids |= _file_ids_by_status_time(db, ProcessingStatus.SKIPPED, OAFileInfo.processing_completed_at, start, end)
    processed_ids = started_ids | all_log_ids
    cleanup_candidates = db.query(CleanupCandidate.id).filter(_range(CleanupCandidate.created_at, start, end)).count()
    deleted = db.query(CleanupCandidate.id).filter(
        CleanupCandidate.status == "deleted",
        _range(CleanupCandidate.executed_at, start, end),
    ).count()
    awaiting_approval = db.query(OAFileInfo.id).filter(
        OAFileInfo.is_zw.is_(True),
        OAFileInfo.processing_status == ProcessingStatus.AWAITING_APPROVAL,
    ).count()
    return {
        "imported": imported,
        "processed": len(processed_ids),
        "completed": len(completed_ids),
        "failed": len(failed_ids),
        "skipped": len(skipped_ids),
        # This is a live backlog snapshot so an operator sees approvals still waiting today.
        "awaiting_approval": awaiting_approval,
        "cleanup_candidates": cleanup_candidates,
        "deleted": deleted,
    }


def _pipeline(db: Session) -> list[dict]:
    grouped = db.query(OAFileInfo.processing_status, func.count(OAFileInfo.id)).filter(
        OAFileInfo.is_zw.is_(True)
    ).group_by(OAFileInfo.processing_status).all()
    counts = {key: 0 for key in PROCESSING_STATUS_LABELS}
    for status, count in grouped:
        key = status.value if hasattr(status, "value") else str(status)
        if key in counts:
            counts[key] += count
    return [
        {"key": key, "label": label, "count": counts[key]}
        for key, label in PROCESSING_STATUS_LABELS.items()
    ]


def _job_run_item(row: JobRun) -> dict:
    return {
        "id": row.id,
        "task_id": row.task_id,
        "kind": row.kind,
        "label": row.label,
        "status": row.status,
        "status_label": STATUS_LABELS.get(row.status, row.status),
        "started_at": to_shanghai_iso(row.started_at),
        "finished_at": to_shanghai_iso(row.finished_at),
        "counts": row.counts if isinstance(row.counts, dict) else {},
        "error": row.error,
        "message": row.message,
        "attempt_count": row.attempt_count or 0,
        "retry_count": row.retry_count or 0,
    }


def _safe_error_summary(value) -> str | None:
    """Map stored error text to a fixed category; never expose the raw exception."""
    if not value:
        return None
    prefix = str(value).strip().split(":", 1)[0].strip().lower()
    if prefix.startswith(("下载失败", "文件读取失败")):
        return "文件读取失败"
    if prefix.startswith(("解密失败", "文件解密失败")):
        return "文件解密失败"
    if prefix.startswith(("解析失败", "重新解析文档失败")):
        return "文件解析失败"
    if prefix.startswith(("ai分析失败", "模型分析失败")):
        return "模型分析失败"
    if prefix.startswith(("加入知识库失败", "加入知识库异常")):
        return "知识库入库失败"
    if prefix.startswith(("审核", "重新处理文件失败")):
        return "人工审核处理失败"
    if prefix.startswith(("任务", "文档")):
        return "任务执行失败，请查看受控日志"
    return "处理失败，请查看受控日志"


def _status_message(status: str, error: str | None = None) -> str:
    if status == ProcessingStatus.FAILED.value:
        return _safe_error_summary(error) or "处理失败，请查看受控日志"
    return {
        ProcessingStatus.PENDING.value: "已同步，等待处理",
        ProcessingStatus.DOWNLOADING.value: "正在读取文件",
        ProcessingStatus.DECRYPTING.value: "正在解密文件",
        ProcessingStatus.PARSING.value: "正在解析文件",
        ProcessingStatus.ANALYZING.value: "正在分析文件",
        ProcessingStatus.AWAITING_APPROVAL.value: "等待人工审核",
        ProcessingStatus.COMPLETED.value: "文档已入库",
        ProcessingStatus.SKIPPED.value: "文件已跳过",
    }.get(status, "状态未知")


def _safe_step_label(step: str, log_status: str) -> str:
    labels = {
        "download": "读取文件",
        "decrypt": "解密文件",
        "parse": "解析文件",
        "analyze": "模型分析",
        "add_to_kb": "写入知识库",
        "review": "人工审核",
        "manual_approve": "人工批准入库",
        "manual_reject": "人工拒绝",
        "cleanup": "清理执行",
        "batch_filter": "批量筛选",
        "skip": "处理跳过",
    }
    action = labels.get(step, "文档处理")
    status = {"success": "完成", "failed": "失败", "pending": "等待中", "skipped": "已跳过"}.get(log_status, "更新")
    return f"{action}{status}"


def get_daily(db: Session, day: date | str | None = None) -> dict:
    resolved, start, end = day_bounds_utc(day)
    summary = _daily_counts(db, start, end)
    run_day_filters = [
        _range(JobRun.started_at, start, end),
        _range(JobRun.finished_at, start, end),
        and_(JobRun.started_at.is_(None), _range(JobRun.created_at, start, end)),
    ]
    # A task can start before Shanghai midnight and still occupy a worker on
    # today's board. Only today's live view can establish that it is still open;
    # historical dates use their recorded start/finish timestamps alone.
    if resolved == datetime.now(SHANGHAI).date():
        run_day_filters.append(and_(
            JobRun.status.in_(("running", "retrying")),
            JobRun.finished_at.is_(None),
            JobRun.started_at.isnot(None),
            JobRun.started_at < start,
        ))
    runs = db.query(JobRun).filter(or_(*run_day_filters)).order_by(
        JobRun.started_at.asc().nullsfirst(), JobRun.created_at.asc()
    ).all()

    log_rows = db.query(ProcessingLog, OAFileInfo.imagefilename).join(
        OAFileInfo, OAFileInfo.imagefileid == ProcessingLog.file_id
    ).filter(
        OAFileInfo.is_zw.is_(True),
        _range(ProcessingLog.created_at, start, end),
    ).order_by(ProcessingLog.created_at.desc(), ProcessingLog.id.desc()).limit(30).all()
    activity = [{
        "type": "document",
        "at": to_shanghai_iso(log.created_at),
        "file_id": log.file_id,
        "label": filename,
        "status": log.status,
        "message": _safe_step_label(log.step, log.status),
    } for log, filename in reversed(log_rows)]

    if not runs:
        activity.insert(0, {
            "type": "notice",
            "at": None,
            "label": "历史任务记录说明",
            "status": "unavailable",
            "message": "该日没有持久任务运行记录；旧历史仅按文档与日志统计，未补造任务记录。",
        })

    return {
        "date": resolved.isoformat(),
        "timezone": "Asia/Shanghai",
        "summary": summary,
        "pipeline": _pipeline(db),
        "runs": [_job_run_item(row) for row in runs],
        "activity": activity,
    }


def get_trend(db: Session, days: int = 14) -> dict:
    if days < 1 or days > 90:
        raise ValueError("days 必须在 1 到 90 之间")
    last_day = datetime.now(SHANGHAI).date()
    first_day = last_day - timedelta(days=days - 1)
    _, range_start, _ = day_bounds_utc(first_day)
    _, _, range_end = day_bounds_utc(last_day)

    imported_rows = db.query(OAFileInfo.created_at).filter(
        _range(OAFileInfo.created_at, range_start, range_end)
    ).all()
    completed_rows = db.query(OAFileInfo.imagefileid, OAFileInfo.processing_completed_at).filter(
        OAFileInfo.is_zw.is_(True),
        OAFileInfo.processing_status == ProcessingStatus.COMPLETED,
        _range(OAFileInfo.processing_completed_at, range_start, range_end),
    ).all()
    failed_rows = db.query(OAFileInfo.imagefileid, OAFileInfo.processing_completed_at).filter(
        OAFileInfo.is_zw.is_(True),
        OAFileInfo.processing_status == ProcessingStatus.FAILED,
        _range(OAFileInfo.processing_completed_at, range_start, range_end),
    ).all()
    log_rows = db.query(ProcessingLog.file_id, ProcessingLog.step, ProcessingLog.status, ProcessingLog.created_at).join(
        OAFileInfo, OAFileInfo.imagefileid == ProcessingLog.file_id
    ).filter(
        OAFileInfo.is_zw.is_(True),
        _range(ProcessingLog.created_at, range_start, range_end),
        or_(
            and_(ProcessingLog.step.in_(_COMPLETION_LOG_STEPS), ProcessingLog.status == "success"),
            and_(ProcessingLog.step.in_(_FATAL_LOG_STEPS), ProcessingLog.status == "failed"),
        ),
    ).all()
    deletion_rows = db.query(CleanupCandidate.executed_at).filter(
        CleanupCandidate.status == "deleted",
        _range(CleanupCandidate.executed_at, range_start, range_end),
    ).all()

    def local_day(value):
        if value is None:
            return None
        utc_value = value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
        return utc_value.astimezone(SHANGHAI).date()

    imported_counts = {}
    for (created_at,) in imported_rows:
        key = local_day(created_at)
        imported_counts[key] = imported_counts.get(key, 0) + 1
    completed_by_day = {}
    failed_by_day = {}
    for file_id, step, status, created_at in log_rows:
        key = local_day(created_at)
        if step in _COMPLETION_LOG_STEPS and status == "success":
            completed_by_day.setdefault(key, set()).add(file_id)
        elif step in _FATAL_LOG_STEPS and status == "failed":
            failed_by_day.setdefault(key, set()).add(file_id)
    for file_id, completed_at in completed_rows:
        completed_by_day.setdefault(local_day(completed_at), set()).add(file_id)
    for file_id, completed_at in failed_rows:
        failed_by_day.setdefault(local_day(completed_at), set()).add(file_id)
    deleted_counts = {}
    for (executed_at,) in deletion_rows:
        key = local_day(executed_at)
        deleted_counts[key] = deleted_counts.get(key, 0) + 1

    items = []
    for offset in range(days):
        current = first_day + timedelta(days=offset)
        items.append({
            "date": current.isoformat(),
            "imported": imported_counts.get(current, 0),
            "completed": len(completed_by_day.get(current, set())),
            "failed": len(failed_by_day.get(current, set())),
            "deleted": deleted_counts.get(current, 0),
        })
    return {"timezone": "Asia/Shanghai", "items": items}


def _status_value(value: str | ProcessingStatus) -> str:
    raw = value.value if isinstance(value, ProcessingStatus) else str(value)
    for status in ProcessingStatus:
        if raw in (status.value, status.name):
            return status.value
    raise ValueError("未知文档状态")


def _category_value(value: str | BusinessCategory) -> str:
    raw = value.value if isinstance(value, BusinessCategory) else str(value)
    for category in BusinessCategory:
        if raw in (category.value, category.name):
            return category.value
    raise ValueError("未知业务分类")


def get_documents(
    db: Session,
    *,
    day: date | str | None = None,
    page: int = 1,
    page_size: int = 20,
    status: str | ProcessingStatus | None = None,
    category: str | BusinessCategory | None = None,
    q: str | None = None,
) -> dict:
    if page < 1 or page_size < 1 or page_size > 100:
        raise ValueError("分页参数无效")
    query = db.query(OAFileInfo)
    if day not in (None, ""):
        _, start, end = day_bounds_utc(day)
        touched_log_ids = db.query(ProcessingLog.file_id).filter(
            _range(ProcessingLog.created_at, start, end)
        ).distinct()
        query = query.filter(or_(
            _range(OAFileInfo.created_at, start, end),
            _range(OAFileInfo.last_sync_at, start, end),
            _range(OAFileInfo.processing_started_at, start, end),
            _range(OAFileInfo.processing_completed_at, start, end),
            OAFileInfo.imagefileid.in_(touched_log_ids),
        ))
    if status:
        query = query.filter(OAFileInfo.processing_status == _status_value(status))
    if category:
        query = query.filter(OAFileInfo.business_category == _category_value(category))
    if q and q.strip():
        pattern = f"%{q.strip()[:200]}%"
        query = query.filter(or_(
            OAFileInfo.imagefilename.ilike(pattern),
            OAFileInfo.imagefileid.ilike(pattern),
        ))

    total = query.count()
    files = query.order_by(OAFileInfo.updated_at.desc().nullslast(), OAFileInfo.id.desc()).offset(
        (page - 1) * page_size
    ).limit(page_size).all()
    file_ids = [file.imagefileid for file in files]
    latest_logs = {}
    if file_ids:
        logs = db.query(ProcessingLog).filter(ProcessingLog.file_id.in_(file_ids)).order_by(
            ProcessingLog.created_at.desc(), ProcessingLog.id.desc()
        ).all()
        for log in logs:
            latest_logs.setdefault(log.file_id, log)

    items = []
    for file in files:
        status_value = file.processing_status.value if hasattr(file.processing_status, "value") else str(file.processing_status)
        category_value = file.business_category.value if hasattr(file.business_category, "value") else str(file.business_category)
        safe_error = _safe_error_summary(file.last_error)
        latest_log = latest_logs.get(file.imagefileid)
        current_step = PROCESSING_STATUS_LABELS.get(status_value, "状态未知")
        if status_value == ProcessingStatus.FAILED.value and latest_log:
            current_step = _safe_step_label(latest_log.step, latest_log.status)
        items.append({
            "file_id": file.imagefileid,
            "filename": file.imagefilename,
            "category": category_value,
            "category_label": CATEGORY_LABELS.get(category_value, "未分类"),
            "status": status_value,
            "status_label": PROCESSING_STATUS_LABELS.get(status_value, "状态未知"),
            "progress": PROCESS_PROGRESS.get(status_value, 0),
            "current_step": current_step,
            "message": _status_message(status_value, file.last_error),
            "last_error": safe_error,
            "started_at": to_shanghai_iso(file.processing_started_at),
            "completed_at": to_shanghai_iso(file.processing_completed_at),
            "document_id": file.document_id,
            "dataset_id": file.dify_dataset_id,
            "filesize": file.filesize,
            "filerealpath": file.filerealpath,
            "is_zw": bool(file.is_zw),
        })
    return {"total": total, "page": page, "page_size": page_size, "items": items}


__all__ = [
    "CATEGORY_LABELS",
    "PROCESSING_STATUS_LABELS",
    "SHANGHAI",
    "day_bounds_utc",
    "get_daily",
    "get_documents",
    "get_trend",
    "record_job_failure",
    "record_job_finished",
    "record_job_published",
    "record_job_retry",
    "record_job_started",
    "to_shanghai_iso",
]
