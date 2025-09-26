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
    openai_base_url: Optional[str] = Field(default_factory=lambda: os.getenv("OPENAI_BASE_URL"))
    openai_model_name: str = Field(default_factory=lambda: os.getenv("OPENAI_MODEL_NAME", "gpt-4"))
    
    # Dify配置
    dify_api_key: str = Field(default_factory=lambda: os.getenv("DIFY_API_KEY", ""))
    dify_base_url: str = Field(default_factory=lambda: os.getenv("DIFY_BASE_URL", "https://api.dify.ai"))
    dify_dataset_id: str = Field(default_factory=lambda: os.getenv("DIFY_DATASET_ID", ""))
    
    # Redis配置
    redis_url: str = Field(default_factory=lambda: os.getenv("REDIS_URL", "redis://137.184.113.70:6379/0"))
    
    # 应用配置
    secret_key: str = Field(default_factory=lambda: os.getenv("SECRET_KEY", "your-secret-key-here"))
    debug: bool = Field(default_factory=lambda: os.getenv("DEBUG", "False").lower() == "true")
    base_url: str = Field(default_factory=lambda: os.getenv("BASE_URL", "http://localhost:8000"))
    
    # 文档处理配置
    max_file_size: int = Field(default=100 * 1024 * 1024)  # 100MB
    supported_formats: list = Field(default=["pdf", "docx", "doc", "txt"])

    # 文档解析接口配置
    document_parse_api_url: str = Field(default_factory=lambda: os.getenv("DOCUMENT_PARSE_API_URL", "http://document-parser:8080"))

    # AI分析配置
    ai_analysis_max_length: int = Field(default_factory=lambda: int(os.getenv("AI_ANALYSIS_MAX_LENGTH", "50000")))

    # 文件筛选配置
    # 共用关键字（所有业务分类都会检查）
    filter_keywords_common: str = Field(default_factory=lambda: os.getenv("FILTER_KEYWORDS_COMMON", "test,demo,temp,tmp,draft,backup,bak,copy,delete,del,deprecated,invalid,expired"))

    # 按业务分类的关键字配置
    filter_keywords_headquarters_issue: str = Field(default_factory=lambda: os.getenv("FILTER_KEYWORDS_HEADQUARTERS_ISSUE", ""))
    filter_keywords_retail_announcement: str = Field(default_factory=lambda: os.getenv("FILTER_KEYWORDS_RETAIL_ANNOUNCEMENT", ""))
    filter_keywords_publication_release: str = Field(default_factory=lambda: os.getenv("FILTER_KEYWORDS_PUBLICATION_RELEASE", ""))
    filter_keywords_branch_issue: str = Field(default_factory=lambda: os.getenv("FILTER_KEYWORDS_BRANCH_ISSUE", ""))
    filter_keywords_branch_receive: str = Field(default_factory=lambda: os.getenv("FILTER_KEYWORDS_BRANCH_RECEIVE", ""))
    filter_keywords_public_standard: str = Field(default_factory=lambda: os.getenv("FILTER_KEYWORDS_PUBLIC_STANDARD", ""))
    filter_keywords_headquarters_receive: str = Field(default_factory=lambda: os.getenv("FILTER_KEYWORDS_HEADQUARTERS_RECEIVE", ""))
    filter_keywords_corporate_announcement: str = Field(default_factory=lambda: os.getenv("FILTER_KEYWORDS_CORPORATE_ANNOUNCEMENT", ""))

    # 保留原有的文件类型关键字（作为备用）
    filter_keywords_pdf: str = Field(default_factory=lambda: os.getenv("FILTER_KEYWORDS_PDF", "scan,preview"))
    filter_keywords_docx: str = Field(default_factory=lambda: os.getenv("FILTER_KEYWORDS_DOCX", "template,blank"))
    filter_keywords_txt: str = Field(default_factory=lambda: os.getenv("FILTER_KEYWORDS_TXT", "log,record"))
    filter_keywords_other: str = Field(default_factory=lambda: os.getenv("FILTER_KEYWORDS_OTHER", "config,setting"))

    # 筛选器配置
    filter_enable_keyword_filter: bool = Field(default_factory=lambda: os.getenv("FILTER_ENABLE_KEYWORD_FILTER", "true").lower() == "true")
    filter_enable_duplicate_filter: bool = Field(default_factory=lambda: os.getenv("FILTER_ENABLE_DUPLICATE_FILTER", "true").lower() == "true")
    filter_case_sensitive_keywords: bool = Field(default_factory=lambda: os.getenv("FILTER_CASE_SENSITIVE_KEYWORDS", "false").lower() == "true")
    filter_max_file_size_mb: int = Field(default_factory=lambda: int(os.getenv("FILTER_MAX_FILE_SIZE_MB", "100")))
    filter_min_file_size_bytes: int = Field(default_factory=lambda: int(os.getenv("FILTER_MIN_FILE_SIZE_BYTES", "100")))
    
    class Config:
        env_file = ".env"
        case_sensitive = False

settings = Settings()
