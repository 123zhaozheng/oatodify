# OA文档处理系统

一个智能化的OA文档下载、解密、分析和知识库集成系统。支持从S3存储下载文档，自动解密，AI分析文档价值，并集成到Dify知识库中。

## 🚀 功能特性

- **📥 文档下载**: 从S3兼容存储自动下载OA文档
- **🔐 文档解密**: 支持AES加密文档的自动解密
- **📄 格式支持**: 支持PDF、DOCX、DOC、TXT等多种文档格式
- **🤖 AI分析**: 使用OpenAI GPT模型智能分析文档价值和适用性
- **📚 知识库集成**: 自动将有价值文档集成到Dify知识库
- **👥 人工审核**: 提供Web界面进行人工审核和批准
- **📊 实时监控**: 完整的处理状态追踪和统计仪表板
- **⚙️ 灵活配置**: 支持自定义OpenAI API、S3存储等配置

## 🏗️ 系统架构

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Streamlit     │    │   FastAPI       │    │    Celery       │
│   Web界面       │    │   REST API      │    │   异步任务      │
└─────────────────┘    └─────────────────┘    └─────────────────┘
         │                       │                       │
         └───────────────────────┼───────────────────────┘
                                 │
         ┌─────────────────┬─────┴─────┬─────────────────┐
         │                 │           │                 │
┌─────────────────┐ ┌─────────────────┐ ┌─────────────────┐ ┌─────────────────┐
│   PostgreSQL    │ │      Redis      │ │   S3 Storage    │ │   OpenAI API    │
│     数据库      │ │   消息队列      │ │    文件存储     │ │   AI分析服务    │
└─────────────────┘ └─────────────────┘ └─────────────────┘ └─────────────────┘
                                                                      │
                                                           ┌─────────────────┐
                                                           │   Dify平台      │
                                                           │    知识库       │
                                                           └─────────────────┘
```

## 📋 系统要求

### 基础环境
- **Python**: >= 3.11
- **操作系统**: Linux, macOS, Windows
- **内存**: >= 4GB RAM
- **存储**: >= 10GB 可用空间

### 外部依赖
- **PostgreSQL**: >= 12.0 (数据库)
- **Redis**: >= 6.0 (消息队列)
- **S3兼容存储**: AWS S3 或其他兼容服务
- **OpenAI API**: 或兼容的AI服务
- **Dify平台**: 知识库管理服务

## 🛠️ 安装部署

### 1. 克隆项目

```bash
git clone <repository-url>
cd ReplChat
```

### 2. 安装依赖

使用 UV 包管理器（推荐）：
```bash
# 安装 UV（如果未安装）
curl -LsSf https://astral.sh/uv/install.sh | sh

# 安装项目依赖
uv sync
```

或使用 pip：
```bash
pip install -r requirements.txt
```

### 3. 配置环境变量

创建 `.env` 文件：

```bash
cp .env.example .env
```

编辑 `.env` 文件，配置以下环境变量：

```env
# 数据库配置
DATABASE_URL=postgresql://user:password@localhost:5432/oa_docs

# S3存储配置
S3_ACCESS_KEY=your-s3-access-key
S3_SECRET_KEY=your-s3-secret-key
S3_BUCKET_NAME=oa-documents
S3_REGION=us-east-1
S3_ENDPOINT_URL=https://your-s3-endpoint.com  # 可选，自定义S3服务

# OpenAI配置
OPENAI_API_KEY=your-openai-api-key
OPENAI_BASE_URL=https://api.openai.com/v1  # 可选，自定义API地址
OPENAI_MODEL_NAME=gpt-4  # 可选，默认gpt-4

# Dify配置
DIFY_API_KEY=your-dify-api-key
DIFY_BASE_URL=https://api.dify.ai
DIFY_DATASET_ID=your-dataset-id

# Redis配置
REDIS_URL=redis://localhost:6379/0

# 应用配置
SECRET_KEY=your-secret-key-here
DEBUG=false
```

### 4. 初始化数据库

```bash
# 启动PostgreSQL服务
sudo systemctl start postgresql

# 创建数据库
createdb oa_docs

# 初始化数据库表（会在首次启动时自动执行）
```

### 5. 启动服务

#### 方法一：使用脚本启动（推荐）

创建启动脚本 `start.sh`：

```bash
#!/bin/bash

