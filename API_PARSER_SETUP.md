# 接口文档解析配置说明

## 概述

项目已从本地文档解析改为接口文档解析模式。新的解析流程使用外部API进行文档解析，然后将解析后的文本内容拼接并传入Dify知识库。

## 主要变更

### 1. 新增接口解析服务
- **文件**: `services/api_document_parser.py`
- **功能**: 通过HTTP接口解析文档，支持多种格式
- **特点**:
  - 调用外部解析API
  - 自动拼接文本块
  - 支持AI分析长度限制
  - 保持与原解析器相同的接口

### 2. 更新Dify集成
- **文件**: `services/dify_service.py`
- **新增方法**: `add_document_to_knowledge_base_by_text()`
- **功能**: 直接通过文本内容创建知识库文档
- **配置**: 使用父子分段模式，符合Dify API要求

### 3. 文档处理流程更新
- **文件**: `tasks/document_processor.py`
- **变更**:
  - 使用新的接口解析服务
  - 传递解析后的文本内容而非文件到Dify
  - 支持ZIP文件中文档的接口解析

## 配置要求

### 环境变量配置

在 `.env` 文件中添加以下配置：

```bash
# 文档解析接口配置
DOCUMENT_PARSE_API_URL=http://your-parse-api-host:port

# AI分析文本长度限制（字符数）
AI_ANALYSIS_MAX_LENGTH=50000

# Dify配置（保持原有配置）
DIFY_API_KEY=your_dify_api_key
DIFY_BASE_URL=https://api.dify.ai
DIFY_DATASET_ID=your_dataset_id
```

### 接口规范

文档解析API必须符合以下规范：

#### 请求格式
```
POST /upload-document/
Content-Type: multipart/form-data

参数:
- file: 文件二进制数据
- separators: 分隔符数组JSON字符串，默认 ["\n\n\n","\n\n",".",""]
- separator_rules: 规则数组JSON，默认 ["after","after","after","after"]
- chunk_size: 单块最大字符数，默认 1000
- chunk_overlap: 重叠字符数，默认 200
- is_separator_regex: 是否正则，默认 false
- keep_separator: 是否保留分隔符，默认 true
```

#### 响应格式
```json
{
  "filename": "原始文件名",
  "file_type": "文件类型",
  "chunks": [
    {
      "content": "文本内容",
      "metadata": {
        "source": "来源文件名",
        "sheet_name": "工作表名（可选）",
        "file_type": "文件类型"
      },
      "length": 123
    }
  ]
}
```

## 使用流程

### 1. 文档解析流程
1. 从S3下载文档
2. 解密文档内容
3. 调用接口解析API获取文本块
4. 拼接文本块形成完整内容
5. 根据AI分析长度限制截取
6. 传入AI分析

### 2. 知识库集成
1. AI分析通过后，使用文本内容创建Dify文档
2. 配置父子分段策略：
   - 父分段：`@@@@@` 分隔符，最大2000 tokens
   - 子分段：`\n` 分隔符，最大500 tokens，重叠50 tokens
3. 使用高质量索引模式

### 3. 测试验证

运行测试脚本验证配置：

```bash
python test_api_parser.py
```

测试将验证：
- 接口解析器配置
- 文档解析功能
- Dify API连接
- 完整的文档处理流程

## 关键特性

### 1. 智能文本拼接
- 自动将解析API返回的文本块拼接为完整文档
- 使用双换行符保持段落分隔
- 记录拼接统计信息

### 2. 长度控制
- 支持配置AI分析的最大文本长度
- 超出限制时自动截取，避免处理超长文档
- 默认限制50,000字符

### 3. 元数据保持
- 保留原文档的元数据信息
- 记录解析方法和统计信息
- 支持表格文件的工作表信息

### 4. 错误处理
- 完善的网络错误处理
- 超时控制（120秒）
- 详细的错误日志记录

## 故障排除

### 常见问题

1. **接口连接失败**
   - 检查 `DOCUMENT_PARSE_API_URL` 配置
   - 确保解析API服务正常运行
   - 验证网络连通性

2. **Dify创建失败**
   - 检查Dify API密钥和数据集ID
   - 确认网络访问权限
   - 查看详细错误日志

3. **文本内容为空**
   - 检查解析API返回的chunks数组
   - 验证文档格式是否支持
   - 查看解析API的错误信息

### 日志监控

关键日志信息：
- `通过接口解析文档: filename`
- `拼接完成，共X个文本块，总长度X字符`
- `文档内容过长，截取前X字符`
- `通过文本创建Dify文档: filename`

## 迁移说明

从原本地解析迁移到接口解析：

1. **备份现有配置**
2. **部署文档解析API服务**
3. **更新环境变量配置**
4. **运行测试验证**
5. **逐步切换生产环境**

## 性能考虑

- 接口解析可能比本地解析稍慢
- 网络传输增加延迟
- 支持并发解析提高整体吞吐量
- 解析服务可独立扩展

## 安全注意事项

- 确保解析API服务的安全性
- 传输敏感文档时考虑加密
- 配置适当的网络访问控制
- 定期更新解析服务组件