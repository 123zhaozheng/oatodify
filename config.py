import os
import json
import logging
from pathlib import Path
from typing import Optional
from pydantic_settings import BaseSettings
from pydantic import Field

class Settings(BaseSettings):
    # NAS 为默认来源；auto 仅在没有 NAS 路径时兼容旧 S3 数据。
    storage_backend: str = Field(default="nas", pattern="^(nas|s3|auto)$")
    nas_root: str = "/mnt/oa"
    nas_path_prefix: Optional[str] = None
    nas_files_encrypted: bool = False
    dat_filerealpath_index: int = Field(default=11, ge=0)
    cleanup_auto_delete: bool = False
    cleanup_min_confidence: int = Field(default=95, ge=0, le=100)
    cleanup_context_chars: int = Field(default=24000, ge=2000)
    cleanup_ai_recheck_days: int = Field(default=30, ge=1)
    ai_json_output_method: str = Field(default="response_format", pattern="^(response_format|prompt)$")
    ai_request_timeout: int = Field(default=120, ge=1)
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
    max_file_size: int = Field(default=100 * 1024 * 1024, ge=1, le=1_000_000_000_000)  # bytes, 100MB
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

    # DAT文件导入配置
    dat_import_directory: str = Field(default_factory=lambda: os.getenv("DAT_IMPORT_DIRECTORY", "/data/dat_files"))
    dat_import_update_existing: bool = Field(default_factory=lambda: os.getenv("DAT_IMPORT_UPDATE_EXISTING", "false").lower() == "true")

    class Config:
        env_file = ".env"
        case_sensitive = False
        extra = "ignore"

logger = logging.getLogger(__name__)
settings = Settings()

# Database and queue URLs are read by modules that create long-lived connections at
# import time.  Keep them out of hot refreshes so a running process never claims to
# have switched its database or Redis connection.
RESTART_ONLY_SETTINGS = frozenset({"database_url", "redis_url", "secret_key", "base_url"})


def runtime_config_path() -> Path:
    """Return the shared runtime configuration file path."""
    return Path(os.environ.get("RUNTIME_CONFIG_PATH", "/app/config/runtime.json")).expanduser()


def _read_runtime_document():
    path = runtime_config_path()
    try:
        with path.open("r", encoding="utf-8") as stream:
            stat = os.fstat(stream.fileno())
            document = json.load(stream)
        signature = (str(path.resolve()), stat.st_mtime_ns, stat.st_size,
                     document.get("version") if isinstance(document, dict) else None)
        return document, signature
    except FileNotFoundError:
        return None, (str(path.resolve()), None, None, None)


def _validated_settings_values(values):
    if not isinstance(values, dict):
        raise ValueError("runtime config values must be an object")
    known = {key: value for key, value in values.items() if key in Settings.model_fields}
    # Validate a complete settings model before updating the process-wide instance.
    # This also ensures constraints such as the configured integer ranges survive
    # a manually edited or damaged runtime file.
    current = settings.model_dump()
    validated = Settings.model_validate({**current, **known})
    return validated.model_dump()


def _apply_runtime_values(values, include_restart):
    accepted = {
        key: value for key, value in values.items()
        if key in Settings.model_fields and (include_restart or key not in RESTART_ONLY_SETTINGS)
    }
    if not accepted:
        return set()
    validated = _validated_settings_values(accepted)
    changed = set()
    for key in accepted:
        value = validated[key]
        if getattr(settings, key) != value:
            setattr(settings, key, value)
            changed.add(key)
    return changed


_runtime_signature = None
_environment_settings = settings.model_dump()


def refresh_settings(include_restart=False):
    """Reload changed persisted settings, applying hot fields by default.

    The file is replaced atomically by the configuration service.  Its version
    and file metadata let each API/worker process cheaply detect cross-process
    changes without rebuilding clients when nothing has changed.
    """
    global _runtime_signature
    try:
        document, signature = _read_runtime_document()
    except (OSError, ValueError, TypeError):
        logger.warning("无法读取运行时配置文件；继续使用当前进程配置")
        return set()
    if signature == _runtime_signature:
        return set()

    values = document.get("values", {}) if isinstance(document, dict) else {}
    if not isinstance(values, dict):
        logger.warning("运行时配置格式无效；继续使用当前进程配置")
        _runtime_signature = signature
        return set()
    try:
        changed = _apply_runtime_values(values, include_restart=include_restart)
        # If the shared file has been removed, hot settings return to this process's
        # environment snapshot. Restart-only settings remain bound to startup state.
        if document is None:
            restore = {
                key: value for key, value in _environment_settings.items()
                if key not in RESTART_ONLY_SETTINGS or include_restart
            }
            changed.update(_apply_runtime_values(restore, include_restart=include_restart))
    except Exception:
        logger.warning("运行时配置校验失败；继续使用当前进程配置")
        _runtime_signature = signature
        return set()
    _runtime_signature = signature
    return changed


# Load the shared file once during import so saved settings override .env values
# before service singletons and database/queue clients are constructed.
try:
    _startup_document, _startup_signature = _read_runtime_document()
    if isinstance(_startup_document, dict):
        _apply_runtime_values(_startup_document.get("values", {}), include_restart=True)
    _runtime_signature = _startup_signature
except Exception:
    logger.warning("启动时运行时配置不可用；使用环境变量和默认配置")
    _runtime_signature = None

# This snapshot is the value actually used at process startup.  GET /console/config
# uses it to accurately report saved restart-only changes as pending restart.
STARTUP_SETTINGS = settings.model_dump()


def restart_required_settings(saved_values):
    return sorted(
        key for key in RESTART_ONLY_SETTINGS
        if key in saved_values and saved_values[key] != STARTUP_SETTINGS.get(key)
    )


def runtime_config_signature():
    """Current shared file signature, including its cross-process revision."""
    try:
        return _read_runtime_document()[1]
    except (OSError, ValueError, TypeError):
        return None
