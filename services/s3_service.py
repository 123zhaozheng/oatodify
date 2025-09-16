import boto3
from botocore.exceptions import ClientError, NoCredentialsError
from config import settings
import logging
from typing import Optional, bytes

logger = logging.getLogger(__name__)

class S3Service:
    """S3存储服务"""
    
    def __init__(self):
        self.client = None
        self._init_client()
    
    def _init_client(self):
        """初始化S3客户端"""
        try:
            session = boto3.Session(
                aws_access_key_id=settings.s3_access_key,
                aws_secret_access_key=settings.s3_secret_key,
                region_name=settings.s3_region
            )
            
            client_kwargs = {}
            if settings.s3_endpoint_url:
                client_kwargs['endpoint_url'] = settings.s3_endpoint_url
            
            self.client = session.client('s3', **client_kwargs)
            logger.info("S3客户端初始化成功")
            
        except NoCredentialsError:
            logger.error("S3凭证未配置")
            raise
        except Exception as e:
            logger.error(f"S3客户端初始化失败: {e}")
            raise
    
    def download_file(self, file_key: str, token_key: Optional[str] = None) -> bytes:
        """
        从S3下载文件
        
        Args:
            file_key: 文件在S3中的键值
            token_key: 访问令牌（如果需要）
            
        Returns:
            文件的二进制数据
        """
        try:
            # 构建下载参数
            download_params = {
                'Bucket': settings.s3_bucket_name,
                'Key': file_key
            }
            
            # 如果有token_key，添加到请求头中
            if token_key:
                download_params['ExtraArgs'] = {
                    'RequestPayer': 'requester',
                    'Metadata': {'token': token_key}
                }
            
            logger.info(f"开始下载文件: {file_key}")
            
            # 下载文件到内存
            response = self.client.get_object(**download_params)
            file_data = response['Body'].read()
            
            logger.info(f"文件下载成功，大小: {len(file_data)} 字节")
            return file_data
            
        except ClientError as e:
            error_code = e.response['Error']['Code']
            if error_code == 'NoSuchKey':
                logger.error(f"文件不存在: {file_key}")
                raise FileNotFoundError(f"文件不存在: {file_key}")
            elif error_code == 'AccessDenied':
                logger.error(f"访问被拒绝: {file_key}")
                raise PermissionError(f"访问被拒绝: {file_key}")
            else:
                logger.error(f"S3下载错误 {error_code}: {e}")
                raise
        except Exception as e:
            logger.error(f"下载文件时发生未知错误: {e}")
            raise
    
    def check_file_exists(self, file_key: str) -> bool:
        """检查文件是否存在"""
        try:
            self.client.head_object(Bucket=settings.s3_bucket_name, Key=file_key)
            return True
        except ClientError:
            return False
    
    def get_file_info(self, file_key: str) -> dict:
        """获取文件信息"""
        try:
            response = self.client.head_object(Bucket=settings.s3_bucket_name, Key=file_key)
            return {
                'size': response['ContentLength'],
                'last_modified': response['LastModified'],
                'content_type': response.get('ContentType', 'unknown'),
                'etag': response['ETag']
            }
        except ClientError as e:
            logger.error(f"获取文件信息失败: {e}")
            raise

# 创建全局实例
s3_service = S3Service()
