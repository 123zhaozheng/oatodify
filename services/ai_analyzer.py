import json
import os
from typing import Dict, Optional
import logging
from openai import OpenAI
from config import settings

logger = logging.getLogger(__name__)

class AIAnalyzer:
    """AI文档分析服务"""
    
    def __init__(self):
        self.client = None
        self.model_name = settings.openai_model_name
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
    
    def analyze_document_content(self, content: str, filename: str, metadata: Dict) -> Dict:
        """
        分析文档内容是否适合加入知识库
        
        Args:
            content: 文档内容
            filename: 文件名
            metadata: 文档元数据
            
        Returns:
            Dict: 分析结果
        """
        try:
            if not self.client:
                logger.warning("OpenAI客户端未初始化，使用规则分析")
                return self._rule_based_analysis(content, filename, metadata)
            
            # 准备分析prompt
            prompt = self._build_analysis_prompt(content, filename, metadata)
            
            # 调用GPT-5进行分析
            # the newest OpenAI model is "gpt-5" which was released August 7, 2025.
            # do not change this unless explicitly requested by the user
            response = self.client.chat.completions.create(
                model=self.model_name,
                messages=[
                    {
                        "role": "system",
                        "content": "你是一个专业的文档分析专家，负责评估文档是否适合加入企业知识库。"
                        + "请根据文档内容、结构、价值和完整性进行综合评估。"
                        + "返回JSON格式的分析结果。"
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                response_format={"type": "json_object"},
                temperature=0.3,
                max_tokens=800
            )
            
            # 解析响应
            content = response.choices[0].message.content or "{}"
            result = json.loads(content)
            
            # 标准化结果格式
            analysis_result = {
                "suitable_for_kb": result.get("suitable_for_kb", False),
                "confidence_score": max(0, min(100, result.get("confidence_score", 0))),
                "category": result.get("category", "unknown"),
                "reasons": result.get("reasons", []),
                "summary": result.get("summary", ""),
                "key_topics": result.get("key_topics", []),
                "quality_score": max(0, min(100, result.get("quality_score", 50))),
                "completeness": result.get("completeness", "unknown"),
                "analysis_method": "ai",
                "model_version": self.model_name
            }
            
            logger.info(f"AI分析完成，适合知识库: {analysis_result['suitable_for_kb']}, "
                       f"置信度: {analysis_result['confidence_score']}")
            
            return analysis_result
            
        except Exception as e:
            logger.error(f"AI分析失败: {e}")
            # 降级到规则分析
            return self._rule_based_analysis(content, filename, metadata)
    
    def _build_analysis_prompt(self, content: str, filename: str, metadata: Dict) -> str:
        """构建分析提示词"""
        
        # 截取内容前2000字符用于分析
        content_preview = content[:2000] + "..." if len(content) > 2000 else content
        
        prompt = f"""
请分析以下文档是否适合加入企业知识库：

文件名: {filename}
文档类型: {metadata.get('file_type', 'unknown')}
内容长度: {len(content)} 字符
页数/段落数: {metadata.get('pages', metadata.get('paragraphs', 'unknown'))}

文档内容预览:
{content_preview}

请从以下维度进行评估并返回JSON格式结果：
1. suitable_for_kb: 是否适合加入知识库 (true/false)
2. confidence_score: 置信度 (0-100)
3. category: 文档类别 (contract/policy/report/manual/notice/other)
4. reasons: 判断理由列表
5. summary: 文档内容摘要 (50字以内)
6. key_topics: 关键主题列表 (最多5个)
7. quality_score: 内容质量评分 (0-100)
8. completeness: 内容完整性 (complete/partial/fragment)

评估标准：
- 内容是否有价值和参考意义
- 结构是否完整清晰
- 信息是否准确可靠
- 是否包含敏感或机密信息
- 语言表达是否规范
"""
        
        return prompt
    
    def _rule_based_analysis(self, content: str, filename: str, metadata: Dict) -> Dict:
        """基于规则的文档分析（AI不可用时的降级方案）"""
        
        logger.info("使用基于规则的分析方法")
        
        suitable = True
        confidence = 60  # 规则分析的置信度较低
        reasons = []
        category = "other"
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
        
        # 关键词分析
        content_lower = content.lower()
        
        # 分类关键词
        category_keywords = {
            'contract': ['合同', '协议', '甲方', '乙方', 'contract', 'agreement'],
            'policy': ['政策', '制度', '规定', '管理办法', 'policy', 'regulation'],
            'report': ['报告', '分析', '总结', '统计', 'report', 'analysis'],
            'manual': ['手册', '指南', '操作', '使用说明', 'manual', 'guide'],
            'notice': ['通知', '公告', '通告', 'notice', 'announcement']
        }
        
        for cat, keywords in category_keywords.items():
            for keyword in keywords:
                if keyword in content_lower or keyword in filename_lower:
                    category = cat
                    quality_score += 5
                    reasons.append(f"识别为{cat}类文档")
                    break
        
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
        
        # 生成摘要（取前50个字符）
        summary = content.strip()[:50] + "..." if len(content.strip()) > 50 else content.strip()
        
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
            "category": category,
            "reasons": reasons,
            "summary": summary,
            "key_topics": key_topics,
            "quality_score": quality_score,
            "completeness": completeness,
            "analysis_method": "rule_based",
            "model_version": "rule_v1.0"
        }

# 创建全局实例
ai_analyzer = AIAnalyzer()
