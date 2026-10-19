# NAS 迁移与历史文档清理升级

本次修改基于仓库提交 `b3dcbbf`。保留 FastAPI、Streamlit、Celery、数据库和 Dify 集成方式。

后续已加入无需登录的中文静态工作台，入口为 `http://宿主机:18000/`；新版部署与页面配置请结合 [中文工作台部署说明](CONSOLE_DEPLOYMENT.md)。旧 Streamlit 仅作为可选过渡界面。

## 已完成的修改

| 环节 | 新行为 |
| --- | --- |
| 文件来源 | 默认读取 `filerealpath` 指向的 NAS 文件；自动处理、审核、下载接口和清理复核共用 `FileStorage` |
| 迁移兼容 | `STORAGE_BACKEND=auto` 时，有 NAS 路径即读取 NAS；只有没有路径才读取旧 S3，不在 NAS 读取失败时回退 |
| 解密 | NAS 默认是明文，保留旧 `asecode` 时也不自动解密；确实仍加密时设置 `NAS_FILES_ENCRYPTED=true` |
| 历史扫描 | 每种清理分别记录检查时间，从未检查及最久未检查的优先，单次 limit 不再永久遮蔽老文件 |
| 过期判断 | 覆盖所有分类，包括总行发文；模型提取全文失效日期、逐字原文引用、置信度；程序核对引用和日期 |
| 版本替换 | 检查明确的全面替代关系和生效日期，校验模型选择的 ID 在候选集合内，始终需要审核 |
| 完全重复 | 同数据集、同业务分类、完整解析正文 SHA256 相同才建议去重，不按同名或上传时间直接删除 |
| 执行保护 | 删除前重新核对文档身份及正文快照；保留的文档必须在 Dify 完成索引、已启用且未归档 |
| 审计与重试 | 建议、原 Dify ID、数据集、依据、审核人、执行次数和错误持久保存；远端失败保留本地 ID，可重试 |
| 前端 | 原来“勾选预览仍删除”的行为已修复，新增清理审核与审计页 |
| 导入与任务 | DAT 可补入 NAS 路径，保持已完成/跳过状态；修复 DAT 队列路由和 Worker 监听，自动处理以条件更新防重复投递 |

删除只作用于 **Dify 知识库副本**。NAS 始终只读，不删除 OA 原件。数据库原文件记录及完整解析正文仍保留。

## 原逻辑的主要问题

1. 按处理完成时间倒序再 `limit`，每次容易重复看新文件，最老文件一直不被检查。
2. 非总行发文才检查有效期，会遗漏总行文件自身明确的失效日期。
3. 原有效期比较将日期转成当天零点，会在有效期最后一天提前删除；现在按北京时间日期比较，次日才算过期。
4. 模型只看前 400/600 字，遗漏末尾的生效和废止条款，也未核验引用、置信度和返回 ID。
5. 同文件名去重未按分类及数据集隔离，上传时间并不代表制度版本时间。
6. 删除时重新推导分类映射，映射改变后可能定位到错误知识库。
7. 上传请求成功即算 COMPLETED，并不保证新文档已经完成索引。
8. 入库前筛选还要求旧 S3 tokenkey，并会直接删除同名旧文件；现在允许 NAS 路径，筛选器不再删除文档。

## NAS 部署

### 1. 配置路径映射

复制 `.env.example` 为 `.env`，将数据库、Redis、Dify、解析服务和行内模型配置替换为实际值。

推荐部署：宿主机把 NAS 挂载到 `/mnt/bank-oa`，容器内部统一使用 `/mnt/oa`。

```dotenv
STORAGE_BACKEND=nas
NAS_HOST_PATH=/mnt/bank-oa
NAS_ROOT=/mnt/oa
NAS_PATH_PREFIX=/oa/files
NAS_FILES_ENCRYPTED=false
DAT_HOST_PATH=/mnt/oa-dat
DAT_IMPORT_DIRECTORY=/data/dat_files
DAT_FILEREALPATH_INDEX=11
```

此时 OA 字段 `/oa/files/2026/制度.pdf` 会读取宿主机 `/mnt/bank-oa/2026/制度.pdf`，对应容器 `/mnt/oa/2026/制度.pdf`。

如果 OA 提供的绝对路径已经等于服务运行环境中的路径，`NAS_PATH_PREFIX` 留空，将 `NAS_ROOT` 设为其共同根目录，并自行调整 Compose 挂载目标使路径一致。裸机部署的 `NAS_ROOT` 直接填宿主机的挂载目录。

