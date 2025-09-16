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
            
            # 准备请求数据 - 根据Dify API文档格式
            data = {
                'name': filename,
                'text': content,
                'indexing_technique': 'high_quality',
                'process_rule': {
                    'mode': 'automatic'
                }
            }
            
            # 发送请求到Dify API
            url = f"{self.base_url}/v1/datasets/{self.dataset_id}/document/create-by-text"
            
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
