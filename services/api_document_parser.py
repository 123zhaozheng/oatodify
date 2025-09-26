import requests
import logging
from typing import Dict, List, Optional
from config import settings

logger = logging.getLogger(__name__)

class ApiDocumentParser:
    """通过接口进行文档解析的服务类"""

    def __init__(self):
        # 从配置中获取文档解析接口的基础URL
        self.parse_api_url = getattr(settings, 'document_parse_api_url', None)
        if not self.parse_api_url:
            logger.warning("未配置document_parse_api_url，将使用默认的解析接口")
            # 如果没有配置，使用一个默认值（需要用户在.env中配置实际地址）
            self.parse_api_url = "http://localhost:8080"

        # 文档解析配置
        self.default_separators = ["\n\n", "\n", ".", ""]
        self.default_separator_rules = ["after", "after", "after", "after"]
        self.default_chunk_size = 1000
        self.default_chunk_overlap = 200

        # AI解析文本长度限制（字符数）
        self.ai_analysis_max_length = getattr(settings, 'ai_analysis_max_length', 50000)

    def parse_document(self, file_data: bytes, filename: str) -> Dict:
        """
        通过接口解析文档内容

        Args:
            file_data: 文件二进制数据
            filename: 文件名

        Returns:
            Dict: 包含解析结果的字典
        """
        try:
            logger.info(f"通过接口解析文档: {filename}")

            # 准备请求参数
            url = f"{self.parse_api_url.rstrip('/')}/upload-document/"

            files = {
                'file': (filename, file_data, 'application/octet-stream')
            }

            data = {
                'separators': str(self.default_separators),  # 转换为字符串
                'separator_rules': str(self.default_separator_rules),
                'chunk_size': self.default_chunk_size,
                'chunk_overlap': self.default_chunk_overlap,
                'is_separator_regex': False,
                'keep_separator': True
            }

            logger.info(f"发送请求到: {url}")
            logger.info(f"请求参数: {data}")

            # 发送请求
            response = requests.post(url, files=files, data=data, timeout=120)

            if response.status_code == 200:
                result = response.json()
                logger.info(f"文档解析成功: {filename}")

                # 提取文本块内容
                chunks = result.get('chunks', [])
                if not chunks:
                    logger.warning(f"解析结果中没有文本块: {filename}")
                    return {
                        'success': False,
                        'error': '解析结果中没有文本块',
                        'file_type': result.get('file_type', 'unknown'),
                        'content': '',
                        'metadata': {}
                    }

                # 拼接所有文本块内容
                full_content = self._concatenate_chunks(chunks)

                if len(full_content) > self.ai_analysis_max_length:
                    logger.info(f"文档内容过长({len(full_content)}字符)，仅截取前{self.ai_analysis_max_length}字符供AI分析参考，不影响知识库入库")

                # 构造元数据
                metadata = {
                    'chunks_count': len(chunks),
                    'total_length': len(full_content),
                    'file_type': result.get('file_type', 'unknown'),
                    'parsing_method': 'api_interface',
                    'api_response': {
                        'filename': result.get('filename', filename),
                        'file_type': result.get('file_type'),
                        'chunks_count': len(chunks)
                    }
                }

                # 如果有表格信息，添加到元数据
                if chunks and 'metadata' in chunks[0]:
                    first_chunk_metadata = chunks[0]['metadata']
                    if 'sheet_name' in first_chunk_metadata:
                        metadata['sheet_name'] = first_chunk_metadata['sheet_name']

                return {
                    'success': True,
                    'file_type': result.get('file_type', 'unknown'),
                    'content': full_content,
                    'metadata': metadata,
                    'content_length': len(full_content),
                    'error': None
                }

            else:
                error_msg = f"文档解析API请求失败: HTTP {response.status_code} - {response.text}"
                logger.error(error_msg)
                return {
                    'success': False,
                    'error': error_msg,
                    'file_type': 'unknown',
                    'content': '',
                    'metadata': {}
                }

        except requests.exceptions.Timeout:
            error_msg = f"文档解析API请求超时: {filename}"
            logger.error(error_msg)
            return {
                'success': False,
                'error': error_msg,
                'file_type': 'unknown',
                'content': '',
                'metadata': {}
            }
        except requests.exceptions.RequestException as e:
            error_msg = f"文档解析API网络错误: {str(e)}"
            logger.error(error_msg)
            return {
                'success': False,
                'error': error_msg,
                'file_type': 'unknown',
                'content': '',
                'metadata': {}
            }
        except Exception as e:
            error_msg = f"文档解析失败: {str(e)}"
            logger.error(error_msg)
            import traceback
            traceback.print_exc()
            return {
                'success': False,
                'error': error_msg,
                'file_type': 'unknown',
                'content': '',
                'metadata': {}
            }

    def _concatenate_chunks(self, chunks: List[Dict]) -> str:
        """
        将文本块拼接成完整文本

        Args:
            chunks: 文本块列表

        Returns:
            str: 拼接后的完整文本
        """
        if not chunks:
            return ""

        content_parts = []

        for chunk in chunks:
            chunk_content = chunk.get('content', '')
            if chunk_content.strip():
                content_parts.append(chunk_content.strip())

        # 使@@@@@符连接文本块，保持dify父切分连续性
        full_content = '@@@@@'.join(content_parts)

        logger.info(f"拼接完成，共{len(chunks)}个文本块，总长度{len(full_content)}字符")

        return full_content

    def is_suitable_for_knowledge_base(self, content: str, filename: str) -> bool:
        """
        基于简单规则判断文档是否适合加入知识库
        """
        try:
            # 文件名黑名单
            blacklist_keywords = [
                'test', 'temp', 'backup', 'log', 'cache',
                '测试', '临时', '备份', '日志', '缓存'
            ]

            filename_lower = filename.lower()
            for keyword in blacklist_keywords:
                if keyword in filename_lower:
                    return False

            # 内容长度检查
            if len(content.strip()) < 100:  # 内容太短
                return False

            if len(content.strip()) > 100000:  # 内容太长
                return False

            # 内容质量检查
            lines = content.split('\n')
            non_empty_lines = [line for line in lines if line.strip()]

            if len(non_empty_lines) < 5:  # 有效行数太少
                return False

            return True

        except Exception as e:
            logger.error(f"适用性检查失败: {e}")
            return False

# 创建全局实例
api_document_parser = ApiDocumentParser()