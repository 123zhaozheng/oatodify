#!/usr/bin/env python3
"""
测试新的接口文档解析流程
"""

import os
import sys
import logging

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from services.api_document_parser import api_document_parser
from services.dify_service import dify_service
from config import settings

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def test_api_parser():
    """测试API文档解析器"""

    # 创建一个简单的测试文档
    test_content = """
这是一个测试文档。

第一段内容：这里包含了一些基本信息。

第二段内容：
- 列表项1
- 列表项2
- 列表项3

第三段内容：包含一些详细的说明文字，用于测试文档解析功能是否正常工作。
这段文字比较长，用来验证文本拼接和长度控制功能。

结论：这是测试文档的结束部分。
""".strip()

    # 将文本内容转换为字节
    test_data = test_content.encode('utf-8')
    test_filename = "test_document.txt"

    logger.info("开始测试API文档解析...")
    logger.info(f"测试文档大小: {len(test_data)} 字节")
    logger.info(f"配置的解析API地址: {api_document_parser.parse_api_url}")

    # 测试解析
    result = api_document_parser.parse_document(test_data, test_filename)

    if result['success']:
        logger.info("✅ 文档解析成功!")
        logger.info(f"文件类型: {result['file_type']}")
        logger.info(f"内容长度: {result['content_length']} 字符")
        logger.info(f"元数据: {result['metadata']}")
        logger.info(f"解析后的内容预览: {result['content'][:200]}...")

        # 测试适用性检查
        suitable = api_document_parser.is_suitable_for_knowledge_base(
            result['content'], test_filename
        )
        logger.info(f"适合加入知识库: {suitable}")

        return result
    else:
        logger.error("❌ 文档解析失败!")
        logger.error(f"错误信息: {result['error']}")
        return None

def test_dify_integration(parsed_content):
    """测试Dify集成"""
    if not parsed_content:
        logger.error("没有解析内容，跳过Dify测试")
        return

    logger.info("开始测试Dify集成...")
    logger.info(f"Dify API配置: {settings.dify_base_url}")
    logger.info(f"数据集ID: {settings.dify_dataset_id}")

    if not settings.dify_api_key:
        logger.warning("⚠️ 未配置Dify API密钥，跳过实际上传测试")
        return

    # 测试连接
    connection_result = dify_service.check_api_connection()
    if connection_result['success']:
        logger.info("✅ Dify API连接正常")
    else:
        logger.error(f"❌ Dify API连接失败: {connection_result['error']}")
        return

    # 模拟添加到知识库（使用测试标记）
    test_metadata = {
        'file_id': 'test_file_123',
        'analysis_result': {
            'suitable_for_kb': True,
            'confidence_score': 95,
            'analysis_method': 'test'
        }
    }

    logger.info("测试文本方式添加到知识库...")
    dify_result = dify_service.add_document_to_knowledge_base_by_text(
        parsed_content['content'],
        f"[TEST] {parsed_content.get('metadata', {}).get('api_response', {}).get('filename', 'test_doc.txt')}",
        test_metadata
    )

    if dify_result['success']:
        logger.info("✅ 文档成功添加到Dify知识库!")
        logger.info(f"文档ID: {dify_result['document_id']}")
        return dify_result['document_id']
    else:
        logger.error(f"❌ 文档添加失败: {dify_result['error']}")
        return None

def main():
    """主测试函数"""
    logger.info("=" * 50)
    logger.info("开始测试新的接口文档解析流程")
    logger.info("=" * 50)

    # 显示当前配置
    logger.info("当前配置:")
    logger.info(f"  - 文档解析API: {getattr(settings, 'document_parse_api_url', '未配置')}")
    logger.info(f"  - AI分析最大长度: {getattr(settings, 'ai_analysis_max_length', 50000)} 字符")
    logger.info(f"  - Dify API: {settings.dify_base_url}")
    logger.info(f"  - Dify数据集: {settings.dify_dataset_id}")
    logger.info("")

    # 测试解析
    parsed_result = test_api_parser()

    if parsed_result:
        logger.info("")
        logger.info("=" * 30)
        logger.info("测试Dify集成")
        logger.info("=" * 30)

        # 测试Dify集成
        doc_id = test_dify_integration(parsed_result)

        if doc_id:
            logger.info(f"✅ 完整流程测试成功! 文档ID: {doc_id}")
        else:
            logger.warning("⚠️ 解析成功但Dify集成测试失败")
    else:
        logger.error("❌ 解析测试失败，无法继续测试Dify集成")

    logger.info("")
    logger.info("=" * 50)
    logger.info("测试完成")
    logger.info("=" * 50)

if __name__ == "__main__":
    main()