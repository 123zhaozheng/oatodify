"""
数据库迁移脚本：导入 oa_file_info 数据
执行日期：2025-09-25
描述：读取 oa_file_info.sql 并批量插入到 PostgreSQL 中
"""

import logging
import os
import re
import sys
from typing import Iterator

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from database import engine

# 配置日志输出
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

DEFAULT_SQL_FILENAME = "oa_file_info.sql"
DEFAULT_BATCH_SIZE = 500


def split_sql_statements(sql_text: str) -> Iterator[str]:
    """按语句拆分 SQL 文本，保留字符串和美元引用中的分号"""
    statement_chars = []
    in_single_quote = False
    in_double_quote = False
    dollar_tag = None
    length = len(sql_text)
    i = 0

    while i < length:
        ch = sql_text[i]
        next_char = sql_text[i + 1] if i + 1 < length else ""

        if ch == "\r":
            i += 1
            continue

        if not in_single_quote and not in_double_quote and dollar_tag is None:
            if ch == "-" and next_char == "-":
                i += 2
                while i < length and sql_text[i] not in "\n":
                    i += 1
                statement_chars.append("\n")
                continue
            if ch == "/" and next_char == "*":
                i += 2
                depth = 1
                while i < length and depth > 0:
                    if sql_text[i] == "/" and i + 1 < length and sql_text[i + 1] == "*":
                        depth += 1
                        i += 2
                        continue
                    if sql_text[i] == "*" and i + 1 < length and sql_text[i + 1] == "/":
                        depth -= 1
                        i += 2
                        continue
                    i += 1
                statement_chars.append("\n")
                continue
            if ch == "$":
                match = re.match(r"\$[A-Za-z0-9_]*\$", sql_text[i:])
                if match:
                    token = match.group(0)
                    statement_chars.append(token)
                    i += len(token)
                    if dollar_tag is None:
                        dollar_tag = token
                    elif token == dollar_tag:
                        dollar_tag = None
                    continue

        if dollar_tag is None and ch == "'" and not in_double_quote:
            if in_single_quote:
                if next_char == "'":
                    statement_chars.extend([ch, next_char])
                    i += 2
                    continue
                in_single_quote = False
            else:
                in_single_quote = True
            statement_chars.append(ch)
            i += 1
            continue

        if dollar_tag is None and ch == '"' and not in_single_quote:
            in_double_quote = not in_double_quote
            statement_chars.append(ch)
            i += 1
            continue

        if ch == ";" and not in_single_quote and not in_double_quote and dollar_tag is None:
            statement = "".join(statement_chars).strip()
            if statement:
                yield statement
            statement_chars = []
            i += 1
            continue

        statement_chars.append(ch)
        i += 1

    statement = "".join(statement_chars).strip()
    if statement:
        yield statement


def iter_statements_from_file(sql_file: str) -> Iterator[str]:
    with open(sql_file, "r", encoding="utf-8") as f:
        content = f.read()
    yield from split_sql_statements(content)


def truncate_table(restart_identity: bool = True) -> None:
    if restart_identity:
        sql = "TRUNCATE TABLE oa_file_info RESTART IDENTITY CASCADE"
    else:
        sql = "TRUNCATE TABLE oa_file_info CASCADE"
    with engine.begin() as conn:
        conn.execute(text(sql))


def execute_sql_from_file(sql_file: str, truncate: bool = False, batch_size: int = DEFAULT_BATCH_SIZE) -> int:
    if not os.path.exists(sql_file):
        raise FileNotFoundError(f"SQL 文件不存在: {sql_file}")

    if truncate:
        logger.info("先清空表 oa_file_info ...")
        truncate_table(restart_identity=True)

    logger.info("连接数据库: %s", engine.url)
    connection = engine.raw_connection()
    cursor = connection.cursor()
    executed = 0

    try:
        for executed, statement in enumerate(iter_statements_from_file(sql_file), start=1):
            cursor.execute(statement)
            if executed % batch_size == 0:
                connection.commit()
                logger.info("已执行 %s 条语句", executed)

        connection.commit()
        logger.info("全部语句执行完成，共 %s 条", executed)
        return executed
    except Exception as exc:
        connection.rollback()
        logger.error("执行 SQL 失败: %s", exc)
        raise
    finally:
        cursor.close()
        connection.close()


def verify_row_count() -> int:
    with engine.connect() as conn:
        result = conn.execute(text("SELECT COUNT(*) FROM oa_file_info"))
        row_count = result.scalar_one()
    logger.info("当前 oa_file_info 记录总数: %s", row_count)
    return row_count


def run_import(sql_file: str, truncate: bool, batch_size: int) -> None:
    try:
        total_statements = execute_sql_from_file(sql_file, truncate=truncate, batch_size=batch_size)
        row_count = verify_row_count()
        logger.info("导入完成: %s 条语句，表内记录 %s 条", total_statements, row_count)
    except FileNotFoundError:
        logger.error("找不到指定的 SQL 文件: %s", sql_file)
        sys.exit(1)
    except SQLAlchemyError as exc:
        logger.error("数据库错误: %s", exc)
        sys.exit(2)
    except Exception as exc:
        logger.error("未知错误: %s", exc)
        sys.exit(3)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="导入 oa_file_info 表数据")
    subparsers = parser.add_subparsers(dest="action", required=True)

    import_parser = subparsers.add_parser("import", help="执行 SQL 文件导入")
    import_parser.add_argument("--file", "-f", default=DEFAULT_SQL_FILENAME, help="要导入的 SQL 文件路径")
    import_parser.add_argument("--truncate", action="store_true", help="导入前清空 oa_file_info 表")
    import_parser.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE, help="每多少条语句提交一次事务")

    rollback_parser = subparsers.add_parser("rollback", help="清空 oa_file_info 表")
    rollback_parser.add_argument("--keep-identity", action="store_true", help="回滚时保留自增序列")

    args = parser.parse_args()

    if args.action == "import":
        run_import(sql_file=args.file, truncate=args.truncate, batch_size=max(1, args.batch_size))
    elif args.action == "rollback":
        try:
            truncate_table(restart_identity=not args.keep_identity)
            logger.info("✓ 已回滚 oa_file_info 表")
        except SQLAlchemyError as exc:
            logger.error("回滚失败: %s", exc)
            sys.exit(4)