# 启动Redis
redis-server --daemonize yes

# 启动Celery Worker
celery -A tasks.document_processor worker --loglevel=info --detach

# 启动FastAPI服务
uvicorn main:app --host 0.0.0.0 --port 8000 --reload &

# 启动Streamlit Web界面
streamlit run app.py --server.port 5000 --server.address 0.0.0.0

echo "所有服务已启动:"
echo "- FastAPI API: http://localhost:8000"
echo "- Streamlit Web界面: http://localhost:5000"
echo "- API文档: http://localhost:8000/docs"
```

运行启动脚本：
```bash
chmod +x start.sh
./start.sh
```

#### 方法二：分别启动各服务

**终端1 - 启动Celery Worker**：
```bash
celery -A tasks.document_processor worker --loglevel=info
```

**终端2 - 启动FastAPI API服务**：
```bash
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

**终端3 - 启动Streamlit Web界面**：
```bash
streamlit run app.py
```

### 6. 验证安装

访问以下地址验证服务是否正常：

- **Web管理界面**: http://localhost:5000
- **API服务**: http://localhost:8000
- **API文档**: http://localhost:8000/docs
- **健康检查**: http://localhost:8000/health

## 🔧 配置说明

### OpenAI 配置

系统支持多种OpenAI API配置方式：

1. **官方OpenAI API**:
   ```env
   OPENAI_API_KEY=sk-your-openai-api-key
   OPENAI_MODEL_NAME=gpt-4
   # OPENAI_BASE_URL留空
   ```

2. **Azure OpenAI Service**:
   ```env
   OPENAI_API_KEY=your-azure-api-key
   OPENAI_BASE_URL=https://your-resource.openai.azure.com/openai/deployments/your-deployment/chat/completions?api-version=2024-02-15-preview
   OPENAI_MODEL_NAME=gpt-4
   ```

3. **自定义API服务**:
   ```env
   OPENAI_API_KEY=your-custom-api-key
   OPENAI_BASE_URL=https://your-custom-api.com/v1
   OPENAI_MODEL_NAME=your-model-name
   ```

详细配置说明请参考 [OPENAI_CONFIG.md](OPENAI_CONFIG.md)

### S3 存储配置

支持AWS S3和其他S3兼容存储服务：

```env
# AWS S3
S3_ACCESS_KEY=AKIAIOSFODNN7EXAMPLE
S3_SECRET_KEY=wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY
S3_BUCKET_NAME=my-oa-documents
S3_REGION=us-west-2

# 自定义S3服务（如MinIO）
S3_ENDPOINT_URL=https://minio.example.com
```

## 📖 使用指南

### 1. 访问Web界面

打开浏览器访问 http://localhost:5000

### 2. 系统功能

- **📊 仪表板**: 查看文档处理统计和状态
- **👥 人工审核**: 审核待处理文档
- **⚙️ 系统设置**: 配置各项系统参数

### 3. API使用

系统提供RESTful API接口：

```bash
# 获取文档列表
curl http://localhost:8000/api/v1/documents

# 提交文档处理任务
curl -X POST http://localhost:8000/api/v1/documents/process \
  -H "Content-Type: application/json" \
  -d '{"file_id": "your-file-id"}'

# 查看处理状态
curl http://localhost:8000/api/v1/documents/{file_id}/status
```

完整API文档：http://localhost:8000/docs

### 4. 文档处理流程

1. **文档上传**: 文档上传到S3存储
2. **自动检测**: 系统检测新文档
3. **下载解密**: 自动下载并解密文档
4. **内容解析**: 提取文档文本内容
5. **AI分析**: 使用AI评估文档价值
6. **人工审核**: 可选的人工审核步骤
7. **知识库集成**: 将通过审核的文档加入Dify知识库

## 🐳 Docker部署

### 使用Docker Compose

创建 `docker-compose.yml`：

```yaml
version: '3.8'

services:
  app:
    build: .
    ports:
      - "8000:8000"
      - "5000:5000"
    environment:
      - DATABASE_URL=postgresql://postgres:password@db:5432/oa_docs
      - REDIS_URL=redis://redis:6379/0
    depends_on:
      - db
      - redis
    volumes:
      - ./logs:/app/logs

  db:
    image: postgres:15
    environment:
      - POSTGRES_DB=oa_docs
      - POSTGRES_USER=postgres
      - POSTGRES_PASSWORD=password
    volumes:
      - postgres_data:/var/lib/postgresql/data
    ports:
      - "5432:5432"

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"

  celery:
    build: .
    command: celery -A tasks.document_processor worker --loglevel=info
    environment:
      - DATABASE_URL=postgresql://postgres:password@db:5432/oa_docs
      - REDIS_URL=redis://redis:6379/0
    depends_on:
      - db
      - redis

volumes:
  postgres_data:
```

