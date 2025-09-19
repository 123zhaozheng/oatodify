import json
import os
from typing import Dict, Optional, Tuple
import logging
from openai import OpenAI
from sqlalchemy.orm import Session
from config import settings
from models import BusinessCategory, DocumentCategoryMapping, KnowledgeBase
from database import get_db

logger = logging.getLogger(__name__)

class DocumentProcessor:
    """文档处理器基类 - 每种业务分类对应特定的AI处理逻辑"""
    
    def __init__(self, category: BusinessCategory, mapping_config: Dict):
        self.category = category
        self.mapping_config = mapping_config
        self.prompt_template = mapping_config.get('ai_prompt_template', '')
        self.output_schema = mapping_config.get('ai_output_schema', '{}')
        self.min_confidence = mapping_config.get('min_confidence_score', 70)
        self.auto_approve_threshold = mapping_config.get('auto_approve_threshold', 90)
        
        # 从环境变量读取JSON输出控制方式
        self.json_output_method = os.getenv('AI_JSON_OUTPUT_METHOD', 'response_format')  # 'response_format' 或 'prompt'
    
    def get_prompt(self, content: str, filename: str, file_info: Dict, metadata: Dict) -> str:
        """获取特定分类的AI提示词"""
        if self.prompt_template:
            # 使用数据库配置的提示词模板
            return self.prompt_template.format(
                filename=filename,
                content=content[:2000] + "..." if len(content) > 2000 else content,
                file_type=metadata.get('file_type', 'unknown'),
                content_length=len(content),
                category=self.category.value,
                chunks_count=metadata.get('chunks_count', 'unknown'),
                parsing_method=metadata.get('parsing_method', 'unknown'),
                business_category=file_info.get('business_category', 'unknown'),
                file_id=file_info.get('imagefileid', 'unknown')
            )
        
        # 使用默认提示词模板
        return self._get_default_prompt(content, filename, file_info, metadata)
    
    def get_output_schema(self) -> Dict:
        """获取特定分类的输出格式定义"""
        try:
            if self.output_schema:
                return json.loads(self.output_schema)
            else:
                return self._get_default_schema()
        except json.JSONDecodeError:
            logger.warning(f"分类 {self.category} 的输出格式定义解析失败，使用默认格式")
            return self._get_default_schema()
    
    def _get_default_prompt(self, content: str, filename: str, file_info: Dict, metadata: Dict) -> str:
        """获取默认提示词"""
        content_preview = content[:2000] + "..." if len(content) > 2000 else content
        
        # 根据JSON输出方式调整提示词
        json_instruction = ""
        if self.json_output_method == 'prompt':
            # 在提示词中限定JSON模板
            schema = self.get_output_schema()
            json_instruction = f"""
请严格按照以下JSON格式返回结果：
{json.dumps(schema, ensure_ascii=False, indent=2)}
"""
        else:
            # 使用response_format参数
            json_instruction = "请返回JSON格式的分析结果。"
        
        base_prompt = f"""
你是一个专业的{self.category.value}类型文档分析专家。

文档信息：
- 文件名: {filename}
- 文档类型: {metadata.get('file_type', 'unknown')}
- 内容长度: {len(content)} 字符
- 文档分块数: {metadata.get('chunks_count', 'unknown')}
- 解析方式: {metadata.get('parsing_method', 'unknown')}
- 业务分类: {self.category.value} (已确定，无需重新判断)

文档内容预览:
{content_preview}

请分析这个{self.category.value}类型的文档是否适合加入企业知识库。

{self._get_category_specific_analysis_requirements()}

{json_instruction}
"""
        return base_prompt
    
    def _get_default_schema(self) -> Dict:
        """获取默认输出格式 - 根据分类定制"""
        base_schema = {
            "type": "object",
            "properties": {
                "suitable_for_kb": {"type": "boolean", "description": "是否适合加入知识库"},
                "confidence_score": {"type": "integer", "minimum": 0, "maximum": 100, "description": "置信度"},
                "reasons": {"type": "array", "items": {"type": "string"}, "description": "判断理由列表"},
                "summary": {"type": "string", "maxLength": 150, "description": "文档内容摘要"},
                "key_topics": {"type": "array", "items": {"type": "string"}, "maxItems": 8, "description": "关键主题"},
                "quality_score": {"type": "integer", "minimum": 0, "maximum": 100, "description": "内容质量评分"},
                "completeness": {"type": "string", "enum": ["complete", "partial", "fragment"], "description": "内容完整性"}
            },
            "required": ["suitable_for_kb", "confidence_score", "reasons", "summary"]
        }
        
        # 根据不同分类添加特定字段
        category_specific_fields = self._get_category_specific_fields()
        if category_specific_fields:
            base_schema["properties"].update(category_specific_fields)
            
        return base_schema
    
    def _get_category_specific_analysis_requirements(self) -> str:
        """获取分类特定的分析要求"""
        requirements_map = {
            BusinessCategory.HEADQUARTERS_ISSUE: """
分析要求：
1. 重点评估政策指导价值和权威性
2. 关注对分支机构的实用性
3. 评估制度规范的完整性和可操作性
4. 注意文件的时效性和适用范围

重点关注字段：
- policy_level: 政策层级 (strategic/operational/guidance)
- target_audience: 目标受众 (all_branches/specific_departments/management)
- implementation_difficulty: 执行难度 (low/medium/high)
            """,
            BusinessCategory.RETAIL_ANNOUNCEMENT: """
分析要求：
1. 评估零售业务操作指导的实用性
2. 关注客户服务改进价值
3. 分析产品营销策略的可复制性
4. 评估合规要求的明确性

重点关注字段：
- service_impact: 服务影响 (customer_facing/internal_process/both)
- product_relevance: 产品相关性 (high/medium/low)
- training_value: 培训价值 (high/medium/low)
            """,
            BusinessCategory.PUBLICATION_RELEASE: """
分析要求：
1. 评估信息的准确性和完整性
2. 关注知识传播和学习价值
3. 分析内容的参考价值和可引用性
4. 注意版权和引用规范

重点关注字段：
- information_type: 信息类型 (news/analysis/case_study/research)
- reference_value: 参考价值 (high/medium/low)
- knowledge_depth: 知识深度 (basic/intermediate/advanced)
            """,
            BusinessCategory.BRANCH_ISSUE: """
分析要求：
1. 评估本地化经验的推广价值
2. 关注最佳实践的可复制性
3. 分析地域适用性和普适性
4. 评估创新做法的借鉴意义

重点关注字段：
- innovation_level: 创新程度 (high/medium/low)
- replicability: 可复制性 (high/medium/low)
- regional_specificity: 地域特殊性 (high/medium/low)
            """,
            BusinessCategory.BRANCH_RECEIVE: """
分析要求：
1. 评估执行指导的完整性和清晰度
2. 关注操作流程的标准化程度
3. 分析合规要求的明确性
4. 评估执行效果的可衡量性

重点关注字段：
- execution_clarity: 执行清晰度 (clear/moderate/unclear)
- compliance_level: 合规程度 (mandatory/recommended/optional)
- measurability: 可衡量性 (quantifiable/qualitative/subjective)
            """,
            BusinessCategory.PUBLIC_STANDARD: """
分析要求：
1. 评估标准化内容的权威性
2. 关注规范的适用范围和实用性
3. 分析操作指导的详细程度
4. 评估制度的可执行性

重点关注字段：
- standard_type: 标准类型 (technical/procedural/management)
- authority_level: 权威程度 (regulatory/industry/internal)
- detail_level: 详细程度 (comprehensive/moderate/basic)
            """,
            BusinessCategory.HEADQUARTERS_RECEIVE: """
分析要求：
1. 评估上级指导的重要性和紧急性
2. 关注政策解读的准确性
3. 分析执行要求的明确性
4. 评估文档的权威性来源

重点关注字段：
- urgency_level: 紧急程度 (urgent/normal/low)
- authority_source: 权威来源 (regulatory/supervisory/industry)
- action_required: 需要行动 (immediate/planned/informational)
            """,
            BusinessCategory.CORPORATE_ANNOUNCEMENT: """
分析要求：
1. 评估公司业务指导的实用性
2. 关注对公客户服务的改进价值
3. 分析业务流程优化的可行性
4. 评估风险控制措施的有效性

重点关注字段：
- business_impact: 业务影响 (high/medium/low)
- client_focus: 客户导向 (b2b_focused/internal_process/mixed)
- risk_relevance: 风险相关性 (high/medium/low)
            """
        }
        return requirements_map.get(self.category, "- 按照通用标准进行评估")
    
    def _get_category_specific_fields(self) -> Dict:
        """获取分类特定的输出字段"""
        fields_map = {
            BusinessCategory.HEADQUARTERS_ISSUE: {
                "policy_level": {"type": "string", "enum": ["strategic", "operational", "guidance"]},
                "target_audience": {"type": "string", "enum": ["all_branches", "specific_departments", "management"]},
                "implementation_difficulty": {"type": "string", "enum": ["low", "medium", "high"]}
            },
            BusinessCategory.RETAIL_ANNOUNCEMENT: {
                "service_impact": {"type": "string", "enum": ["customer_facing", "internal_process", "both"]},
                "product_relevance": {"type": "string", "enum": ["high", "medium", "low"]},
                "training_value": {"type": "string", "enum": ["high", "medium", "low"]}
            },
            BusinessCategory.PUBLICATION_RELEASE: {
                "information_type": {"type": "string", "enum": ["news", "analysis", "case_study", "research"]},
                "reference_value": {"type": "string", "enum": ["high", "medium", "low"]},
                "knowledge_depth": {"type": "string", "enum": ["basic", "intermediate", "advanced"]}
            },
            BusinessCategory.BRANCH_ISSUE: {
                "innovation_level": {"type": "string", "enum": ["high", "medium", "low"]},
                "replicability": {"type": "string", "enum": ["high", "medium", "low"]},
                "regional_specificity": {"type": "string", "enum": ["high", "medium", "low"]}
            },
            BusinessCategory.BRANCH_RECEIVE: {
                "execution_clarity": {"type": "string", "enum": ["clear", "moderate", "unclear"]},
                "compliance_level": {"type": "string", "enum": ["mandatory", "recommended", "optional"]},
                "measurability": {"type": "string", "enum": ["quantifiable", "qualitative", "subjective"]}
            },
            BusinessCategory.PUBLIC_STANDARD: {
                "standard_type": {"type": "string", "enum": ["technical", "procedural", "management"]},
                "authority_level": {"type": "string", "enum": ["regulatory", "industry", "internal"]},
                "detail_level": {"type": "string", "enum": ["comprehensive", "moderate", "basic"]}
            },
            BusinessCategory.HEADQUARTERS_RECEIVE: {
                "urgency_level": {"type": "string", "enum": ["urgent", "normal", "low"]},
                "authority_source": {"type": "string", "enum": ["regulatory", "supervisory", "industry"]},
                "action_required": {"type": "string", "enum": ["immediate", "planned", "informational"]}
            },
            BusinessCategory.CORPORATE_ANNOUNCEMENT: {
                "business_impact": {"type": "string", "enum": ["high", "medium", "low"]},
                "client_focus": {"type": "string", "enum": ["b2b_focused", "internal_process", "mixed"]},
                "risk_relevance": {"type": "string", "enum": ["high", "medium", "low"]}
            }
        }
        return fields_map.get(self.category, {})

