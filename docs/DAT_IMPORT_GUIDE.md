# DAT文件导入功能使用指南

## 功能概述

DAT文件导入功能允许从数据组提供的.dat文件中批量导入文件信息到`oa_file_info`表。该功能支持增量导入和定时自动同步。

## 文件格式说明

### DAT文件格式
- **字段分隔符**: ASCII码1字符（`\x01`）
- **文本编码**: UTF-8
- **每行代表**: 一条文件记录

### 字段顺序
DAT文件的字段按以下顺序排列（共10个字段）：

1. `imagefileid` - 文件ID（必填，唯一）
2. `business_category` - 业务分类（枚举值）
3. `is_zw` - 是否正文（布尔值：1/true/yes 或 0/false/no）
4. `fj_imagefileid` - 附件文件ID列表（JSON格式或逗号分隔）
5. `imagefilename` - 文件名（必填）
6. `imagefiletype` - 文档类型（如：pdf, docx等）
7. `is_zip` - 是否压缩文件（布尔值）
8. `filesize` - 文件大小（字节）
9. `asecode` - OSS下载解密code
10. `tokenkey` - OSS下载key

### 业务分类枚举值
```
HEADQUARTERS_ISSUE - 总行发文
RETAIL_ANNOUNCEMENT - 零售条线公告
PUBLICATION_RELEASE - 刊物发布
BRANCH_ISSUE - 支行发文
BRANCH_RECEIVE - 支行收文
PUBLIC_STANDARD - 公共发布及规范文件
HEADQUARTERS_RECEIVE - 总行收文
CORPORATE_ANNOUNCEMENT - 公司条线公告
```

### 示例数据
```
FILE001<SOH>HEADQUARTERS_ISSUE<SOH>1<SOH>["ATT001","ATT002"]<SOH>测试文档.pdf<SOH>pdf<SOH>0<SOH>1024576<SOH>abc123<SOH>token_key_xyz
```
注：`<SOH>` 代表ASCII码1字符

## 配置说明

### 环境变量配置

在`.env`文件中添加以下配置：

```bash
# DAT文件导入配置
DAT_IMPORT_DIRECTORY=/data/dat_files  # DAT文件存放目录
DAT_IMPORT_UPDATE_EXISTING=false       # 是否更新已存在的记录（默认：false）
```

### 配置项说明

- **DAT_IMPORT_DIRECTORY**: DAT文件存放的目录路径
  - 系统会自动选择该目录下最新的.dat文件
  - 默认值：`/data/dat_files`

- **DAT_IMPORT_UPDATE_EXISTING**: 是否更新已存在的记录
  - `true`: 如果记录已存在，更新记录的所有字段
  - `false`: 如果记录已存在，跳过该记录（增量导入）
  - 默认值：`false`

## 使用方式

### 1. 定时自动导入

系统每天凌晨2:10自动执行导入任务：

- **执行时间**: 每天 02:10
- **导入模式**: 自动选择最新的DAT文件
- **更新策略**: 根据配置文件设置

**Celery Beat配置**（已自动配置）：
```python
'import-dat-file': {
    'task': 'import_dat_file_task',
    'schedule': crontab(hour='2', minute='10'),
    'args': ()
}
```

### 2. 手动触发导入

#### 方式一：通过Web界面

1. 打开系统维护页面
2. 选择"📥 数据导入"标签页
3. （可选）输入DAT文件路径，留空则自动选择最新文件
4. （可选）勾选"更新已存在记录"
5. 点击"🚀 开始导入"按钮
6. 在"📊 任务监控"标签页查看执行进度

#### 方式二：通过API调用

**端点**: `POST /data/import-dat`

**请求体**（可选）：
```json
{
  "dat_file_path": "/data/dat_files/data_20250114.dat",  // 可选
  "update_existing": false  // 可选
}
```

**响应示例**：
```json
{
  "success": true,
  "message": "DAT文件导入任务已提交",
  "task_id": "abc123-def456-789",
  "description": "任务将自动导入最新的DAT文件数据，请通过task_id查询任务状态"
}
```

**查询任务状态**：
```
GET /maintenance/task-status/{task_id}
```

**查询导入历史**：
```
GET /data/import-status
```

#### 方式三：通过Celery命令行

```bash
# 手动触发导入任务
celery -A tasks.document_processor call import_dat_file_task

# 指定文件路径
celery -A tasks.document_processor call import_dat_file_task --args='["/path/to/file.dat", false]'
```

## 导入流程

1. **文件选择**
   - 如果指定文件路径，使用指定文件
   - 否则自动选择配置目录下最新的.dat文件

2. **数据解析**
   - 按行读取DAT文件
   - 使用ASCII码1字符分割字段
   - 验证字段数量（至少10个字段）
   - 解析各字段类型（枚举、布尔、整数、JSON等）

