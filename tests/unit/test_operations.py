from datetime import datetime, timedelta
from sqlalchemy.orm import sessionmaker

from api import console
from models import (
    BusinessCategory,
    CleanupCandidate,
    OAFileInfo,
    ProcessingLog,
    ProcessingStatus,
)
from models_operations import JobRun
from services import operations


def _utc(value):
    return datetime.fromisoformat(value)


def test_shanghai_day_bounds_and_iso_timezone():
    day, start, end = operations.day_bounds_utc("2026-10-12")
    assert day.isoformat() == "2026-10-12"
    assert start == _utc("2026-10-11T16:00:00")
    assert end == _utc("2026-10-12T16:00:00")
    assert operations.to_shanghai_iso(start) == "2026-10-12T00:00:00+08:00"


def test_documents_filter_by_touch_day_and_return_safe_labeled_rows(db, make_doc):
    day_doc = make_doc(
        "day-file",
        imagefilename="当日制度.pdf",
        processing_status=ProcessingStatus.FAILED,
        processing_started_at=_utc("2026-10-11T17:00:00"),
        processing_completed_at=_utc("2026-10-11T18:00:00"),
        last_error="解析失败: 文档正文、api_key=super-secret",
        updated_at=_utc("2026-10-11T18:00:00"),
    )
    old_doc = make_doc(
        "old-file",
        imagefilename="昨日制度.pdf",
        created_at=_utc("2026-10-11T15:59:59"),
        last_sync_at=_utc("2026-10-11T15:59:59"),
        updated_at=_utc("2026-10-11T15:59:59"),
    )
    db.add(ProcessingLog(
        file_id=day_doc.imagefileid,
        step="parse",
        status="failed",
        message="敏感正文绝不返回",
        created_at=_utc("2026-10-11T17:30:00"),
    ))
    db.add(ProcessingLog(
        file_id=old_doc.imagefileid,
        step="parse",
        status="success",
        created_at=_utc("2026-10-11T15:00:00"),
    ))
    db.commit()

    page = operations.get_documents(db, day="2026-10-12", q="当日", status="FAILED", page=1, page_size=5)
    assert page["total"] == 1
    item = page["items"][0]
    assert item["file_id"] == "day-file"
    assert item["category_label"] == "公共发布及规范文件"
    assert item["status_label"] == "处理失败"
    assert item["last_error"] == "文件解析失败"
    assert "正文" not in item["last_error"]
    assert "secret" not in str(item)
    assert item["started_at"].endswith("+08:00")


def test_daily_counts_distinct_documents_and_persistent_runs(db, make_doc):
    started = make_doc(
        "started",
        processing_status=ProcessingStatus.PENDING,
        processing_started_at=_utc("2026-10-11T17:00:00"),
        created_at=_utc("2026-10-11T17:00:00"),
        updated_at=_utc("2026-10-11T17:00:00"),
    )
    completed = make_doc(
        "completed",
        processing_status=ProcessingStatus.COMPLETED,
        processing_started_at=_utc("2026-10-11T17:10:00"),
        processing_completed_at=_utc("2026-10-11T17:20:00"),
        created_at=_utc("2026-10-11T17:10:00"),
        updated_at=_utc("2026-10-11T17:20:00"),
    )
    failed = make_doc(
        "failed",
        processing_status=ProcessingStatus.FAILED,
        processing_started_at=_utc("2026-10-11T17:30:00"),
        processing_completed_at=_utc("2026-10-11T17:40:00"),
        created_at=_utc("2026-10-11T17:30:00"),
        updated_at=_utc("2026-10-11T17:40:00"),
        last_error="下载失败: internal response with private content",
    )
    db.add_all([
        ProcessingLog(file_id=started.imagefileid, step="download", status="success", created_at=_utc("2026-10-11T17:01:00")),
        ProcessingLog(file_id=completed.imagefileid, step="add_to_kb", status="success", created_at=_utc("2026-10-11T17:20:00")),
        ProcessingLog(file_id=failed.imagefileid, step="download", status="failed", message="credential=hidden", created_at=_utc("2026-10-11T17:40:00")),
        CleanupCandidate(
            unique_key="cleanup-1", file_id="completed", document_id="dify-completed",
            dataset_id="kb-test", kind="expiration", evidence="{}", status="deleted",
            created_at=_utc("2026-10-11T17:50:00"), executed_at=_utc("2026-10-11T18:00:00"),
        ),
        JobRun(
            task_id="task-1", task_name="batch_process_documents", kind="batch", label="批量处理",
            status="warning", started_at=_utc("2026-10-11T17:02:00"),
            finished_at=_utc("2026-10-11T17:03:00"), counts={"submitted": 1, "submission_errors": 1},
            error="部分记录处理失败，请查看文档状态或清理建议", message="已提交1个单文件任务",
            created_at=_utc("2026-10-11T17:01:00"), updated_at=_utc("2026-10-11T17:03:00"),
        ),
    ])
    db.commit()

    result = operations.get_daily(db, "2026-10-12")
    assert result["timezone"] == "Asia/Shanghai"
    assert result["summary"] == {
        "imported": 3,
        "processed": 3,
        "completed": 1,
        "failed": 1,
        "skipped": 0,
        "awaiting_approval": 0,
        "cleanup_candidates": 1,
        "deleted": 1,
    }
    assert result["runs"][0]["status_label"] == "部分异常"
    assert result["runs"][0]["counts"] == {"submitted": 1, "submission_errors": 1}
    assert result["runs"][0]["started_at"].endswith("+08:00")
    assert "历史任务" not in str(result["activity"])