class AIAnalyzer:
    """增强版AI文档分析服务 - 支持分类特定的处理逻辑"""
    
    def __init__(self):
        self.client = None
        self.model_name = settings.openai_model_name
        self.processors = {}  # 文档处理器缓存
        self._init_client()
    
    def _init_client(self):
        """初始化OpenAI客户端"""
        try:
            api_key = settings.openai_api_key
            if not api_key:
                logger.error("未配置OPENAI_API_KEY")
                return
            
            # 构建客户端参数
            client_kwargs = {"api_key": api_key}
            
            # 如果配置了自定义base_url，则使用自定义URL
            if settings.openai_base_url:
                client_kwargs["base_url"] = settings.openai_base_url
                logger.info(f"使用自定义OpenAI URL: {settings.openai_base_url}")
            
            self.client = OpenAI(**client_kwargs)
            logger.info(f"OpenAI客户端初始化成功，模型: {self.model_name}")
            
        except Exception as e:
            logger.error(f"OpenAI客户端初始化失败: {e}")
    
    def get_document_processor(self, category: BusinessCategory, db: Session) -> DocumentProcessor:
        """获取文档处理器"""
        if category not in self.processors:
            # 从数据库获取映射配置
            mapping = db.query(DocumentCategoryMapping).filter(
                DocumentCategoryMapping.business_category == category,
                DocumentCategoryMapping.is_active == True
            ).first()
            
            if mapping:
                mapping_config = {
                    'ai_prompt_template': mapping.ai_prompt_template,
                    'ai_output_schema': mapping.ai_output_schema,
                    'min_confidence_score': mapping.min_confidence_score,
                    'auto_approve_threshold': mapping.auto_approve_threshold
                }
            else:
                logger.warning(f"未找到分类 {category} 的映射配置，使用默认配置")
                mapping_config = {}
            
            self.processors[category] = DocumentProcessor(category, mapping_config)
        
        return self.processors[category]
    
    def get_target_knowledge_base(self, category: BusinessCategory, db: Session) -> Optional[KnowledgeBase]:
        """获取目标知识库"""
        mapping = db.query(DocumentCategoryMapping).filter(
            DocumentCategoryMapping.business_category == category,
            DocumentCategoryMapping.is_active == True
        ).first()
        
        if mapping and mapping.knowledge_base.status == 'active':
            return mapping.knowledge_base
        
        # 如果没有找到特定映射，返回默认知识库
        default_kb = db.query(KnowledgeBase).filter(
            KnowledgeBase.status == 'active'
        ).first()
        
        if default_kb:
            logger.info(f"分类 {category} 使用默认知识库: {default_kb.name}")
        
        return default_kb
    
    def analyze_document_content(self, content: str, filename: str, file_info: Dict, metadata: Dict) -> Tuple[Dict, Optional[KnowledgeBase]]:
        """
        分析文档内容是否适合加入知识库，并返回目标知识库
        
        Args:
            content: 文档内容
            filename: 文件名
            file_info: 文件信息字典(包含imagefileid, business_category等数据库字段)
            metadata: 文档解析元数据(包含file_type, chunks_count, parsing_method等)
            
        Returns:
            Tuple[Dict, Optional[KnowledgeBase]]: (分析结果, 目标知识库)
        """
        try:
            # 获取业务分类(从数据库文件信息中获取，不需要AI判断)
            category = file_info.get('business_category')
            if not category:
                logger.error("文件信息中缺少business_category")
                return self._rule_based_analysis(content, filename, file_info, metadata), None
            
            if isinstance(category, str):
                try:
                    category = BusinessCategory(category)
                except ValueError:
                    logger.error(f"无效的业务分类: {category}")
                    return self._rule_based_analysis(content, filename, file_info, metadata), None
            
            # 获取数据库会话
            db = next(get_db())
            
            try:
                # 获取文档处理器和目标知识库
                processor = self.get_document_processor(category, db)
                target_kb = self.get_target_knowledge_base(category, db)
                
                if not self.client:
                    logger.warning("OpenAI客户端未初始化，使用规则分析")
                    return self._rule_based_analysis(content, filename, file_info, metadata), target_kb
                
                # 获取特定分类的提示词
                prompt = processor.get_prompt(content, filename, file_info, metadata)
                
                # 构建消息
                messages = [
                    {
                        "role": "system",
                        "content": f"你是一个专业的{category.value}类型文档分析专家，负责评估文档是否适合加入企业知识库。请根据文档内容、结构、价值和完整性进行综合评估。"
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ]
                
                # 根据JSON输出方式调用不同的API
                if processor.json_output_method == 'response_format':
                    # 使用response_format参数控制JSON输出
                    response = self.client.chat.completions.create(
                        model=self.model_name,
                        messages=messages,
                        response_format={"type": "json_object"},
                        temperature=0.3,
                        max_tokens=1200
                    )
                else:
                    # 使用提示词控制JSON输出
                    response = self.client.chat.completions.create(
                        model=self.model_name,
                        messages=messages,
                        temperature=0.3,
                        max_tokens=1200
                    )
                
                # 解析响应
                content_result = response.choices[0].message.content or "{}"
                result = json.loads(content_result)
                
                # 标准化结果格式
                analysis_result = {
                    "suitable_for_kb": result.get("suitable_for_kb", False),
                    "confidence_score": max(0, min(100, result.get("confidence_score", 0))),
                    "reasons": result.get("reasons", []),
                    "summary": result.get("summary", ""),
                    "key_topics": result.get("key_topics", []),
                    "quality_score": max(0, min(100, result.get("quality_score", 50))),
                    "completeness": result.get("completeness", "unknown"),
                    "analysis_method": "ai",
                    "model_version": self.model_name,
                    "json_output_method": processor.json_output_method,
                    "processor_config": {
                        "category": category.value,
                        "min_confidence": processor.min_confidence,
                        "auto_approve_threshold": processor.auto_approve_threshold
                    }
                }
                
                # 添加分类特定的字段
                category_fields = processor._get_category_specific_fields()
                for field_name in category_fields.keys():
                    if field_name in result:
                        analysis_result[field_name] = result[field_name]
                
                # 应用分类特定的质量控制
                if analysis_result["confidence_score"] < processor.min_confidence:
                    analysis_result["suitable_for_kb"] = False
                    analysis_result["reasons"].append(f"置信度低于阈值 {processor.min_confidence}")
                
                logger.info(f"AI分析完成 [分类: {category.value}]，适合知识库: {analysis_result['suitable_for_kb']}, "
                           f"置信度: {analysis_result['confidence_score']}, 目标知识库: {target_kb.name if target_kb else 'None'}")
                
                return analysis_result, target_kb
                
            finally:
                db.close()
            
        except Exception as e:
            logger.error(f"AI分析失败: {e}")
            # 降级到规则分析
            return self._rule_based_analysis(content, filename, file_info, metadata), None
    
    def _rule_based_analysis(self, content: str, filename: str, file_info: Dict, metadata: Dict) -> Dict:
        """基于规则的文档分析（AI不可用时的降级方案）"""
        
        logger.info("使用基于规则的分析方法")
        
        suitable = True
        confidence = 60  # 规则分析的置信度较低
        reasons = []
        category = file_info.get('business_category', 'public_standard')
        if hasattr(category, 'value'):
            category = category.value
        quality_score = 50
        
        # 文件名分析
        filename_lower = filename.lower()
        
        # 黑名单关键词
        blacklist_keywords = [
            'test', 'temp', 'backup', 'log', 'cache', 'debug',
            '测试', '临时', '备份', '日志', '缓存', '调试'
        ]
        
        for keyword in blacklist_keywords:
            if keyword in filename_lower:
                suitable = False
                reasons.append(f"文件名包含黑名单关键词: {keyword}")
                confidence = max(confidence - 20, 10)
        
        # 内容长度分析
        content_length = len(content.strip())
        if content_length < 100:
            suitable = False
            reasons.append("内容过短，缺乏实质性信息")
            confidence = max(confidence - 30, 10)
        elif content_length > 50000:
            reasons.append("内容较长，需要人工审核")
            confidence = max(confidence - 10, 30)
        
        # 文档类型分析
        file_type = metadata.get('file_type', 'unknown')
        if file_type in ['pdf', 'docx', 'doc']:
            quality_score += 10
            reasons.append("标准文档格式")
        elif file_type == 'txt':
            quality_score -= 5
            reasons.append("纯文本格式，结构化程度较低")
        
        # 内容质量评估
        lines = content.split('\n')
        non_empty_lines = [line for line in lines if line.strip()]
        
        if len(non_empty_lines) < 5:
            suitable = False
            reasons.append("有效行数过少")
            quality_score -= 20
        
        # 敏感信息检测
        sensitive_keywords = [
            '密码', '秘密', '机密', '私人', '个人信息',
            'password', 'secret', 'confidential', 'private'
        ]
        
        content_lower = content.lower()
        for keyword in sensitive_keywords:
            if keyword in content_lower:
                suitable = False
                reasons.append("可能包含敏感信息")
                confidence = max(confidence - 25, 10)
                break
        
        # 提取关键主题（简单实现）
        key_topics = []
        common_words = content_lower.split()
        word_freq = {}
        for word in common_words:
            if len(word) > 3:  # 只考虑长度大于3的词
                word_freq[word] = word_freq.get(word, 0) + 1
        
        # 获取出现频率最高的前5个词作为关键主题
        sorted_words = sorted(word_freq.items(), key=lambda x: x[1], reverse=True)
        key_topics = [word for word, freq in sorted_words[:5] if freq > 1]
        
        # 生成摘要（取前150个字符）
        summary = content.strip()[:150] + "..." if len(content.strip()) > 150 else content.strip()
        
        # 完整性评估
        completeness = "complete"
        if content_length < 500:
            completeness = "fragment"
        elif content_length < 2000:
            completeness = "partial"
        
        if not reasons:
            reasons.append("通过基本规则检查")
        
        return {
            "suitable_for_kb": suitable,
            "confidence_score": confidence,
            "reasons": reasons,
            "summary": summary,
            "key_topics": key_topics,
            "quality_score": quality_score,
            "completeness": completeness,
            "analysis_method": "rule_based",
            "model_version": "rule_v2.0",
            "json_output_method": "rule_based"
        }

# 创建全局实例
ai_analyzer = AIAnalyzer()
