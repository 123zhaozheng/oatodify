# OA文档处理系统 Docker 部署指南

## 📋 系统架构

本系统采用微服务架构，包含以下组件：

- **FastAPI 后端**: REST API 服务 (端口: 8000)
- **Streamlit 前端**: Web 用户界面 (端口: 8501)  
- **Celery Worker**: 文档处理后台任务
- **Celery Beat**: 定时任务调度器
- **PostgreSQL**: 主数据库 (端口: 5432)
- **Redis**: 缓存和消息队列 (端口: 6379)
- **Nginx**: 反向代理 (端口: 80/443)
- **Flower**: Celery 监控界面 (端口: 5555)

## 🚀 快速开始

### 1. 环境准备

确保系统已安装：
- Docker 20.10+
- Docker Compose 2.0+

### 2. 配置环境变量

复制并编辑环境配置文件：
```bash
cp .env.example .env
```

编辑 `.env` 文件，配置必要的参数：
```bash
# 数据库配置
DATABASE_URL=postgresql://postgres:mypassword@postgres:5432/oa_docs

# S3存储配置
S3_ACCESS_KEY=your_s3_access_key
S3_SECRET_KEY=your_s3_secret_key
S3_BUCKET_NAME=your_bucket_name
S3_REGION=us-east-1
S3_ENDPOINT_URL=https://your-s3-endpoint.com

# OpenAI配置
OPENAI_API_KEY=your_openai_api_key
OPENAI_BASE_URL=https://api.openai.com/v1
OPENAI_MODEL_NAME=gpt-4

# Dify配置
DIFY_API_KEY=your_dify_api_key
DIFY_BASE_URL=https://api.dify.ai
DIFY_DATASET_ID=your_dataset_id

# Redis配置
REDIS_URL=redis://redis:6379/0

# 应用配置
SECRET_KEY=your-secret-key-change-this-in-production
DEBUG=false
```

### 3. 启动系统

使用 Docker Compose 启动完整系统：
```bash
# 启动所有服务
docker-compose up -d

# 查看服务状态
docker-compose ps

# 查看日志
docker-compose logs -f
```

### 4. 验证部署

访问以下地址验证服务：
- **API 文档**: http://localhost:8000/docs
- **前端界面**: http://localhost:8501
- **健康检查**: http://localhost:8000/health
- **Flower 监控**: http://localhost:5555

## 🔧 单独运行模式

### 构建镜像
```bash
docker build -t oa-document-processor .
```

### 运行特定服务

#### FastAPI 后端
```bash
docker run -d \
  --name oa-api \
  -p 8000:8000 \
  --env-file .env \
  -e DATABASE_URL="postgresql://host.docker.internal:5432/oa_docs" \
  -e REDIS_URL="redis://host.docker.internal:6379/0" \
  oa-document-processor fastapi
```

#### Streamlit 前端
```bash
docker run -d \
  --name oa-frontend \
  -p 8501:8501 \
  --env-file .env \
  -e DATABASE_URL="postgresql://host.docker.internal:5432/oa_docs" \
  oa-document-processor streamlit
```

#### Celery Worker
```bash
docker run -d \
  --name oa-worker \
  --env-file .env \
  -e DATABASE_URL="postgresql://host.docker.internal:5432/oa_docs" \
  -e REDIS_URL="redis://host.docker.internal:6379/0" \
  oa-document-processor celery-worker
```

#### Celery Beat
```bash
docker run -d \
  --name oa-beat \
  --env-file .env \
  -e DATABASE_URL="postgresql://host.docker.internal:5432/oa_docs" \
  -e REDIS_URL="redis://host.docker.internal:6379/0" \
  oa-document-processor celery-beat
```

## 📊 监控与维护

### 查看服务状态
```bash
# 查看所有服务
docker-compose ps

# 查看特定服务日志
docker-compose logs -f api
docker-compose logs -f worker
docker-compose logs -f frontend
```

### 扩展 Worker
```bash
# 扩展到 4 个 Worker 实例
docker-compose up -d --scale worker=4
```

### 重启服务
```bash
# 重启所有服务
docker-compose restart

# 重启特定服务
docker-compose restart api
docker-compose restart worker
```

### 更新服务
```bash
# 重新构建并启动
docker-compose build
docker-compose up -d
```

## 🛠️ 故障排除

### 常见问题

#### 1. 数据库连接失败
```bash
# 检查数据库容器状态
docker-compose logs postgres

# 检查网络连接
docker exec -it oa-api ping postgres
```

#### 2. Redis 连接失败
```bash
# 检查 Redis 容器状态
docker-compose logs redis

# 测试 Redis 连接
docker exec -it oa-api redis-cli -h redis ping
```

#### 3. 文件上传失败
检查 S3 配置和网络连接：
```bash
# 进入容器测试
docker exec -it oa-api bash
python -c "
from services.s3_service import s3_service
print('S3 connection test:', s3_service.test_connection())
"
```

#### 4. Worker 任务失败
```bash
# 查看 Worker 日志
docker-compose logs -f worker

# 查看 Flower 监控界面
# 访问 http://localhost:5555
```

### 性能优化

#### 1. 调整 Worker 数量
根据服务器性能调整：
```yaml
# docker-compose.yml
worker:
  deploy:
    replicas: 4  # 调整 Worker 数量
```

#### 2. 数据库性能优化
```bash
# 进入数据库容器
docker exec -it oa-postgres psql -U postgres -d oa_docs

# 查看数据库性能
SELECT * FROM pg_stat_activity;
SELECT * FROM pg_stat_user_tables;
```

#### 3. 内存和资源限制
```yaml
# docker-compose.yml
api:
  deploy:
    resources:
      limits:
        memory: 1G
        cpus: '1'
      reservations:
        memory: 512M
        cpus: '0.5'
```

## 🔒 安全配置

### 1. 环境变量安全
- 不要在代码中硬编码敏感信息
- 使用 Docker Secrets 或外部密钥管理
- 定期轮换 API 密钥

### 2. 网络安全
```yaml
# 限制网络访问
networks:
  oa-network:
    driver: bridge
    internal: true  # 仅内部网络
```

### 3. 容器安全
```dockerfile
# 使用非 root 用户运行
USER appuser

# 只读文件系统
read_only: true
```

## 📈 生产部署建议

### 1. 资源配置
- **CPU**: 最少 4 核心
- **内存**: 最少 8GB
- **存储**: SSD 推荐
- **网络**: 稳定的互联网连接

### 2. 高可用配置
```yaml
# 多个 API 实例
api:
  deploy:
    replicas: 3
    
# 多个 Worker 实例  
worker:
  deploy:
    replicas: 6
```

### 3. 备份策略
```bash
# 数据库备份
docker exec oa-postgres pg_dump -U postgres oa_docs > backup.sql

# Redis 备份
docker exec oa-redis redis-cli BGSAVE
```

### 4. 监控告警
- 集成 Prometheus + Grafana
- 配置日志聚合 (ELK Stack)
- 设置健康检查告警

## 📝 维护命令

```bash
# 清理无用的容器和镜像
docker system prune -a

# 查看系统资源使用
docker stats

# 导出/导入镜像
docker save oa-document-processor > oa-system.tar
docker load < oa-system.tar

# 数据库维护
docker exec -it oa-postgres psql -U postgres -d oa_docs -c "VACUUM ANALYZE;"
```

## 🆘 技术支持

如遇到问题，请检查：
1. Docker 和 Docker Compose 版本
2. 系统资源使用情况
3. 网络连接状态
4. 环境变量配置
5. 服务日志输出

更多详细信息请参考项目文档或联系技术支持团队。