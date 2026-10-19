"""重新解数前的脏行清理工具：查询预览 + 批量删除 oa_file_info 行。

背景：数据侧曾把 NAS 路径写入 tokenkey（filerealpath 为空），期间文档无法下载。
重新解数前需按入库时间清理这段时间的行；老 S3 数据（更早入库）不受影响。

容器内用法：
  docker compose exec api python purge_reimport.py query --from 2026-08-02
  docker compose exec api python purge_reimport.py delete --from 2026-08-02 [--to 2026-10-12] [--tokenkey-abs] [--include-cleanup] [--yes]

过滤条件按 created_at（入库时间，UTC）计；--to 为闭区间当日。
--tokenkey-abs 仅作用于 tokenkey 以 / 开头（被写入 NAS 路径）的行。
--status 仅作用于指定处理状态（如 FAILED），避免误删范围内已成功的行。
delete 默认预览，加 --yes 才执行；随行删除其 processing_logs；
cleanup_candidates 属审计记录，默认仅统计，加 --include-cleanup 才一并删除。
"""
import argparse
import sys
from datetime import datetime, timedelta

from sqlalchemy import func, select, delete

from database import SessionLocal
from models import OAFileInfo, ProcessingLog, CleanupCandidate, ProcessingStatus

BATCH = 500


def build_filters(args):
    filters = [OAFileInfo.created_at >= datetime.fromisoformat(args.from_date)]
    if args.to_date:
        filters.append(OAFileInfo.created_at < datetime.fromisoformat(args.to_date) + timedelta(days=1))
    if args.tokenkey_abs:
        filters.append(OAFileInfo.tokenkey.like('/%'))
    if args.status:
        try:
            filters.append(OAFileInfo.processing_status == ProcessingStatus[args.status.upper()])
        except KeyError:
            valid = '/'.join(s.name for s in ProcessingStatus)
            raise SystemExit(f"无效状态 {args.status}，可选: {valid}")
    return filters


def report(db, args):
    filters = build_filters(args)
    total = db.execute(select(func.count()).select_from(OAFileInfo).where(*filters)).scalar()
    print(f"命中 {total} 行")
    if not total:
        return 0
    span = db.execute(
        select(func.min(OAFileInfo.created_at), func.max(OAFileInfo.created_at)).where(*filters)
    ).one()
    print(f"入库时间范围: {span[0]} ~ {span[1]}")
    by_status = db.execute(
        select(OAFileInfo.processing_status, func.count())
        .where(*filters).group_by(OAFileInfo.processing_status)
    ).all()
    print(f"处理状态分布: {dict((str(getattr(s, 'value', s)), n) for s, n in by_status)}")
    token = db.execute(
        select(
            func.count().filter(OAFileInfo.tokenkey.like('/%')),
            func.count().filter(OAFileInfo.tokenkey != None, ~OAFileInfo.tokenkey.like('/%')),  # noqa: E711
            func.count().filter((OAFileInfo.tokenkey == None) | (OAFileInfo.tokenkey == '')),  # noqa: E711
            func.count().filter(OAFileInfo.document_id != None),  # noqa: E711
        ).where(*filters)
    ).one()
    print(f"tokenkey 形态: NAS路径(/开头) {token[0]} | S3 key {token[1]} | 空 {token[2]}")
    if token[3]:
        print(f"⚠️  命中 {token[3]} 行已入 Dify（有 document_id），删除将丢失对应入库记录，请确认")
    scoped_file_ids = select(OAFileInfo.imagefileid).where(*filters)
    log_count = db.execute(
        select(func.count()).select_from(ProcessingLog)
        .where(ProcessingLog.file_id.in_(scoped_file_ids))
    ).scalar()
    cleanup_count = db.execute(
        select(func.count()).select_from(CleanupCandidate)
        .where(CleanupCandidate.file_id.in_(scoped_file_ids))
    ).scalar()
    print(f"关联记录: processing_logs {log_count} 行 | cleanup_candidates {cleanup_count} 行")
    samples = db.execute(
        select(OAFileInfo.id, OAFileInfo.imagefileid, OAFileInfo.imagefilename,
               OAFileInfo.processing_status, OAFileInfo.tokenkey, OAFileInfo.created_at)
        .where(*filters).order_by(OAFileInfo.created_at).limit(args.sample)
    ).all()
    print(f"--- 样例（前 {args.sample} 行，按入库时间）---")
    for r in samples:
        print(f"  id={r.id} {r.imagefileid} {r.imagefilename} status={r.processing_status} "
              f"created={r.created_at} tokenkey={(r.tokenkey or '')[:60]}")
    return total


def collect_ids(db, args):
    rows = db.execute(
        select(OAFileInfo.id, OAFileInfo.imagefileid).where(*build_filters(args))
    ).all()
    return [r.id for r in rows], [r.imagefileid for r in rows]


def batch_delete(db, table, column, ids):
    removed = 0
    for i in range(0, len(ids), BATCH):
        chunk = ids[i:i + BATCH]
        removed += db.execute(delete(table).where(column.in_(chunk))).rowcount
    return removed


def main():
    parser = argparse.ArgumentParser(description="重新解数前的 oa_file_info 脏行查询/删除")
    parser.add_argument("command", choices=["query", "delete"])
    parser.add_argument("--from", dest="from_date", required=True, help="起始入库日期 YYYY-MM-DD（含）")
    parser.add_argument("--to", dest="to_date", help="截止入库日期 YYYY-MM-DD（含，默认至今）")
    parser.add_argument("--tokenkey-abs", action="store_true", help="仅处理 tokenkey 以 / 开头的行")
    parser.add_argument("--status", help="仅处理指定处理状态的行，如 FAILED（避免误删范围内已成功的行）")
    parser.add_argument("--include-cleanup", action="store_true", help="连同 cleanup_candidates 一并删除")
    parser.add_argument("--yes", action="store_true", help="真正执行删除（默认只预览）")
    parser.add_argument("--sample", type=int, default=10, help="样例行数，默认 10")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        total = report(db, args)
        if args.command == "query" or not total:
            return
        if not args.yes:
            print("\n[预览] 加 --yes 执行删除：将删除命中行及其 processing_logs；"
                  "cleanup_candidates 需另加 --include-cleanup。")
            return
        row_ids, file_ids = collect_ids(db, args)
        removed_logs = batch_delete(db, ProcessingLog, ProcessingLog.file_id, file_ids)
        removed_cleanup = 0
        if args.include_cleanup:
            removed_cleanup = batch_delete(db, CleanupCandidate, CleanupCandidate.file_id, file_ids)
        removed_rows = batch_delete(db, OAFileInfo, OAFileInfo.id, row_ids)
        db.commit()
        print(f"\n已删除: oa_file_info {removed_rows} 行 | processing_logs {removed_logs} 行"
              + (f" | cleanup_candidates {removed_cleanup} 行" if args.include_cleanup else ""))
    except Exception as e:
        db.rollback()
        print(f"执行失败，已回滚: {e}", file=sys.stderr)
        sys.exit(1)
    finally:
        db.close()


if __name__ == "__main__":
    main()
