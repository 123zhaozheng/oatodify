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

-- 创建知识库信息表
CREATE TABLE IF NOT EXISTS knowledge_bases (
    id SERIAL PRIMARY KEY,
    name VARCHAR(200) NOT NULL COMMENT '知识库名称',
    description TEXT COMMENT '知识库描述',
    dify_dataset_id VARCHAR(100) NOT NULL UNIQUE COMMENT 'Dify数据集ID',
    
    -- 配置信息
    api_key VARCHAR(500) COMMENT '专用API密钥',
    base_url VARCHAR(500) COMMENT '专用API地址',
    
    -- 状态信息
    status VARCHAR(20) DEFAULT 'active' COMMENT '知识库状态',
    document_count INTEGER DEFAULT 0 COMMENT '文档数量',
    last_sync_at TIMESTAMP COMMENT '最后同步时间',
    
    -- 时间戳
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    
    INDEX idx_status (status),
    INDEX idx_dify_dataset_id (dify_dataset_id)
);

-- 创建文档分类与知识库关系表
CREATE TABLE IF NOT EXISTS document_category_mappings (
    id SERIAL PRIMARY KEY,
    
    -- 关联信息
    knowledge_base_id INTEGER NOT NULL COMMENT '知识库ID',
    business_category VARCHAR(50) NOT NULL COMMENT '业务分类',
    
    -- AI处理配置
    ai_prompt_template TEXT COMMENT 'AI提示词模板',
    ai_output_schema TEXT COMMENT 'AI输出JSON格式定义',
    processing_priority INTEGER DEFAULT 5 COMMENT '处理优先级',
    
    -- 质量控制
    min_confidence_score INTEGER DEFAULT 70 COMMENT '最低置信度要求',
    auto_approve_threshold INTEGER DEFAULT 90 COMMENT '自动审批阈值',
    
    -- 状态
    is_active BOOLEAN DEFAULT TRUE COMMENT '是否启用',
    
    -- 时间戳
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    
    FOREIGN KEY (knowledge_base_id) REFERENCES knowledge_bases(id) ON DELETE CASCADE,
    INDEX idx_category (business_category),
    INDEX idx_kb_category (knowledge_base_id, business_category),
    INDEX idx_active (is_active),
    UNIQUE KEY uk_kb_category (knowledge_base_id, business_category)
);

-- 为现有的oa_file_info表添加目标知识库字段
ALTER TABLE oa_file_info 
ADD COLUMN target_knowledge_base_id INTEGER COMMENT '目标知识库ID',
ADD FOREIGN KEY (target_knowledge_base_id) REFERENCES knowledge_bases(id) ON DELETE SET NULL;

-- 插入默认知识库配置
INSERT INTO knowledge_bases (name, description, dify_dataset_id, status) 
VALUES ('默认知识库', '系统默认知识库', 'default-dataset-id', 'active')
ON DUPLICATE KEY UPDATE name = VALUES(name);

-- 插入默认的文档分类映射(假设默认知识库ID为1)
INSERT INTO document_category_mappings (knowledge_base_id, business_category, is_active) VALUES
(1, 'headquarters_issue', TRUE),
(1, 'retail_announcement', TRUE),
(1, 'publication_release', TRUE),
(1, 'branch_issue', TRUE),
(1, 'branch_receive', TRUE),
(1, 'public_standard', TRUE),
(1, 'headquarters_receive', TRUE),
(1, 'corporate_announcement', TRUE)
ON DUPLICATE KEY UPDATE is_active = VALUES(is_active);