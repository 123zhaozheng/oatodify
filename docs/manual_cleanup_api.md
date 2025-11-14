# 手动触发文档清理任务 - API使用说明

## API接口列表

### 1. 手动清理总行发文版本重复

**接口地址:** `POST /maintenance/clean-version-duplicates`

**描述:** 手动触发总行发文版本去重任务，检测修订文档并删除旧版本

**请求参数:**
- `limit` (可选): 每次处理的文档数量限制，默认50，最大200

**请求示例:**

```bash
# 使用默认限制（50个文档）
curl -X POST "http://localhost:8000/maintenance/clean-version-duplicates"

# 指定处理数量
curl -X POST "http://localhost:8000/maintenance/clean-version-duplicates?limit=100"
```

**返回示例:**

```json
{
  "success": true,
  "message": "总行发文版本去重任务已提交，限制处理: 50 个文档",
  "task_id": "abc123-def456-ghi789",
  "description": "任务将检测修订文档并清理旧版本，请查看日志了解详细进度"
}
```

---

### 2. 手动清理过期文档

**接口地址:** `POST /maintenance/clean-expired-documents`

**描述:** 手动触发过期文档清理任务，检查文档有效期并删除过期文档

**请求参数:**
- `limit` (可选): 每次处理的文档数量限制，默认50，最大200

**请求示例:**

```bash
# 使用默认限制（50个文档）
curl -X POST "http://localhost:8000/maintenance/clean-expired-documents"

# 指定处理数量
curl -X POST "http://localhost:8000/maintenance/clean-expired-documents?limit=100"
```

**返回示例:**

```json
{
  "success": true,
  "message": "过期文档清理任务已提交，限制处理: 50 个文档",
  "task_id": "xyz789-abc123-def456",
  "description": "任务将检查文档有效期并清理过期文档，请查看日志了解详细进度"
}
```

---

### 3. 查询维护任务状态

**接口地址:** `GET /maintenance/task-status/{task_id}`

**描述:** 查询维护任务的执行状态和结果

**路径参数:**
- `task_id`: 任务ID（从提交任务时返回的task_id）

**请求示例:**

```bash
curl -X GET "http://localhost:8000/maintenance/task-status/abc123-def456-ghi789"
```

**返回示例（任务进行中）:**

```json
{
  "task_id": "abc123-def456-ghi789",
  "state": "PROGRESS",
  "ready": false,
  "successful": null,
  "info": "任务正在执行中..."
}
```

**返回示例（任务完成）:**

```json
{
  "task_id": "abc123-def456-ghi789",
  "state": "SUCCESS",
  "ready": true,
  "successful": true,
  "result": {
    "processed": 50,
    "duplicates_found": 5,
    "deleted": 8,
    "errors": 0,
    "details": [
      {
        "title": "信贷管理办法",
        "latest_document": "file_id_123",
        "deleted_count": 2,
        "reasoning": "根据文档中的发文号判断，file_id_123是最新版本"
      }
    ]
  }
}
```

**返回示例（任务失败）:**

```json
{
  "task_id": "abc123-def456-ghi789",
  "state": "FAILURE",
  "ready": true,
  "successful": false,
  "error": "处理过程中发生错误: ..."
}
```

---

## 使用场景

### 场景1: 定期维护

在每月或每周进行系统维护时，手动触发清理任务：

```bash
# 1. 先清理版本重复
curl -X POST "http://localhost:8000/maintenance/clean-version-duplicates?limit=100"

# 2. 等待几分钟，然后清理过期文档
curl -X POST "http://localhost:8000/maintenance/clean-expired-documents?limit=100"
```

### 场景2: 紧急清理

发现大量重复或过期文档需要紧急清理：

```bash
# 使用较大的limit值，一次性处理更多文档
curl -X POST "http://localhost:8000/maintenance/clean-version-duplicates?limit=200"
```

### 场景3: 测试验证

在测试环境验证清理功能：

```bash
# 使用小的limit值，先测试几个文档
curl -X POST "http://localhost:8000/maintenance/clean-version-duplicates?limit=5"

# 然后查询任务状态
curl -X GET "http://localhost:8000/maintenance/task-status/{返回的task_id}"
```

---

## Python调用示例

### 使用 requests 库

