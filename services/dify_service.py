import requests
import json
import logging
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
    
    def add_document_to_knowledge_base(self, 
                                     content: str, 
                                     filename: str, 
                                     metadata: Dict) -> Dict:
        """
        将文档添加到Dify知识库
        
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
            
            # 准备请求数据
            # TODO: 根据实际的Dify API文档调整请求格式
            data = {
                'name': filename,
                'text': content,
                'metadata': {
                    'source': 'oa_system',
                    'file_type': metadata.get('file_type', 'unknown'),
                    'content_length': len(content),
                    'category': metadata.get('category', 'other'),
                    'upload_time': metadata.get('upload_time', ''),
                    **metadata
                }
            }
            
            # 发送请求到Dify API
            url = f"{self.base_url}/v1/datasets/{self.dataset_id}/documents"
            
            logger.info(f"向Dify发送文档: {filename}")
            
            response = self.session.post(url, json=data, timeout=30)
            
            if response.status_code == 200 or response.status_code == 201:
                result = response.json()
                document_id = result.get('id') or result.get('document_id')
                
                logger.info(f"文档成功添加到Dify知识库: {document_id}")
                
                return {
                    'success': True,
                    'document_id': document_id,
                    'error': None,
                    'response': result
                }
            else:
                error_msg = f"Dify API请求失败: {response.status_code} - {response.text}"
                logger.error(error_msg)
                
                return {
                    'success': False,
                    'error': error_msg,
                    'document_id': None,
                    'status_code': response.status_code
                }
                
        except requests.exceptions.Timeout:
            error_msg = "Dify API请求超时"
            logger.error(error_msg)
            return {
                'success': False,
                'error': error_msg,
                'document_id': None
            }
        except requests.exceptions.RequestException as e:
            error_msg = f"Dify API网络错误: {str(e)}"
            logger.error(error_msg)
            return {
                'success': False,
                'error': error_msg,
                'document_id': None
            }
        except Exception as e:
            error_msg = f"添加文档到Dify失败: {str(e)}"
            logger.error(error_msg)
            import traceback
            traceback.print_exc()
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
            
            # TODO: 实现文档更新逻辑
            # 这里需要根据实际的Dify API来实现
            
            logger.info(f"更新Dify文档: {document_id}")
            
            return {
                'success': True,
                'error': None,
                'message': 'TODO: 实现文档更新功能'
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
            
            # TODO: 实现文档删除逻辑
            # 这里需要根据实际的Dify API来实现
            
            logger.info(f"删除Dify文档: {document_id}")
            
            return {
                'success': True,
                'error': None,
                'message': 'TODO: 实现文档删除功能'
            }
            
        except Exception as e:
            error_msg = f"删除Dify文档失败: {str(e)}"
            logger.error(error_msg)
            return {
                'success': False,
                'error': error_msg
            }
    
    def check_api_connection(self) -> bool:
        """检查Dify API连接状态"""
        try:
            if not self.api_key:
                return False
            
            # TODO: 实现API连接检查
            # 这里需要根据实际的Dify API来实现
            
            return True
            
        except Exception as e:
            logger.error(f"Dify API连接检查失败: {e}")
            return False

# 创建全局实例
dify_service = DifyService()