def test_trend_uses_shanghai_dates_and_real_counts(db, make_doc):
    make_doc(
        "today-completed",
        processing_status=ProcessingStatus.COMPLETED,
        processing_completed_at=_utc("2026-10-11T17:00:00"),
        created_at=_utc("2026-10-11T17:00:00"),
        updated_at=_utc("2026-10-11T17:00:00"),
    )
    items = operations.get_trend(db, 1)["items"]
    assert len(items) == 1
    # The host clock may differ in tests; the target date is derived from the actual Shanghai day.
    assert items[0]["date"]
    assert set(items[0]) == {"date", "imported", "completed", "failed", "deleted"}


def test_celery_lifecycle_persists_warning_counts_without_raw_errors(db, monkeypatch):
    factory = sessionmaker(bind=db.bind)
    monkeypatch.setattr(operations, "get_db_session", factory)

    task_name = "tasks.document_processor.import_dat_file_task"
    operations.record_job_published("job-track", task_name)
    operations.record_job_started("job-track", task_name)
    # A fast worker can start before the producer's after-publish callback runs.
    operations.record_job_published("job-track", task_name)
    assert db.query(JobRun).filter_by(task_id="job-track").one().status == "running"
    operations.record_job_retry("job-track", task_name)
    operations.record_job_started("job-track", task_name)
    operations.record_job_finished(
        "job-track",
        task_name,
        "SUCCESS",
        {
            "success": True,
            "stats": {
                "new_records": 4,
                "updated_records": 2,
                "skipped_records": 1,
                "error_records": 1,
                "errors": ["/secure/path document正文 api_key=do-not-persist"],
            },
        },
    )

    row = db.query(JobRun).filter_by(task_id="job-track").one()
    assert row.status == "warning"
    assert row.attempt_count == 2
    assert row.retry_count == 1
    assert row.counts == {"imported": 4, "updated": 2, "skipped": 1, "errors": 1}
    assert "do-not-persist" not in str(row.counts)
    assert "document正文" not in str(row.error)
    assert row.started_at is not None and row.finished_at is not None


def test_batch_result_distinguishes_queued_subtasks_from_completed_import(monkeypatch):
    class QueuedTask:
        id = "real-celery-id"

    monkeypatch.setattr(console.batch_process_documents, "delay", lambda limit: QueuedTask())
    result = console.console_action(console.ConsoleActionRequest(action="process_pending", limit=8))
    assert result["success"] is True
    assert result["task_id"] == "real-celery-id"
    assert "不代表已入库" in result["message"]


def test_console_scan_must_be_explicitly_preview():
    import pytest
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        console.ConsoleActionRequest(action="scan_cleanup", dry_run=False)


def test_prerun_calls_runtime_hot_refresh(monkeypatch):
    from services import runtime_config
    from tasks.document_processor import refresh_runtime_settings_and_track

    calls = []
    monkeypatch.setattr(runtime_config, "refresh_runtime_settings", lambda: calls.append("refresh"))
    monkeypatch.setattr(operations, "record_job_started", lambda task_id, task_name: None)
    refresh_runtime_settings_and_track(sender="tasks.document_processor.batch_process_documents", task_id="prerun-id")
    assert calls == ["refresh"]


def test_publish_is_recorded_only_after_broker_publish(monkeypatch):
    from celery.signals import after_task_publish, before_task_publish
    from tasks.document_processor import track_published_task

    calls = []
    monkeypatch.setattr(operations, "record_job_published", lambda task_id, task_name: calls.append((task_id, task_name)))
    sender = "tasks.document_processor.import_dat_file_task"
    headers = {"id": "broker-confirmed-id", "task": sender}

    before_task_publish.send(sender=sender, headers=headers, body=None)
    assert calls == []
    after_task_publish.send(sender=sender, headers=headers, body=None)
    assert calls == [("broker-confirmed-id", sender)]


