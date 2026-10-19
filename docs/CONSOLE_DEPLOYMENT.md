# 中文工作台部署与使用

新版静态前端与现有 FastAPI 同源部署。打开 `http://宿主机:18000/` 即可进入，无需登录；无需运行 Node 构建，也不依赖 CDN。原 Streamlit 保留为可选 `legacy-ui` profile，仅供旧界面过渡使用。

## 1. 新部署与升级

先按 [NAS 与清理升级指南](NAS_CLEANUP_UPGRADE.md) 完成数据库、Redis、Dify、解析服务及 NAS 挂载配置。已有部署升级前备份数据库，暂停旧 Worker/Beat，再构建和运行迁移：

```bash
docker compose -f docker-compose.yml -f docker-compose.nas.yml build
docker compose -f docker-compose.yml -f docker-compose.nas.yml run --rm api migrate
docker compose -f docker-compose.yml -f docker-compose.nas.yml up -d api worker beat
```

新版会创建每日任务记录表。API、Worker、Beat 使用同一数据库，并共享 `runtime_config` 卷，挂载为 `/app/config`。`RUNTIME_CONFIG_PATH` 默认为 `/app/config/runtime.json`，同一部署各进程必须使用同一路径和共享文件内容。

API 启动不再等待 Redis。数据库初始化失败时，首页和基于共享文件的系统参数配置仍可访问；每日数据、知识库和分类映射等依赖数据库的接口会报告失败。`/health` 返回 `degraded` 和 `database_initialized:false`。修复数据库连接后运行迁移并重启 API；Worker/Beat 仍等待数据库与 Redis 可用后才启动。这里的健康标志表示启动初始化结果，当前依赖连接以页面连接检查为准。

若直接在宿主机运行：

```bash
export RUNTIME_CONFIG_PATH=/absolute/path/to/shared-config/runtime.json
uv run uvicorn main:app --host 0.0.0.0 --port 18000
```

Worker 和 Beat 也设置同一 `RUNTIME_CONFIG_PATH` 后按现有 Celery 命令启动。目录需要 API 用户可写、Worker/Beat 用户可读；容器默认同一运行用户。

原代理配置 `nginx.conf` 已将根页面和静态资源指向 API，新界面不需要 Streamlit WebSocket。静态资源短缓存，API及主HTML不缓存，避免升级后继续使用旧脚本。

## 2. 页面如何使用

- **总览 / 每日过程**：按北京时间选择日期，查看文件统计、处理趋势和实际任务记录；可暂停自动刷新。没有数据时显示空状态，接口失败时显示错误，系统连接状态来自实际接口。
- **文档处理**：可查全部或指定日期涉及的文件，按关键词、分类和状态筛选；打开详情查看逐步日志、模型分析、原文及附件，下载原文件或重新提交失败正文。
- **人工审核**：查看模型置信度、入库理由、目标知识库和正文，提交批准/拒绝及意见。
- **清理维护**：默认预览生成清理建议，查看原文依据后批准或拒绝；批准后单独执行，远端失败可重试。清理执行保留上一版服务端快照、索引可用性检查与审计。
- **系统配置**：编辑 NAS、DAT、解析、模型、Dify、清理及筛选参数；配置知识库及分类映射。保存提示生效范围。密钥不回显，留空保留，清除需要显式选择；不要将“空密码输入框”误认为没有保存密码。

## 3. 每日统计口径

日期按 `Asia/Shanghai`，接口时间戳附带时区。数据库原有无时区时间按项目 UTC 部署约定解释；若旧数据库保存的是本地北京时间而不是 UTC，升级前应确认并统一该约定，避免历史记录出现八小时偏差。

