# 文档版本管理和有效期管理功能

本文档介绍新增的文档版本管理和有效期管理功能。

## 功能概述

### 1. 总行发文版本去重

自动检测和清理总行发文中的旧版本文档，保留最新版本。

**工作流程:**

1. 查询所有已完成的总行发文文档
2. 检查文档名是否包含修订关键词（如：修订、修改、更新、废止等）
3. 从文档名中提取《》中的标题进行模糊匹配
4. 如果找到多个相同标题的文档：
   - 下载每个文档并提取前400字
   - 使用AI分析文档版本号（如：昆农商发【2025】xxx号）
   - 判断哪个是最新版本
   - 删除旧版本文档

**涉及的修订关键词:**
- 修订、修改、更新、调整、变更、修正、补充、完善、废止、废除

### 2. 文档有效期检查

检查除总行发文外的其他文档是否过期，自动删除过期文档。

**工作流程:**

1. 查询所有已完成的非总行发文文档
2. 检查ai_metadata中的expiration_date字段：
   - 如果有有效期且已过期 → 删除文档
   - 如果没有有效期信息 → 使用AI判断是否过期
3. AI判断方式：
   - 下载文档前600字
   - 注入当前日期
   - 让AI关注标题中的日期和文档时间区间
   - 判断文档是否过期

**永久有效标识:**
- 永久、无、permanent、none、never、长期

## 文件结构

```
services/
  └── version_manager.py         # 版本管理和有效期管理服务

tasks/
  └── document_processor.py      # 添加了两个新的定时任务
      - clean_headquarters_version_duplicates  # 总行发文版本去重
      - clean_expired_documents                # 过期文档清理

tests/
  └── test_version_manager.py    # 测试脚本
```

## API说明

### VersionManager 类

位于 `services/version_manager.py`

#### 主要方法

1. **extract_title_from_brackets(filename: str) -> Optional[str]**
   - 从文档名中提取《》中间的内容
   - 参数: 文件名
   - 返回: 提取的标题，如果没有找到返回None

2. **check_revision_keywords(filename: str) -> bool**
   - 检查文档名是否包含修订关键词
   - 参数: 文件名
   - 返回: 是否包含修订关键词

3. **find_similar_documents(db, title, business_category) -> List[OAFileInfo]**
   - 根据标题模糊查询相似文档
   - 参数:
     - db: 数据库会话
     - title: 提取的标题
     - business_category: 业务分类
   - 返回: 相似文档列表

4. **compare_versions_by_ai(documents_with_previews) -> Dict**
   - 通过AI判断哪个文档是最新版本
   - 参数: 包含文档信息和预览内容的列表
   - 返回: 包含最新版本ID、旧版本ID列表和判断理由的字典

5. **check_document_expiration_by_metadata(file_info) -> Tuple[bool, Optional[str]]**
   - 通过ai_metadata检查文档是否过期
   - 参数: 文件信息
   - 返回: (是否过期, 过期日期)

6. **check_document_expiration_by_ai(file_info, preview_content) -> Tuple[bool, str]**
   - 通过AI判断文档是否过期
   - 参数:
     - file_info: 文件信息
     - preview_content: 文档预览内容
   - 返回: (是否过期, 判断理由)

7. **delete_document_from_dify(file_info, db) -> bool**
   - 从Dify知识库中删除文档
   - 参数:
     - file_info: 文件信息
     - db: 数据库会话
   - 返回: 是否删除成功

8. **process_headquarters_version_deduplication(db, limit=50) -> Dict**
   - 处理总行发文的版本去重
   - 参数:
     - db: 数据库会话
     - limit: 每次处理的文档数量限制
   - 返回: 处理结果统计

9. **process_document_expiration_check(db, limit=50) -> Dict**
   - 处理文档有效期检查
   - 参数:
     - db: 数据库会话
     - limit: 每次处理的文档数量限制
   - 返回: 处理结果统计

## 定时任务配置

在 `tasks/document_processor.py` 中配置了两个新的定时任务：

```python
app.conf.beat_schedule = {
    # ... 其他任务 ...

    'clean-headquarters-version-duplicates': {
        'task': 'clean_headquarters_version_duplicates',
        'schedule': crontab(hour='2', minute='0'),  # 每天凌晨2点执行
        'args': (50,)  # 每次处理50个文档
    },
    'clean-expired-documents': {
        'task': 'clean_expired_documents',
        'schedule': crontab(hour='3', minute='0', day_of_week='0'),  # 每周日凌晨3点执行（每7天一次）
        'args': (50,)  # 每次处理50个文档
    },
}
```