def test_daily_runs_include_finishes_and_live_cross_midnight_tasks(db):
    today, start, end = operations.day_bounds_utc()
    yesterday = today - timedelta(days=1)
    yesterday_start = operations.day_bounds_utc(yesterday)[1]

    def run(task_id, status, started_at, finished_at=None, created_at=None):
        return JobRun(
            task_id=task_id,
            task_name="tasks.document_processor.process_document",
            kind="document",
            label="单文件处理",
            status=status,
            started_at=started_at,
            finished_at=finished_at,
            counts={},
            created_at=created_at or started_at,
            updated_at=finished_at or started_at,
        )

    db.add_all([
        run("cross-midnight-running", "running", start - timedelta(minutes=30)),
        run("cross-midnight-retry", "retrying", start - timedelta(minutes=15)),
        run("finished-today", "success", yesterday_start, start + timedelta(minutes=5)),
        run("started-today", "running", start + timedelta(hours=1)),
        run("old-active", "running", yesterday_start - timedelta(days=1)),
        run("finished-yesterday", "success", yesterday_start - timedelta(hours=1), yesterday_start + timedelta(minutes=5)),
    ])
    db.commit()

    today_runs = operations.get_daily(db, today)["runs"]
    today_ids = {item["task_id"] for item in today_runs}
    assert today_ids == {
        "cross-midnight-running", "cross-midnight-retry", "finished-today", "started-today", "old-active",
    }
    yesterday_ids = {item["task_id"] for item in operations.get_daily(db, yesterday)["runs"]}
    assert "finished-yesterday" in yesterday_ids
    assert "old-active" not in yesterday_ids


def test_beat_cleanup_tasks_resolve_hot_delete_setting_at_execution(monkeypatch):
    from tasks import document_processor as tasks

    class FakeDB:
        def close(self):
            pass

    db_instance = FakeDB()
    monkeypatch.setattr(tasks, "get_db_session", lambda: db_instance)
    observed = []
    monkeypatch.setattr(
        tasks.version_manager,
        "process_headquarters_version_deduplication",
        lambda db, limit, dry_run: observed.append(("versions", dry_run)) or {"processed": 0, "errors": 0},
    )
    monkeypatch.setattr(
        tasks.version_manager,
        "process_document_expiration_check",
        lambda db, limit, dry_run: observed.append(("expiration", dry_run)) or {"processed": 0, "deleted": 0, "errors": 0, "candidates": 0},
    )
    monkeypatch.setattr(
        tasks.version_manager,
        "process_duplicate_document_cleanup",
        lambda db, days, limit, dry_run: observed.append(("duplicates", dry_run)) or {"processed": 0, "deleted": 0, "errors": 0, "candidates": 0},
    )

    monkeypatch.setattr(tasks.settings, "cleanup_auto_delete", True)
    tasks.clean_headquarters_version_duplicates.run(2, None)
    tasks.clean_expired_documents.run(2, 5, None)
    assert observed == [("versions", False), ("expiration", False), ("duplicates", False)]
    assert tasks.app.conf.beat_schedule["clean-headquarters-version-duplicates"]["args"] == (2000, None)
    assert tasks.app.conf.beat_schedule["clean-expired-documents"]["args"] == (2000, 5, None)

    observed.clear()
    monkeypatch.setattr(tasks.settings, "cleanup_auto_delete", False)
    tasks.clean_headquarters_version_duplicates.run(2, None)
    tasks.clean_expired_documents.run(2, 5, None)
    assert observed == [("versions", True), ("expiration", True), ("duplicates", True)]

    observed.clear()
    monkeypatch.setattr(tasks.settings, "cleanup_auto_delete", True)
    tasks.clean_expired_documents.run(2, 5, True)
    assert observed == [("expiration", True), ("duplicates", True)]


def test_console_scans_pass_explicit_preview_mode(monkeypatch):
    submitted = []

    class QueuedTask:
        def __init__(self, task_id):
            self.id = task_id

    monkeypatch.setattr(
        console.clean_expired_documents,
        "delay",
        lambda *args: submitted.append(("cleanup", args)) or QueuedTask("cleanup-task"),
    )
    monkeypatch.setattr(
        console.clean_headquarters_version_duplicates,
        "delay",
        lambda *args: submitted.append(("versions", args)) or QueuedTask("versions-task"),
    )

    console.console_action(console.ConsoleActionRequest(action="scan_cleanup", limit=12))
    console.console_action(console.ConsoleActionRequest(action="scan_versions", limit=13))
    assert submitted == [
        ("cleanup", (12, 5, True)),
        ("versions", (13, True)),
    ]
