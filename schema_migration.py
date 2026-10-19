"""旧库的幂等增量迁移；不修改已有状态枚举，不清空任何表。"""
from sqlalchemy import inspect, text
from models import Base
import models_operations  # 注册独立任务记录模型，CLI 迁移同样创建其表。


def migrate_schema(engine):
    with engine.begin() as conn:
        # API / Worker 同时启动时串行执行 DDL。
        if conn.dialect.name == "postgresql":
            conn.execute(text("SELECT pg_advisory_xact_lock(71425019)"))
        inspector = inspect(conn)
        if inspector.has_table("oa_file_info"):
            existing = {c["name"] for c in inspector.get_columns("oa_file_info")}
            for column in Base.metadata.tables["oa_file_info"].columns:
                if column.name not in existing:
                    type_sql = column.type.compile(dialect=conn.dialect)
                    conn.execute(text(f'ALTER TABLE oa_file_info ADD COLUMN "{column.name}" {type_sql}'))
        Base.metadata.create_all(bind=conn)
        for index in Base.metadata.tables["oa_file_info"].indexes:
            index.create(bind=conn, checkfirst=True)


if __name__ == "__main__":
    from database import engine
    migrate_schema(engine)
