import os
from typing import Optional
from pydantic_settings import BaseSettings
from pydantic import Field

class Settings(BaseSettings):
    # 数据库配置
    database_url: str = Field(default_factory=lambda: os.getenv("DATABASE_URL", "postgresql://user:password@localhost/oa_docs"))
    
    # S3配置
    s3_access_key: str = Field(default_factory=lambda: os.getenv("S3_ACCESS_KEY", ""))
    s3_secret_key: str = Field(default_factory=lambda: os.getenv("S3_SECRET_KEY", ""))
    s3_bucket_name: str = Field(default_factory=lambda: os.getenv("S3_BUCKET_NAME", "oa-documents"))
    s3_region: str = Field(default_factory=lambda: os.getenv("S3_REGION", "us-east-1"))
    s3_endpoint_url: Optional[str] = Field(default_factory=lambda: os.getenv("S3_ENDPOINT_URL"))
    
    # OpenAI配置
    openai_api_key: str = Field(default_factory=lambda: os.getenv("OPENAI_API_KEY", ""))
    
    # Dify配置
    dify_api_key: str = Field(default_factory=lambda: os.getenv("DIFY_API_KEY", ""))
    dify_base_url: str = Field(default_factory=lambda: os.getenv("DIFY_BASE_URL", "https://api.dify.ai"))
    dify_dataset_id: str = Field(default_factory=lambda: os.getenv("DIFY_DATASET_ID", ""))
    
    # Redis配置
    redis_url: str = Field(default_factory=lambda: os.getenv("REDIS_URL", "redis://137.184.113.70:6379/0"))
    
    # 应用配置
    secret_key: str = Field(default_factory=lambda: os.getenv("SECRET_KEY", "your-secret-key-here"))
    debug: bool = Field(default_factory=lambda: os.getenv("DEBUG", "False").lower() == "true")
    
    # 文档处理配置
    max_file_size: int = Field(default=100 * 1024 * 1024)  # 100MB
    supported_formats: list = Field(default=["pdf", "docx", "doc", "txt"])
    
    class Config:
        env_file = ".env"
        case_sensitive = False

settings = Settings()