启动服务：
```bash
docker-compose up -d
```

## 🔍 监控和日志

### 日志文件

- **应用日志**: `logs/app.log`
- **Celery日志**: `logs/celery.log`
- **错误日志**: `logs/error.log`

### 监控指标

通过Web界面查看：
- 文档处理统计
- 系统健康状态
- AI分析成功率
- 存储使用情况

### 性能监控

```bash
# 查看Celery任务状态
celery -A tasks.document_processor inspect active

# 查看队列状态
celery -A tasks.document_processor inspect reserved

# 监控系统资源
htop
```

## 🛡️ 安全考虑

1. **API密钥安全**: 使用环境变量存储敏感信息
2. **网络安全**: 配置防火墙和VPN
3. **数据加密**: 敏感数据加密存储
4. **访问控制**: 配置适当的用户权限
5. **日志安全**: 避免在日志中记录敏感信息

## 🔧 故障排除

### 常见问题

1. **数据库连接失败**
   ```bash
   # 检查PostgreSQL服务
   sudo systemctl status postgresql
   
   # 测试数据库连接
   psql -h localhost -U your_user -d oa_docs
   ```

2. **Redis连接失败**
   ```bash
   # 检查Redis服务
   redis-cli ping
   
   # 查看Redis日志
   sudo journalctl -u redis
   ```

3. **OpenAI API错误**
   ```bash
   # 测试API连接
   curl -X POST "$OPENAI_BASE_URL/chat/completions" \
     -H "Authorization: Bearer $OPENAI_API_KEY" \
     -H "Content-Type: application/json" \
     -d '{"model": "'$OPENAI_MODEL_NAME'", "messages": [{"role": "user", "content": "test"}], "max_tokens": 10}'
   ```

4. **文件权限问题**
   ```bash
   # 修复日志目录权限
   chmod -R 755 logs/
   chown -R $USER:$USER logs/
   ```

### 调试模式

启用调试模式：
```env
DEBUG=true
```

查看详细日志：
```bash
tail -f logs/app.log
```

## 📚 开发指南

### 项目结构

```
ReplChat/
├── api/                    # API路由
├── services/              # 业务服务
│   ├── ai_analyzer.py    # AI分析服务
│   ├── s3_service.py     # S3存储服务
│   └── dify_service.py   # Dify集成服务
├── tasks/                # Celery异步任务
├── templates/            # Web界面模板
├── utils/                # 工具函数
├── config.py             # 配置管理
├── models.py             # 数据模型
├── database.py           # 数据库连接
├── main.py               # FastAPI应用
└── app.py                # Streamlit应用
```

### 添加新功能

1. **新增API接口**: 在 `api/routes.py` 中添加路由
2. **新增服务**: 在 `services/` 目录下创建服务文件
3. **新增任务**: 在 `tasks/` 目录下添加异步任务
4. **新增页面**: 在 `templates/` 目录下创建页面模板

### 代码规范

- 使用Python类型提示
- 遵循PEP8代码规范
- 添加适当的文档字符串
- 编写单元测试

## 🤝 贡献指南

1. Fork 项目
2. 创建功能分支 (`git checkout -b feature/AmazingFeature`)
3. 提交更改 (`git commit -m 'Add some AmazingFeature'`)
4. 推送到分支 (`git push origin feature/AmazingFeature`)
5. 创建 Pull Request

## 📄 许可证

本项目采用 MIT 许可证 - 详见 [LICENSE](LICENSE) 文件

## 📞 支持

如果遇到问题或需要帮助：

1. 查看 [故障排除](#🔧-故障排除) 部分
2. 检查 [Issues](https://github.com/your-repo/issues) 页面
3. 创建新的 Issue 描述问题
4. 联系项目维护者

---

**🚀 快速开始**: 
1. 配置环境变量 → 2. 启动服务 → 3. 访问 http://localhost:5000 → 4. 开始使用！ 