3. **数据导入**
   - 检查记录是否已存在（根据`imagefileid`）
   - 如果不存在：创建新记录
   - 如果已存在：
     - `update_existing=true`: 更新记录
     - `update_existing=false`: 跳过记录
   - 每1000条记录提交一次事务

4. **结果统计**
   - `total_lines`: 总行数
   - `parsed_lines`: 成功解析的行数
   - `new_records`: 新增记录数
   - `updated_records`: 更新记录数
   - `skipped_records`: 跳过记录数
   - `error_records`: 错误记录数
   - `errors`: 错误详情列表

## 监控与日志

### Web界面监控

在"📊 任务监控"标签页可以查看：
- 任务执行状态（等待/执行中/成功/失败）
- 执行结果统计
- 错误信息详情

### 日志查看

**Celery Worker日志**：
```bash
tail -f celery_worker.log
```

**关键日志信息**：
- 文件选择：`自动选择最新DAT文件: /path/to/file.dat`
- 导入进度：`已处理 1000 条记录...`
- 完成统计：`DAT文件导入完成 - 统计: {...}`

### 导入历史查询

通过API查询最近的导入记录：

**请求**：
```
GET /data/import-status
```

**响应**：
```json
{
  "total_imported": 10000,
  "recent_imports": [
    {
      "date": "2025-01-14",
      "source": "dat_import",
      "count": 1500
    },
    {
      "date": "2025-01-13",
      "source": "dat_import",
      "count": 1200
    }
  ]
}
```

## 错误处理

### 常见错误及解决方案

1. **文件不存在**
   - 错误：`未找到DAT文件: 在目录 /data/dat_files 中未找到.dat文件`
   - 解决：检查目录路径配置，确保目录存在且包含.dat文件

2. **字段数量不足**
   - 错误：`字段数量不足: 8 < 10`
   - 解决：检查DAT文件格式，确保每行至少有10个字段

3. **无效的业务分类**
   - 错误：`无效的业务分类: INVALID_CATEGORY`
   - 解决：检查业务分类值是否在枚举列表中

4. **数据库连接失败**
   - 错误：`导入记录失败: could not connect to database`
   - 解决：检查数据库连接配置和网络连接

5. **文件编码问题**
   - 错误：`解析行数据失败: 'utf-8' codec can't decode`
   - 解决：确保DAT文件使用UTF-8编码

### 事务回滚

- 每1000条记录作为一个事务批次
- 如果某条记录导入失败，该条记录会被跳过，但不影响其他记录
- 批次内的错误会触发该批次的回滚

## 性能优化建议

1. **批量提交**: 系统默认每1000条提交一次，适用于大多数场景

2. **并发控制**: 避免同时运行多个导入任务

3. **文件大小**: 建议单个DAT文件不超过100万行

4. **索引优化**: `imagefileid`字段已建立唯一索引，加速查重

5. **定时任务**: 定时任务设置在凌晨2:10，避免业务高峰期

## 最佳实践

1. **增量导入**:
   - 日常导入建议使用增量模式（`update_existing=false`）
   - 减少数据库写入操作，提高性能

2. **全量更新**:
   - 数据纠正时使用更新模式（`update_existing=true`）
   - 确保数据一致性

3. **文件命名**:
   - 建议使用日期命名：`data_YYYYMMDD.dat`
   - 便于识别和追溯

4. **备份策略**:
   - 导入前备份数据库
   - 保留历史DAT文件

5. **监控告警**:
   - 定期检查导入任务执行状态
   - 关注错误数和跳过数的异常增长

## 故障排查

### 检查清单

1. ☑ DAT文件是否存在且可读
2. ☑ 文件编码是否为UTF-8
3. ☑ 字段分隔符是否正确（ASCII码1）
4. ☑ 字段数量是否正确（至少10个）
5. ☑ 业务分类值是否有效
6. ☑ 数据库连接是否正常
7. ☑ Celery Worker是否运行中
8. ☑ Celery Beat是否运行中

### 调试命令

```bash
# 检查Celery服务状态
celery -A tasks.document_processor inspect active

# 查看任务队列
celery -A tasks.document_processor inspect scheduled

# 手动测试导入
python -c "
from services.dat_importer import import_dat_file
from database import get_db_session
db = get_db_session()
result = import_dat_file('/path/to/test.dat', db, False)
print(result)
"
```

## 联系支持

如遇到问题，请提供以下信息：
- 错误日志
- DAT文件样本（前几行）
- 系统配置信息
- 任务ID

---

**文档版本**: 1.0
**更新日期**: 2025-01-14
**维护者**: OA文档处理系统团队
