-- =============================================================================
-- OA文档处理系统数据库初始化脚本
-- 在 PostgreSQL 容器启动时自动执行
-- =============================================================================

-- 创建数据库（如果不存在）
-- SELECT 'CREATE DATABASE oa_docs' WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'oa_docs')\gexec

-- 连接到数据库
\c oa_docs;

-- 创建扩展
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";

-- 创建索引提升性能
-- 这些索引将在应用启动时通过 SQLAlchemy 创建，这里只是预留

-- 插入初始配置数据（如果需要）
-- INSERT INTO ... ON CONFLICT DO NOTHING;

-- 创建函数和触发器（如果需要）

-- 设置数据库参数优化
ALTER SYSTEM SET shared_preload_libraries = 'pg_stat_statements';
ALTER SYSTEM SET log_statement = 'all';
ALTER SYSTEM SET log_min_duration_statement = 1000;

-- 重载配置
SELECT pg_reload_conf();

-- 输出初始化完成信息
\echo '✅ OA文档处理系统数据库初始化完成'