路径必须是绝对路径。程序拒绝 `..`、根目录以外的路径、越界符号链接、目录、空文件及超出 `MAX_FILE_SIZE` 的文件。宿主机 NAS 挂载目录应由运维管理，服务只读访问。

### 2. DAT 字段约定

默认维持原有 11 列，追加第 12 列：

```text
[跳过列], imagefileid, business_category, is_zw, fj_imagefileid,
imagefilename, imagefiletype, is_zip, filesize, asecode, tokenkey, filerealpath
```

实际分隔符仍为 ASCII 1（`\x01`）。新增列的位置若不同，设置 `DAT_FILEREALPATH_INDEX`，索引从 0 开始。旧 11 列数据仍可导入；NAS 模式处理没有路径的记录会明确失败。

若数据组直接写数据库，则向 `oa_file_info.filerealpath` 写入完整绝对路径。字段最终名称如果不同，需要调整该字段或在数据接口中做映射。

迁移期间，即使 `DAT_IMPORT_UPDATE_EXISTING=false`，新 DAT 中的非空 NAS 路径也会补入同 ID 的旧记录，但不会重置处理状态或重复上传已入库文件。首次迁移需提供包含历史记录的新路径数据，不要只提供当天新增记录。

### 3. 升级顺序

先备份数据库，暂停原 Worker 和 Beat，完成宿主机 NAS 挂载，确认目录真实存在、可读及挂载正常：

```bash
mountpoint /mnt/bank-oa
ls /mnt/bank-oa
```

然后构建镜像并升级表结构：

```bash
docker compose -f docker-compose.yml -f docker-compose.nas.yml build
docker compose -f docker-compose.yml -f docker-compose.nas.yml run --rm api migrate
```

迁移只增加缺少的字段和 `cleanup_candidates` 表，可重复执行，不清空旧数据。启动的数据库检查也会执行幂等迁移；PostgreSQL 使用事务 advisory lock 避免多容器同时执行 DDL。

为已入库旧记录回填实际数据集绑定：

```bash
docker compose -f docker-compose.yml -f docker-compose.nas.yml run --rm --entrypoint python api backfill_bindings.py --limit 10000
```

回填会通过 Dify 文档详情接口确认文档 ID 确实属于所选数据集，再写入绑定。默认尝试当前分类映射。如果映射已经改变，先恢复/登记旧知识库配置，再明确指定旧数据集：

```bash
docker compose -f docker-compose.yml -f docker-compose.nas.yml run --rm --entrypoint python api backfill_bindings.py --dataset-id ACTUAL_OLD_DATASET_ID --limit 10000
```

无法确认的记录会计入 `unresolved`，保持未绑定，不能删除。不要用猜测的数据集 ID 批量填库。

启动服务：

```bash
docker compose -f docker-compose.yml -f docker-compose.nas.yml up -d api worker beat
```

API 和 Worker 都必须挂载 NAS；只挂到宿主机或只挂 API 不能保证后台任务读取。NAS override 禁止自动创建不存在的宿主机源目录。现有 `document-parser` 镜像及其源码挂载路径沿用原项目，部署前替换为行内实际配置。本次没有执行真实 Docker 镜像构建。

数据库和 Redis 若使用现有服务，`.env` 填行内地址；若使用 Compose 中附带的服务，另行启动对应服务并统一凭证。

## 行内 DeepSeek 接入

现有调用已使用 OpenAI SDK 的 Chat Completions 协议。只要行内网关兼容此协议，配置：

```dotenv
OPENAI_BASE_URL=http://YOUR_INTERNAL_GATEWAY/v1
OPENAI_API_KEY=YOUR_INTERNAL_API_KEY
OPENAI_MODEL_NAME=YOUR_DEPLOYED_MODEL_ID
AI_JSON_OUTPUT_METHOD=response_format
AI_REQUEST_TIMEOUT=120
```

`OPENAI_MODEL_NAME` 填行内网关真正发布的 DeepSeek v4 Flash 模型 ID，不强行假设产品展示名就是 API ID。如果网关不支持 `response_format={"type":"json_object"}`，改成 `AI_JSON_OUTPUT_METHOD=prompt`。两个分析服务都遵循同一配置。

入库正文完整保存和上传。生命周期分析在字符预算内使用完整正文，超出 `CLEANUP_CONTEXT_CHARS` 时保留头尾并明确标记中段省略，模型不能因此猜测全文。每份文档的已核验日期与原文依据缓存；日期到期由规则重新比较，不需要每天再次问模型。无确定日期的分析默认 30 天后重问；正文哈希或模型 ID 改变时重新分析。

