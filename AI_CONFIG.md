# AI分析器配置说明

## 概述

新的AI分析器支持多知识库管理和分类特定的处理逻辑，每种文档分类可以有不同的AI提示词和输出格式。

## 环境变量配置

### AI JSON输出控制方式

```bash
# 控制AI如何返回JSON格式的结果
AI_JSON_OUTPUT_METHOD=response_format  # 或 prompt
```

**两种方式的区别：**

1. **response_format**: 使用OpenAI的`response_format={"type": "json_object"}`参数强制AI返回JSON
   - 优点：更可靠，AI必须返回有效JSON
   - 缺点：需要OpenAI API支持，某些模型可能不支持

2. **prompt**: 在提示词中包含JSON模板，让AI按照模板返回
   - 优点：兼容性好，所有模型都支持
   - 缺点：AI可能不严格遵循格式

## 数据库配置

### 知识库表 (knowledge_bases)

存储多个知识库的配置信息：

```sql
-- 示例：创建专门的零售业务知识库
INSERT INTO knowledge_bases (name, description, dify_dataset_id, status) 
VALUES ('零售业务知识库', '专门存储零售条线相关文档', 'retail-dataset-001', 'active');
```

### 文档分类映射表 (document_category_mappings)

配置每种业务分类对应的知识库和AI处理逻辑：

```sql
-- 示例：配置零售公告使用专门的知识库和提示词
INSERT INTO document_category_mappings (
    knowledge_base_id, 
    business_category, 
    ai_prompt_template,
    ai_output_schema,
    min_confidence_score,
    auto_approve_threshold
) VALUES (
    2,  -- 零售业务知识库ID
    'retail_announcement',
    '你是零售业务专家，请分析以下文档...',  -- 自定义提示词
    '{"type": "object", "properties": {...}}',  -- 自定义输出格式
    75,  -- 最低置信度
    85   -- 自动审批阈值
);
```

## AI分析流程

### 1. 文档分类确定
- **不再让AI判断文档分类**：业务分类来自数据库的`business_category`字段
- AI只负责分析文档是否适合加入知识库

### 2. 处理器选择
- 根据`business_category`从数据库查找对应的`DocumentCategoryMapping`
- 获取该分类特定的提示词模板和输出格式

### 3. 知识库选择
- 根据分类映射确定目标知识库
- 如果没有特定映射，使用默认知识库

### 4. AI分析执行
- 使用分类特定的提示词和输出格式
- 根据`AI_JSON_OUTPUT_METHOD`选择JSON输出方式

## 分类特定的输出字段

每种业务分类都有特定的分析字段：

### 总行发文 (headquarters_issue)
- `policy_level`: 政策层级 (strategic/operational/guidance)
- `target_audience`: 目标受众 (all_branches/specific_departments/management)
- `implementation_difficulty`: 执行难度 (low/medium/high)

### 零售条线公告 (retail_announcement)
- `service_impact`: 服务影响 (customer_facing/internal_process/both)
- `product_relevance`: 产品相关性 (high/medium/low)
- `training_value`: 培训价值 (high/medium/low)

### 刊物发布 (publication_release)
- `information_type`: 信息类型 (news/analysis/case_study/research)
- `reference_value`: 参考价值 (high/medium/low)
- `knowledge_depth`: 知识深度 (basic/intermediate/advanced)

### 支行发文 (branch_issue)
- `innovation_level`: 创新程度 (high/medium/low)
- `replicability`: 可复制性 (high/medium/low)
- `regional_specificity`: 地域特殊性 (high/medium/low)

### 支行收文 (branch_receive)
- `execution_clarity`: 执行清晰度 (clear/moderate/unclear)
- `compliance_level`: 合规程度 (mandatory/recommended/optional)
- `measurability`: 可衡量性 (quantifiable/qualitative/subjective)

### 公共发布及规范文件 (public_standard)
- `standard_type`: 标准类型 (technical/procedural/management)
- `authority_level`: 权威程度 (regulatory/industry/internal)
- `detail_level`: 详细程度 (comprehensive/moderate/basic)

### 总行收文 (headquarters_receive)
- `urgency_level`: 紧急程度 (urgent/normal/low)
- `authority_source`: 权威来源 (regulatory/supervisory/industry)
- `action_required`: 需要行动 (immediate/planned/informational)

### 公司条线公告 (corporate_announcement)
- `business_impact`: 业务影响 (high/medium/low)
- `client_focus`: 客户导向 (b2b_focused/internal_process/mixed)
- `risk_relevance`: 风险相关性 (high/medium/low)

## 自定义配置示例

### 1. 自定义提示词模板

```sql
UPDATE document_category_mappings 
SET ai_prompt_template = '
你是一个专业的{category}文档分析专家。

文档信息：
- 文件名: {filename}
- 文档类型: {file_type}
- 内容长度: {content_length} 字符
- 业务分类: {business_category}

请分析这个文档的以下方面：
1. 是否包含实用的操作指导
2. 是否有助于提升客户服务质量
3. 内容的完整性和准确性

文档内容：
{content}

请返回JSON格式的分析结果。
'
WHERE business_category = 'retail_announcement';
```

### 2. 自定义输出格式

```sql
UPDATE document_category_mappings 
SET ai_output_schema = '{
  "type": "object",
  "properties": {
    "suitable_for_kb": {"type": "boolean"},
    "confidence_score": {"type": "integer", "minimum": 0, "maximum": 100},
    "reasons": {"type": "array", "items": {"type": "string"}},
    "summary": {"type": "string", "maxLength": 200},
    "service_impact": {"type": "string", "enum": ["high", "medium", "low"]},
    "training_value": {"type": "string", "enum": ["high", "medium", "low"]},
    "customer_relevance": {"type": "boolean"}
  },
  "required": ["suitable_for_kb", "confidence_score", "reasons", "summary"]
}'
WHERE business_category = 'retail_announcement';
```

## 使用说明

### 1. 添加新知识库

```python
from models import KnowledgeBase
from database import get_db_session

db = get_db_session()
new_kb = KnowledgeBase(
    name="风险管理知识库",
    description="专门存储风险管理相关文档",
    dify_dataset_id="risk-dataset-001"
)
db.add(new_kb)
db.commit()
```

### 2. 配置分类映射

```python
from models import DocumentCategoryMapping, BusinessCategory

mapping = DocumentCategoryMapping(
    knowledge_base_id=new_kb.id,
    business_category=BusinessCategory.HEADQUARTERS_ISSUE,
    min_confidence_score=80,
    auto_approve_threshold=90
)
db.add(mapping)
db.commit()
```

### 3. 测试AI分析

```python
from services.ai_analyzer import ai_analyzer

file_info = {
    'imagefileid': 'test-001',
    'business_category': BusinessCategory.RETAIL_ANNOUNCEMENT,
    'imagefilename': 'test.pdf'
}

metadata = {
    'file_type': 'pdf',
    'chunks_count': 5,
    'parsing_method': 'api_interface'
}

result, target_kb = ai_analyzer.analyze_document_content(
    content="测试文档内容...",
    filename="test.pdf",
    file_info=file_info,
    metadata=metadata
)
```

## 注意事项

1. **metadata参数**: 来自文档解析服务，包含文件类型、分块数量等技术信息
2. **file_info参数**: 来自数据库，包含业务分类、文件ID等业务信息
3. **不要让AI判断文档分类**: 业务分类已经在数据库中确定
4. **JSON输出方式**: 根据使用的AI模型选择合适的输出控制方式
5. **分类特定字段**: 每种分类都有特定的分析维度，便于后续扩展 