| 指标 | 含义 |
| --- | --- |
| 新增文件 | 所选北京时间日创建的 OA 文件记录 |
| 处理涉及文件 | 当日有处理开始时间或处理日志的正文文件去重计数 |
| 成功入库 / 失败 / 跳过 | 当日相应终态时间或处理日志对应的正文文件去重计数；重复尝试可能涉及多个结果 |
| 待人工审核 | 当前待审核正文积压快照，不是选定历史日期的快照 |
| 清理建议 | 所选日期新创建的清理建议 |
| 实际删除 | 所选日期成功执行的清理删除 |

文档日期筛选表示该日期同步、处理或日志触及的文件；不等于所有文件都在该日首次导入。批处理“成功”表示完成了子任务提交，单份文件的成功入库另有记录和文件状态。

升级后通过 Celery 发布和执行信号持久化任务记录，包括定时任务。此前未记录的历史运行不能从 Redis 或文件状态准确复原，页面会明确说明缺少旧运行记录；不制造历史成功任务。

## 4. 配置生效与保存

持久配置优先于启动时 `.env`/环境变量默认值。保存使用版本校验、文件锁和原子替换，不同人员同时保存时会提示版本冲突，需要刷新并重新确认修改。

NAS 路径映射、导入、模型、Dify、解析、清理和筛选热配置，在 API 后续请求以及 Worker 后续任务中读取；运行中的任务沿用开始时的配置。知识库/分类映射更新会发布共享修订版本，其他进程在下一次刷新时清缓存。

数据库地址、Redis地址和其他基础启动配置只保存为待重启项。执行：

```bash
docker compose -f docker-compose.yml -f docker-compose.nas.yml restart api worker beat
```

再查看配置页面及连接状态。修改数据库连接意味着新数据库需要已有表结构和数据，请由运维准备目标数据库；页面保存地址不会迁移数据库数据。修改 Redis 地址后所有进程需统一重启，避免发送端和执行端使用不同队列。

页面可配置容器中可见的 NAS 根路径和 OA 前缀；宿主机 NAS 挂载及 Docker 卷映射仍由运维完成。页面不执行宿主机挂载或 Docker 服务控制命令。

既有密钥只在服务端保存，浏览器GET不返回原值。无登录模式按用户要求沿用行内访问范围；浏览器跨来源写请求被拒绝，服务端内网调用可不带 Origin。审核人填写值只用于审计。

## 5. Chrome 109 与验证

前端为本地 HTML / CSS / JavaScript，使用系统中文字体与本地 SVG 图标。未采用 oklch、CSS nesting、:has、容器查询、Popover API、View Transitions 或需要新浏览器的框架运行时。

浏览器检查使用 Chromium `109.0.5414.46`（Playwright 1.29.2），18 项交互检查全部通过，包括日期/分页、正文详情、审批、清理确认、配置与密钥、并发冲突及办公屏/窄屏布局；没有页面脚本异常。这是 Chrome 109 对应的 Chromium 内核实测，不等同于每一台行内电脑、每个扩展程序和网络策略均已验证。

离线回归共 69 项通过，包含 NAS/清理回归、任务与日期统计、配置保存与脱敏、同源写保护、重复审批保护和数据库故障下配置页可访问。项目中执行：

```bash
uv run --with pytest --with httpx pytest -q
```

本次实际测试使用项目虚拟环境中的 `python -m pytest -q`，产生两条既有 SQLAlchemy/Pydantic 弃用提示，没有测试失败。

真实 NAS、行内 DeepSeek 网关、Dify 和 PostgreSQL 并发联调仍需在部署环境完成。离线测试使用隔离 SQLite 和模拟外部服务；界面预览数据仅来自隔离测试环境。

## 6. 需求与源码

用户故事及验收标准见 [前端需求文档](FRONTEND_REQUIREMENTS.md)。

- `web/`：新版静态前端。
- `api/console.py`、`services/operations.py`、`models_operations.py`：每日观测和持久任务记录。
- `api/console_config.py`、`services/runtime_config.py`：页面配置、密钥脱敏和业务映射配置。
- `main.py`：同源页面/接口入口。

本次没有推送远端仓库或对生产环境做更改。
