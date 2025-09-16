# OpenAI 自定义配置说明

本文档说明如何配置系统以支持自定义的 OpenAI API 服务。

## 🔧 配置选项

系统支持以下环境变量来配置 OpenAI API：

| 环境变量 | 说明 | 必需 | 默认值 |
|---------|------|------|--------|
| `OPENAI_API_KEY` | OpenAI API 密钥 | ✅ 是 | 无 |
| `OPENAI_BASE_URL` | 自定义 API 基础地址 | ❌ 否 | 官方 API |
| `OPENAI_MODEL_NAME` | 模型名称 | ❌ 否 | `gpt-4` |

## 📋 使用场景

### 1. 官方 OpenAI API

使用官方 OpenAI 服务：

```bash
export OPENAI_API_KEY="sk-your-openai-api-key"
export OPENAI_MODEL_NAME="gpt-4"
# OPENAI_BASE_URL 留空，系统将使用官方 API
```

### 2. Azure OpenAI Service

使用 Azure OpenAI 服务：

```bash
export OPENAI_API_KEY="your-azure-api-key"
export OPENAI_BASE_URL="https://your-resource.openai.azure.com/openai/deployments/your-deployment/chat/completions?api-version=2024-02-15-preview"
export OPENAI_MODEL_NAME="gpt-4"
```

### 3. 自定义 OpenAI 兼容服务

使用第三方 OpenAI 兼容 API：

```bash
export OPENAI_API_KEY="your-custom-api-key"
export OPENAI_BASE_URL="https://api.example.com/v1"
export OPENAI_MODEL_NAME="gpt-3.5-turbo"
```

### 4. 本地部署的模型服务

使用本地部署的兼容服务（如 Ollama、LocalAI 等）：

```bash
export OPENAI_API_KEY="local-key"
export OPENAI_BASE_URL="http://localhost:11434/v1"
export OPENAI_MODEL_NAME="llama2:7b"
```

## 🚀 配置步骤

### 方法1：环境变量设置

1. **Linux/macOS**:
   ```bash
   export OPENAI_API_KEY="your-api-key"
   export OPENAI_BASE_URL="https://your-api-url/v1"
   export OPENAI_MODEL_NAME="your-model-name"
   ```

2. **Windows**:
   ```cmd
   set OPENAI_API_KEY=your-api-key
   set OPENAI_BASE_URL=https://your-api-url/v1
   set OPENAI_MODEL_NAME=your-model-name
   ```

### 方法2：.env 文件

在项目根目录创建 `.env` 文件：

```env
OPENAI_API_KEY=your-api-key
OPENAI_BASE_URL=https://your-api-url/v1
OPENAI_MODEL_NAME=your-model-name
```

## 🧪 测试配置

### 使用示例脚本测试

运行提供的测试脚本：

```bash
python example_openai_config.py
```

### 使用 Web 界面测试

1. 启动应用：`streamlit run app.py`
2. 进入 "系统设置" -> "AI配置" 页面
3. 点击 "🧪 测试AI分析" 按钮

## ⚠️ 注意事项

1. **API 兼容性**: 确保自定义 API 服务与 OpenAI API v1 兼容
2. **模型名称**: 使用正确的模型名称，确保目标服务支持该模型
3. **网络访问**: 确保应用能够访问指定的 API 地址
4. **API 密钥安全**: 不要在代码中硬编码 API 密钥
5. **重启应用**: 修改环境变量后需要重启应用才能生效

## 🔍 故障排除

### 常见问题

1. **连接失败**
   - 检查 `OPENAI_BASE_URL` 格式是否正确
   - 确认网络连接和防火墙设置
   - 验证 API 服务是否正常运行

2. **认证失败**
   - 检查 `OPENAI_API_KEY` 是否正确
   - 确认 API 密钥是否有效且未过期

3. **模型不存在**
   - 检查 `OPENAI_MODEL_NAME` 是否正确
   - 确认目标服务是否支持该模型

4. **请求格式错误**
   - 确保 API 服务完全兼容 OpenAI API v1 格式
   - 检查请求参数是否符合服务要求

### 调试方法

1. **查看日志**:
   ```bash
   tail -f logs/app.log
   ```

2. **测试 API 连接**:
   ```bash
   curl -X POST "$OPENAI_BASE_URL/chat/completions" \
     -H "Authorization: Bearer $OPENAI_API_KEY" \
     -H "Content-Type: application/json" \
     -d '{
       "model": "'$OPENAI_MODEL_NAME'",
       "messages": [{"role": "user", "content": "Hello"}],
       "max_tokens": 10
     }'
   ```

## 📞 技术支持

如果遇到配置问题，请：

1. 检查日志文件中的错误信息
2. 使用测试脚本验证配置
3. 确认 API 服务的兼容性
4. 联系系统管理员获取帮助 