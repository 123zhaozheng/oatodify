# OA 文档处理系统

将 OA 文档从挂载 NAS 读取、解析和分析后送入 Dify，并持续检查历史文档的有效期、重复正文及制度替代关系。保留旧 S3 兼容方式，支持 OpenAI Chat Completions 兼容的行内 DeepSeek 网关。

新版提供无需登录的中文工作台：每日运行过程、文档详情与失败重试、人工入库审核、清理预览/审核/执行，以及页面配置。界面参考白色侧栏、浅灰卡片、黑色操作按钮和蓝色趋势图，使用本地静态资源；已在 Chromium 109 内核实际验证。

## 文档

- [前端用户故事与需求文档](docs/FRONTEND_REQUIREMENTS.md)：用户目标、页面、接口与验收标准。
- [中文工作台部署说明](docs/CONSOLE_DEPLOYMENT.md)：升级、配置生效范围、每日统计口径及验证结果。
- [NAS 与历史清理升级指南](docs/NAS_CLEANUP_UPGRADE.md)：路径映射、DAT 字段、旧库迁移和安全清理。

## 快速部署

需要 Python 3.11 及以上、PostgreSQL、Redis、文档解析服务、Dify 和行内模型网关。宿主机先挂载 NAS；服务只读 OA 原件，清理删除仅作用于 Dify 知识库副本。

```bash
git clone https://github.com/123zhaozheng/oatodify.git
cd oatodify
# 如使用交付源码包，可直接进入解压后的 oatodify 目录。
cp .env.example .env
```

填写 `.env` 的数据库、Redis、解析、模型和 Dify 配置，以及 `NAS_HOST_PATH`、`DAT_HOST_PATH` 和路径映射。应用的 Compose 服务可连接行内已有数据库/Redis；如使用项目附带服务，应另行启动并统一凭证。原解析服务镜像和源码挂载为部署占位配置，需替换为实际服务。

已有部署先备份数据库并暂停旧 Worker/Beat，随后运行：

```bash
docker compose -f docker-compose.yml -f docker-compose.nas.yml build
docker compose -f docker-compose.yml -f docker-compose.nas.yml run --rm api migrate
docker compose -f docker-compose.yml -f docker-compose.nas.yml up -d api worker beat
```

访问 `http://宿主机:18000/`；API 文档为 `/docs`。API 同时提供前端，无需 Node 构建。旧 Streamlit 可通过 `--profile legacy-ui` 启动 `frontend` 服务，端口 8501。

API、Worker 和 Beat 共享 `runtime_config` 卷。配置页支持 NAS、导入、解析、模型、Dify、清理、筛选、知识库及分类映射；热配置在后续请求/任务读取，数据库与 Redis 等启动项保存后需统一重启。密钥不回显，留空保留，显式操作才能清除。

数据库/Redis异常时，API首页和文件配置页仍可打开；涉及数据库的功能如实报告失败。修复后运行迁移并重启服务。完整升级步骤及旧文档的数据集绑定回填请阅读上面的两份部署指南。

## 主要处理流程

1. DAT 导入 OA 文件信息，新增 `filerealpath` 绝对路径字段。
2. 在允许的 NAS 根目录中只读读取；按配置决定是否解密。
3. 解析全文，模型分析价值和业务分类，自动或人工审核后送入 Dify。
4. 每日扫描历史文件，保存过期、完全重复及制度替代建议。
5. 审核后单独执行清理，执行前复核原文快照、数据集及保留文档索引状态；保留审计并支持失败重试。

默认清理只生成建议，不自动删除。页面扫描始终为预览；模型结论必须通过原文引用、置信度及程序规则核验。NAS 读取失败不会掩盖为成功，挂载目录存在也不等于远端 NAS 在线。

## 本地开发与验证

```bash
uv sync
export RUNTIME_CONFIG_PATH=/absolute/path/to/shared-config/runtime.json
uv run uvicorn main:app --host 0.0.0.0 --port 18000
```

Worker、Beat 使用相同配置路径和 NAS 可见路径，按现有 Celery 入口启动。运行测试：

```bash
uv run --with pytest --with httpx pytest -q
node --check web/app.js
```

本次 69 项离线回归和真实 Chromium 109.0.5414.46 的 18 项交互检查全部通过。行内 NAS、DeepSeek 网关、Dify、PostgreSQL 并发及真实 Docker 部署仍需在目标环境联调。

## 代码位置

| 目录/文件 | 职责 |
| --- | --- |
| `web/` | 中文静态工作台 |
| `api/` | 文件、清理、每日过程与配置接口 |
| `services/file_storage.py` | NAS 读取与 S3 兼容 |
| `services/cleanup_service.py` | 清理建议、原文复核、执行及审计 |
| `services/operations.py` | 每日统计和持久任务记录 |
| `services/runtime_config.py` | 共享配置、脱敏、版本校验和热刷新 |
| `tasks/document_processor.py` | Celery 处理、导入及定时扫描 |
| `schema_migration.py` | 幂等数据库升级 |
| `templates/`、`app.py` | 旧 Streamlit 界面 |
| `tests/unit/` | 离线回归测试 |