### 调整定时任务执行时间

可以根据需要修改 `schedule` 参数：

```python
# 每天凌晨2点
crontab(hour='2', minute='0')

# 每周一凌晨3点
crontab(day_of_week=1, hour='3', minute='0')

# 每月1号凌晨4点
crontab(day_of_month=1, hour='4', minute='0')

# 每小时执行
crontab(minute='0')

# 每30分钟执行
crontab(minute='*/30')
```

## 使用方法

### 1. 手动触发任务

使用Celery命令行触发任务：

```bash
# 触发总行发文版本去重
celery -A tasks.document_processor call clean_headquarters_version_duplicates --args='[50]'

# 触发过期文档清理
celery -A tasks.document_processor call clean_expired_documents --args='[50]'
```

### 2. 在代码中调用

```python
from tasks.document_processor import clean_headquarters_version_duplicates, clean_expired_documents

# 异步调用
result1 = clean_headquarters_version_duplicates.delay(50)
result2 = clean_expired_documents.delay(50)

# 同步调用（等待结果）
stats1 = clean_headquarters_version_duplicates.apply(args=[50]).get()
stats2 = clean_expired_documents.apply(args=[50]).get()
```

### 3. 运行测试

```bash
cd tests
python test_version_manager.py
```

## 返回结果格式

### 总行发文版本去重结果

```python
{
    'processed': 10,           # 处理的文档数量
    'duplicates_found': 3,     # 找到的重复组数
    'deleted': 5,              # 删除的文档数量
    'errors': 0,               # 错误数量
    'details': [               # 详细信息
        {
            'title': '信贷管理办法',
            'latest_document': 'doc_id_123',
            'deleted_count': 2,
            'reasoning': 'AI判断理由'
        }
    ]
}
```

### 过期文档清理结果

```python
{
    'processed': 20,              # 处理的文档数量
    'expired_by_metadata': 5,     # 通过元数据判定过期的数量
    'expired_by_ai': 3,           # 通过AI判定过期的数量
    'deleted': 8,                 # 删除的文档数量
    'errors': 0,                  # 错误数量
    'details': [                  # 详细信息
        {
            'filename': '通知.docx',
            'expiration_date': '2024-12-31',
            'check_method': 'metadata'
        },
        {
            'filename': '公告.pdf',
            'reasoning': 'AI判断理由',
            'check_method': 'ai'
        }
    ]
}
```

## 注意事项

1. **数据安全**
   - 删除操作不可逆，请确保数据备份
   - 建议先在测试环境验证
   - 可以先运行测试脚本查看会影响哪些文档

2. **性能考虑**
   - 每次处理的文档数量有限制（默认50）
   - AI调用会消耗API配额
   - 文档下载和解析需要时间

3. **AI依赖**
   - 需要配置OPENAI_API_KEY
   - 确保AI服务可用
   - AI判断可能不是100%准确

4. **日志监控**
   - 所有操作都有详细日志
   - 建议定期检查日志文件
   - 关注错误和异常情况

## 故障排查

### 常见问题

1. **AI客户端未初始化**
   - 检查环境变量 OPENAI_API_KEY 是否配置
   - 检查 OPENAI_BASE_URL 是否正确（如使用自定义URL）

2. **文档下载失败**
   - 检查S3配置是否正确
   - 检查网络连接
   - 确认文件tokenkey有效

3. **删除失败**
   - 检查Dify API配置
   - 确认document_id存在
   - 检查知识库权限

4. **定时任务不执行**
   - 确认Celery Beat服务运行中
   - 检查定时任务配置
   - 查看Celery日志

### 查看日志

```bash
# 查看Celery worker日志
tail -f logs/celery_worker.log

# 查看Celery beat日志
tail -f logs/celery_beat.log

# 查看应用日志
tail -f logs/app.log
```

## 未来改进

1. 支持批量删除确认机制
2. 添加删除前的人工审核流程
3. 提供删除记录的恢复功能
4. 优化AI判断的准确性
5. 支持更多的日期格式识别
6. 添加Web界面管理功能

## 相关接口

### Dify文档删除接口

```
DELETE /v1/datasets/{dataset_id}/documents/{document_id}
```

- dataset_id: 知识库ID
- document_id: 文档ID
- 需要API密钥认证

## 联系方式

如有问题或建议，请联系开发团队。
