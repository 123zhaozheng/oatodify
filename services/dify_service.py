import requests
import json
import logging
import tempfile
import os
from typing import Dict, Optional
from config import settings

logger = logging.getLogger(__name__)

class DifyService:
    """Dify知识库集成服务"""
    
    def __init__(self):
        self.api_key = settings.dify_api_key
        self.base_url = settings.dify_base_url.rstrip('/')
        self.dataset_id = settings.dify_dataset_id
        self.session = requests.Session()
        
        if self.api_key:
            self.session.headers.update({
                'Authorization': f'Bearer {self.api_key}',
                'Content-Type': 'application/json'
            })
    
    def convert_doc_to_docx(self, doc_content: bytes, original_filename: str) -> bytes:
        """
        将DOC格式转换为DOCX格式
        注意：当前实现为占位符，实际生产环境需要安装LibreOffice或其他转换工具
        
        Args:
            doc_content: DOC文件的二进制内容
            original_filename: 原始文件名
        
        Returns:
            bytes: DOCX格式的二进制数据
        """
        logger.warning(f"DOC格式转换为占位符实现，文件: {original_filename}")
        logger.warning("生产环境请使用LibreOffice无头模式或其他DOC转换工具")
        
        # 临时解决方案：抛出异常，阻止DOC文件被错误处理
        raise NotImplementedError(
            f"DOC格式文件 {original_filename} 需要专门的转换工具。"
            "请配置LibreOffice、unoconv或其他DOC转DOCX转换器。"
            "当前不支持DOC格式文件上传到知识库。"
        )
    
    def add_document_to_knowledge_base_by_file(self, 
                                             file_content: bytes, 
                                             filename: str, 
                                             metadata: Dict) -> Dict:
        """
        通过文件上传将文档添加到Dify知识库（使用父子分段策略）
        
        Args:
            file_content: 文件的二进制内容
            filename: 文件名
            metadata: 文档元数据
            
        Returns:
            Dict: 添加结果
        """
        try:
            if not self.api_key:
                logger.error("Dify API密钥未配置")
                return {
                    'success': False,
                    'error': 'Dify API密钥未配置',
                    'document_id': None
                }
            
            # 检查文件格式，如果是DOC则转换为DOCX
            file_extension = filename.lower().split('.')[-1]
            final_content = file_content
            final_filename = filename
            
            if file_extension == 'doc':
                logger.info(f"检测到DOC格式文件，开始转换: {filename}")
                final_content = self.convert_doc_to_docx(file_content, filename)
                final_filename = filename.rsplit('.', 1)[0] + '.docx'
                logger.info(f"DOC转换完成，新文件名: {final_filename}")
            
            # 准备multipart form data - 使用Dify API支持的字段
            data_json = {
                'indexing_technique': 'high_quality',
                'process_rule': {
                    'mode': 'custom',
                    'rules': {
                        'pre_processing_rules': [
                            {'id': 'remove_extra_spaces', 'enabled': True},
                            {'id': 'remove_urls_emails', 'enabled': False}
                        ],
                        'segmentation': {
                            'separator': '\n',
                            'max_tokens': 1000
                        }
                    }
                }
            }
            
            # 包含元数据以保持可追溯性
            if metadata:
                # 添加文档元数据
                data_json['name'] = metadata.get('title', filename)
                if 'file_id' in metadata:
                    data_json['doc_metadata'] = {
                        'file_id': metadata['file_id'],
                        'analysis_result': metadata.get('analysis_result', {}),
                        'source': 'OA_Document_Processor'
                    }
            
            # 发送文件上传请求到Dify API
            url = f"{self.base_url}/v1/datasets/{self.dataset_id}/document/create-by-file"
            
            logger.info(f"向Dify上传文件: {final_filename} (父子分段模式)")
            
            files = {
                'file': (final_filename, final_content, 'application/octet-stream')
            }
            
            form_data = {
                'data': json.dumps(data_json)
            }
            
            # 临时移除Content-Type头，让requests自动设置multipart边界
            original_headers = self.session.headers.copy()
            if 'Content-Type' in self.session.headers:
                del self.session.headers['Content-Type']
            
            try:
                response = self.session.post(url, files=files, data=form_data, timeout=60)
            finally:
                # 恢复原始headers
                self.session.headers.update(original_headers)
            
            if response.status_code == 200 or response.status_code == 201:
                result = response.json()
                document_id = result.get('document', {}).get('id') or result.get('id')
                
                logger.info(f"文档成功上传到Dify知识库: {document_id} (父子分段模式)")
                
                return {
                    'success': True,
                    'document_id': document_id,
                    'error': None,
                    'response': result,
                    'segmentation_mode': 'hierarchical_model'
                }
            else:
                error_msg = f"Dify文件上传失败: {response.status_code} - {response.text}"
                logger.error(error_msg)
                
                return {
                    'success': False,
                    'error': error_msg,
                    'document_id': None,
                    'status_code': response.status_code
                }
                
        except requests.exceptions.Timeout:
            error_msg = "Dify文件上传超时"
            logger.error(error_msg)
            return {
                'success': False,
                'error': error_msg,
                'document_id': None
            }
        except requests.exceptions.RequestException as e:
            error_msg = f"Dify文件上传网络错误: {str(e)}"
            logger.error(error_msg)
            return {
                'success': False,
                'error': error_msg,
                'document_id': None
            }
        except Exception as e:
            error_msg = f"文件上传到Dify失败: {str(e)}"
            logger.error(error_msg)
            import traceback
            traceback.print_exc()
            return {
                'success': False,
                'error': error_msg,
                'document_id': None
            }
    
    def add_document_to_knowledge_base_by_text(self,
                                             content: str,
                                             filename: str,
                                             metadata: Dict) -> Dict:
        """
        通过文本内容将文档添加到Dify知识库（使用create-by-text接口）

        Args:
            content: 文档内容
            filename: 文件名
            metadata: 文档元数据

        Returns:
            Dict: 添加结果
        """
        try:
            if not self.api_key:
                logger.error("Dify API密钥未配置")
                return {
                    'success': False,
                    'error': 'Dify API密钥未配置',
                    'document_id': None
                }

            # 准备数据，根据Dify API文档配置
            data = {
                'name': filename,
                'text': content,
                'indexing_technique': 'high_quality',  # 高质量索引
                'doc_form': 'hierarchical_model',      # 父子分段模式
                'process_rule': {
                    'mode': 'custom',  # 自定义模式
                    'rules': {
                        'pre_processing_rules': [],  # 暂不进行预处理
                        'segmentation': {
                            'separator': '@@@@@',  # 父分段标识符
                            'max_tokens': 2000     # 父分段最大长度
                        },
                        'parent_mode': 'paragraph',  # 段落召回
                        'subchunk_segmentation': {
                            'separator': '\n',   # 子分段标识符
                            'max_tokens': 500,   # 子分段最大长度
                            'chunk_overlap': 50  # 重叠50token
                        }
                    }
                }
            }

            # 添加元数据
            if metadata and 'file_id' in metadata:
                # 在文档名称中包含元数据信息，便于追溯
                data['name'] = f"{filename} (ID: {metadata['file_id']})"

            # 发送请求到Dify API
            url = f"{self.base_url}/v1/datasets/{self.dataset_id}/document/create-by-text"

            logger.info(f"通过文本创建Dify文档: {filename} (父子分段模式)")
            logger.info(f"文本长度: {len(content)} 字符")

            response = self.session.post(url, json=data, timeout=60)

            if response.status_code == 200 or response.status_code == 201:
                result = response.json()
                document_id = result.get('document', {}).get('id') or result.get('id')

                logger.info(f"文档通过文本成功创建到Dify知识库: {document_id}")

                return {
                    'success': True,
                    'document_id': document_id,
                    'error': None,
                    'response': result,
                    'segmentation_mode': 'hierarchical_model'
                }
            else:
                error_msg = f"Dify文本创建失败: {response.status_code} - {response.text}"
                logger.error(error_msg)

                return {
                    'success': False,
                    'error': error_msg,
                    'document_id': None,
                    'status_code': response.status_code
                }

        except requests.exceptions.Timeout:
            error_msg = "Dify文本创建超时"
            logger.error(error_msg)
            return {
                'success': False,
                'error': error_msg,
                'document_id': None
            }
        except requests.exceptions.RequestException as e:
            error_msg = f"Dify文本创建网络错误: {str(e)}"
            logger.error(error_msg)
            return {
                'success': False,
                'error': error_msg,
                'document_id': None
            }
        except Exception as e:
            error_msg = f"文本创建到Dify失败: {str(e)}"
            logger.error(error_msg)
            import traceback
            traceback.print_exc()
            return {
                'success': False,
                'error': error_msg,
                'document_id': None
            }

    def add_document_to_knowledge_base(self,
                                     content: str,
                                     filename: str,
                                     metadata: Dict) -> Dict:
        """
        将文档内容添加到Dify知识库（兼容性方法，优先使用文本方式）

        Args:
            content: 文档内容
            filename: 文件名
            metadata: 文档元数据

        Returns:
            Dict: 添加结果
        """
        try:
            # 优先使用文本方式创建文档
            return self.add_document_to_knowledge_base_by_text(content, filename, metadata)

        except Exception as e:
            error_msg = f"文档内容上传失败: {str(e)}"
            logger.error(error_msg)
            return {
                'success': False,
                'error': error_msg,
                'document_id': None
            }
    
    def update_document_in_knowledge_base(self, 
                                        document_id: str,
                                        content: str, 
                                        filename: str, 
                                        metadata: Dict) -> Dict:
        """
        更新知识库中的文档
        
        Args:
            document_id: 文档ID
            content: 新的文档内容
            filename: 文件名
            metadata: 文档元数据
            
        Returns:
            Dict: 更新结果
        """
        try:
            if not self.api_key:
                logger.error("Dify API密钥未配置")
                return {
                    'success': False,
                    'error': 'Dify API密钥未配置'
                }
            
            # 准备更新数据
            data = {
                'name': filename,
                'text': content
            }
            
            # 发送更新请求到Dify API
            url = f"{self.base_url}/v1/datasets/{self.dataset_id}/documents/{document_id}/update_by_text"
            
            logger.info(f"更新Dify文档: {document_id}")
            
            response = self.session.post(url, json=data, timeout=30)
            
            if response.status_code == 200:
                result = response.json()
                logger.info(f"文档更新成功: {document_id}")
                
                return {
                    'success': True,
                    'error': None,
                    'response': result
                }
            else:
                error_msg = f"Dify文档更新失败: {response.status_code} - {response.text}"
                logger.error(error_msg)
                
                return {
                    'success': False,
                    'error': error_msg,
                    'status_code': response.status_code
                }
            
        except Exception as e:
            error_msg = f"更新Dify文档失败: {str(e)}"
            logger.error(error_msg)
            return {
                'success': False,
                'error': error_msg
            }
    
    def delete_document_from_knowledge_base(self, document_id: str) -> Dict:
        """
        从知识库中删除文档
        
        Args:
            document_id: 文档ID
            
        Returns:
            Dict: 删除结果
        """
        try:
            if not self.api_key:
                logger.error("Dify API密钥未配置")
                return {
                    'success': False,
                    'error': 'Dify API密钥未配置'
                }
            
            # 发送删除请求到Dify API
            url = f"{self.base_url}/v1/datasets/{self.dataset_id}/documents/{document_id}"
            
            logger.info(f"删除Dify文档: {document_id}")
            
            response = self.session.delete(url, timeout=30)
            
            if response.status_code == 200 or response.status_code == 204:
                logger.info(f"文档删除成功: {document_id}")
                
                return {
                    'success': True,
                    'error': None,
                    'message': f'文档已删除: {document_id}'
                }
            else:
                error_msg = f"Dify文档删除失败: {response.status_code} - {response.text}"
                logger.error(error_msg)
                
                return {
                    'success': False,
                    'error': error_msg,
                    'status_code': response.status_code
                }
            
        except Exception as e:
            error_msg = f"删除Dify文档失败: {str(e)}"
            logger.error(error_msg)
            return {
                'success': False,
                'error': error_msg
            }
    
    def check_api_connection(self) -> Dict:
        """检查Dify API连接状态"""
        try:
            if not self.api_key:
                return {
                    'success': False,
                    'error': 'Dify API密钥未配置'
                }
            
            # 通过获取数据集列表来测试连接
            url = f"{self.base_url}/v1/datasets?page=1&limit=1"
            
            response = self.session.get(url, timeout=10)
            
            if response.status_code == 200:
                logger.info("Dify API连接测试成功")
                return {
                    'success': True,
                    'error': None,
                    'message': 'API连接正常'
                }
            else:
                error_msg = f"Dify API连接失败: {response.status_code} - {response.text}"
                logger.error(error_msg)
                return {
                    'success': False,
                    'error': error_msg
                }
            
        except requests.exceptions.Timeout:
            error_msg = "Dify API连接超时"
            logger.error(error_msg)
            return {
                'success': False,
                'error': error_msg
            }
        except requests.exceptions.RequestException as e:
            error_msg = f"Dify API网络错误: {str(e)}"
            logger.error(error_msg)
            return {
                'success': False,
                'error': error_msg
            }
        except Exception as e:
            error_msg = f"Dify API连接检查失败: {str(e)}"
            logger.error(error_msg)
            return {
                'success': False,
                'error': error_msg
            }

# 创建全局实例
dify_service = DifyService()