```dotenv
CLEANUP_CONTEXT_CHARS=24000
CLEANUP_MIN_CONFIDENCE=95
CLEANUP_AI_RECHECK_DAYS=30
```

前缀元数据中明确未到期或永久的记录先保留；过期元数据不能直接触发删除，必须回到原文核验。活动结束、旧年度、报名截止、局部修改等不能单独证明整个制度已经失效。模型 API 异常不会触发删除。

## 清理操作与定时任务

默认 `CLEANUP_AUTO_DELETE=false`，预览及定时扫描只生成持久化建议。前端“系统维护 → 清理审核与审计”查看依据、批准/拒绝，批准后单独点击执行。删除前会再次核对目标快照及替代文档索引状态。

- 每天北京时间 02:00：总行发文版本关系检查，单次 2000 份，轮转覆盖历史。
- 每天北京时间 03:00：全部分类有效期及正文重复检查，每阶段单次 2000 份。
- 每天北京时间 02:10：按北京时间选择前一天日期目录的最新 DAT，避免 UTC 容器取错日期。
- 每 5 分钟：批量提交待处理正文。

查询 API 示例（URL 的 `/api/v1` 前缀不能省略）：

```bash
curl -X POST 'http://localhost:18000/api/v1/maintenance/clean-expired-documents?limit=50&dry_run=true'
curl 'http://localhost:18000/api/v1/maintenance/cleanup-candidates?status=pending'
curl -X POST 'http://localhost:18000/api/v1/maintenance/cleanup-candidates/1/review' \
  -H 'Content-Type: application/json' \
  -d '{"approved":true,"reviewer":"审核人","comment":"已核对制度全文"}'
curl -X POST 'http://localhost:18000/api/v1/maintenance/cleanup-candidates/1/execute'
```

候选状态：`pending → approved → deleted`；拒绝为 `rejected`，文档身份变化为 `stale`，远端执行失败为 `failed`。相同文档快照的同类建议不会重复创建，也不会在后续扫描中覆盖已拒绝结论。`failed` 建议可以再次执行；已成功删除的任务重放为幂等成功。Dify 返回 404 时，仅在进一步确认原数据集仍存在且目标文档确实不存在后才确认删除完成。

如经过预览核对后要自动删除，将 `CLEANUP_AUTO_DELETE=true`。定时任务只自动执行已核验全文失效日及完全重复正文建议；AI 版本替换仍需人工审核。手动 API 只有 `dry_run=false` 且自动开关已开启时才自动执行这两类。预览 `dry_run=true` 始终不删除。

`days` 参数为了兼容旧 API 保留，现在不再限制为“近 5 天”；重复扫描覆盖全部历史。没有可核验依据的相似或同名文档会保留。

权限沿用原项目的内网服务模式；本次未新增登录或鉴权，审批人是审计填写字段，需要沿用行内网关/访问控制部署。

## 验证与限制

39 项新增离线测试位于 `tests/unit`，使用临时 SQLite、临时 NAS 目录和模拟解析/模型/Dify 响应，不访问行内服务：

```bash
uv run --with pytest python -m pytest tests/unit -q
```

已验证 NAS 路径映射与权限边界、明文/旧解密配置、DAT 兼容、自动入库与人工审核、中文下载头、升级保留旧记录、历史轮转、跨数据集/分类保护、原文引用及置信度、替代文档索引保护、审批与执行分离、执行失败重试和删除幂等。

未完成真实 NAS、PostgreSQL 并发、行内模型网关、解析服务及 Dify 的联合验证。这些连接参数尚未提供。本次也未推送远端仓库。

版本替换仍是总行发文专用，沿用《》标题召回；其他分类的语义替代、附件连带失效、OCR 差异重复、OA 原生撤回状态和精细文号关联未自动实现。超长文档中段条款可能不在模型输入内，缺少依据时保留。若 OA 后续能提供官方有效状态、失效日期、文号和被替代文号，应优先增加这些字段，以官方状态为准，模型负责提取和辅助核对。

## 回滚

恢复原版本代码，按原部署选择 S3 或 NAS 来源；原版本仅支持 S3，若 OA 已完全停用 S3 则不能直接恢复原文件读取。增量列和审计表可保留，不需要删列或清空表。已从 Dify 删除的内容不能靠代码回滚恢复，可使用保存的完整解析正文重新创建知识库文档，新的 Dify ID 必须重新绑定。