```python
import requests
import time

# 基础URL
BASE_URL = "http://localhost:8000"

# 1. 提交清理任务
def submit_cleanup_task(task_type="version", limit=50):
    """提交清理任务"""
    if task_type == "version":
        url = f"{BASE_URL}/maintenance/clean-version-duplicates"
    else:
        url = f"{BASE_URL}/maintenance/clean-expired-documents"

    response = requests.post(url, params={"limit": limit})
    result = response.json()

    print(f"任务已提交: {result['message']}")
    print(f"任务ID: {result['task_id']}")

    return result['task_id']

# 2. 查询任务状态
def check_task_status(task_id):
    """查询任务状态"""
    url = f"{BASE_URL}/maintenance/task-status/{task_id}"
    response = requests.get(url)
    result = response.json()

    print(f"任务状态: {result['state']}")
    print(f"是否完成: {result['ready']}")

    if result['ready']:
        if result['successful']:
            print("任务成功完成!")
            print(f"处理结果: {result['result']}")
        else:
            print(f"任务失败: {result['error']}")

    return result

# 3. 等待任务完成
def wait_for_task(task_id, max_wait=300):
    """等待任务完成（最多等待max_wait秒）"""
    start_time = time.time()

    while time.time() - start_time < max_wait:
        status = check_task_status(task_id)

        if status['ready']:
            return status

        print("任务进行中，等待5秒...")
        time.sleep(5)

    print("等待超时!")
    return None

# 使用示例
if __name__ == "__main__":
    # 提交版本去重任务
    task_id = submit_cleanup_task(task_type="version", limit=50)

    # 等待任务完成
    result = wait_for_task(task_id)

    if result and result['successful']:
        print("\n清理统计:")
        stats = result['result']
        print(f"  处理文档数: {stats['processed']}")
        print(f"  发现重复组: {stats['duplicates_found']}")
        print(f"  删除文档数: {stats['deleted']}")
        print(f"  错误数: {stats['errors']}")
```

---

## JavaScript/前端调用示例

### 使用 fetch API

```javascript
// 基础URL
const BASE_URL = 'http://localhost:8000';

// 1. 提交清理任务
async function submitCleanupTask(taskType = 'version', limit = 50) {
  const endpoint = taskType === 'version'
    ? '/maintenance/clean-version-duplicates'
    : '/maintenance/clean-expired-documents';

  const response = await fetch(`${BASE_URL}${endpoint}?limit=${limit}`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json'
    }
  });

  const result = await response.json();
  console.log('任务已提交:', result.message);
  console.log('任务ID:', result.task_id);

  return result.task_id;
}

// 2. 查询任务状态
async function checkTaskStatus(taskId) {
  const response = await fetch(`${BASE_URL}/maintenance/task-status/${taskId}`);
  const result = await response.json();

  console.log('任务状态:', result.state);
  console.log('是否完成:', result.ready);

  if (result.ready) {
    if (result.successful) {
      console.log('任务成功完成!');
      console.log('处理结果:', result.result);
    } else {
      console.log('任务失败:', result.error);
    }
  }

  return result;
}

// 3. 等待任务完成
async function waitForTask(taskId, maxWait = 300000) {
  const startTime = Date.now();

  while (Date.now() - startTime < maxWait) {
    const status = await checkTaskStatus(taskId);

    if (status.ready) {
      return status;
    }

    console.log('任务进行中，等待5秒...');
    await new Promise(resolve => setTimeout(resolve, 5000));
  }

  console.log('等待超时!');
  return null;
}

// 使用示例
async function runCleanup() {
  try {
    // 提交版本去重任务
    const taskId = await submitCleanupTask('version', 50);

    // 等待任务完成
    const result = await waitForTask(taskId);

    if (result && result.successful) {
      console.log('\n清理统计:');
      const stats = result.result;
      console.log(`  处理文档数: ${stats.processed}`);
      console.log(`  发现重复组: ${stats.duplicates_found}`);
      console.log(`  删除文档数: ${stats.deleted}`);
      console.log(`  错误数: ${stats.errors}`);
    }
  } catch (error) {
    console.error('执行清理任务失败:', error);
  }
}

// 执行
runCleanup();
```

---

## 对比：定时任务 vs 手动触发

| 特性 | 定时任务 | 手动触发 |
|------|---------|---------|
| 触发方式 | 自动（按计划执行） | 手动（通过API） |
| 执行时间 | 固定时间（凌晨2点/3点） | 任意时间 |
| 处理数量 | 固定（50个） | 可调整（1-200个） |
| 适用场景 | 日常维护 | 紧急清理、测试 |
| 灵活性 | 低 | 高 |

---

## 注意事项

### 1. 并发控制
- 避免同时运行多个相同类型的清理任务
- 建议等待上一个任务完成后再提交新任务

### 2. 数据安全
- 删除操作不可逆，请谨慎使用
- 建议先在测试环境验证
- 生产环境建议先用小的limit值测试

### 3. 性能考虑
- 大量文档处理需要时间
- AI调用会消耗API配额
- 建议根据系统负载调整limit值

### 4. 监控日志
- 查看应用日志了解详细进度
- 关注错误日志
- 定期检查任务执行结果

---

## 故障排查

### 问题1: 任务提交失败
**可能原因:**
- Celery worker未运行
- Redis连接失败

**解决方法:**
```bash
# 检查Celery worker状态
celery -A tasks.document_processor inspect active

# 检查Redis连接
redis-cli ping
```

### 问题2: 任务一直处于PROGRESS状态
**可能原因:**
- Worker处理缓慢
- AI服务响应慢

**解决方法:**
- 查看worker日志
- 检查AI服务可用性
- 减小limit值

### 问题3: 查询任务状态返回404
**可能原因:**
- task_id错误
- 任务结果已过期（默认保留1天）

**解决方法:**
- 确认task_id正确
- 及时查询任务结果

---

## 相关文档

- [版本管理功能详细文档](version_management.md)
- [API完整文档](http://localhost:8000/docs) - FastAPI自动生成的交互式文档
- [Celery任务队列文档](https://docs.celeryproject.org/)

---

## 联系方式

如有问题或建议，请联系开发团队。
