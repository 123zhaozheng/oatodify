"""Shared, versioned runtime configuration and safe hot-refresh support."""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
import json
import logging
import os
from pathlib import Path
import tempfile
import threading
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from config import (
    restart_required_settings,
    runtime_config_path,
    runtime_config_signature,
    settings,
)

logger = logging.getLogger(__name__)


class RuntimeConfigError(Exception):
    """An expected runtime-configuration read or write failure."""


class VersionConflict(RuntimeConfigError):
    """The caller edited an out-of-date configuration version."""


def _field(key, label, kind, group, help_text, *, secret=False, apply="hot",
           options=None, minimum=None, maximum=None, optional=False):
    return {
        "key": key, "label": label, "type": "secret" if secret else kind,
        "group": group, "secret": secret, "apply": apply, "help": help_text,
        "options": [{"value": value, "label": title} for value, title in (options or [])],
        "min": minimum, "max": maximum, "optional": optional,
    }


CONFIG_FIELDS = [
    _field("storage_backend", "存储方式", "enum", "NAS 与导入", "选择文档读取的存储后端。",
           options=[("nas", "NAS"), ("s3", "S3"), ("auto", "自动")]),
    _field("nas_root", "NAS 根目录", "string", "NAS 与导入", "NAS 挂载根目录，必须是绝对路径。"),
    _field("nas_path_prefix", "NAS 路径前缀", "string", "NAS 与导入", "OA 路径前缀映射；非空时必须是绝对路径，留空表示不映射。", optional=True),
    _field("nas_files_encrypted", "NAS 文件已加密", "boolean", "NAS 与导入", "开启后按现有解密规则处理 NAS 文件。"),
    _field("max_file_size", "文件读取保护上限（字节）", "integer", "NAS 与导入", "NAS/文件存储读取时的硬保护上限；这是读取保护，与下方处理筛选上限分别生效。", minimum=1, maximum=1_000_000_000_000),
    _field("s3_access_key", "S3 访问密钥", "string", "NAS 与导入", "S3 访问密钥。", secret=True),
    _field("s3_secret_key", "S3 私密密钥", "string", "NAS 与导入", "S3 私密密钥。", secret=True),
    _field("s3_bucket_name", "S3 存储桶", "string", "NAS 与导入", "S3 存储桶名称。"),
    _field("s3_region", "S3 区域", "string", "NAS 与导入", "S3 区域名称。"),
    _field("s3_endpoint_url", "S3 服务地址", "string", "NAS 与导入", "地址摘要仅展示无凭证部分；留空保留当前地址。", secret=True, optional=True),
    _field("dat_import_directory", "DAT 导入目录", "string", "NAS 与导入", "DAT 文件的默认导入目录，必须是绝对路径。"),
    _field("dat_import_update_existing", "DAT 覆盖已有文件", "boolean", "NAS 与导入", "导入时是否更新已有文件记录。"),
    _field("dat_filerealpath_index", "DAT 路径列序号", "integer", "NAS 与导入", "DAT 行中 filerealpath 字段的从零开始序号。", minimum=0, maximum=1000),
    _field("document_parse_api_url", "解析服务地址", "string", "解析与模型", "地址摘要仅展示无凭证部分；留空保留当前地址。", secret=True),
    _field("ai_analysis_max_length", "模型分析最大字符数", "integer", "解析与模型", "送入模型分析的正文最大字符数。", minimum=1, maximum=10000000),
    _field("ai_request_timeout", "模型请求超时（秒）", "integer", "解析与模型", "模型请求超时时间。", minimum=1, maximum=3600),
    _field("ai_json_output_method", "模型 JSON 输出方式", "enum", "解析与模型", "控制模型 JSON 输出格式。",
           options=[("response_format", "接口格式约束"), ("prompt", "提示词约束")]),
    _field("openai_api_key", "模型 API Key", "string", "解析与模型", "模型服务 API 密钥。", secret=True),
    _field("openai_base_url", "模型服务地址", "string", "解析与模型", "地址摘要仅展示无凭证部分；留空保留当前地址。", secret=True, optional=True),
    _field("openai_model_name", "模型名称", "string", "解析与模型", "模型服务使用的模型名称。"),
    _field("dify_api_key", "默认 Dify API Key", "string", "Dify 与分类映射", "默认知识库 API 密钥。", secret=True),
    _field("dify_base_url", "默认 Dify 地址", "string", "Dify 与分类映射", "地址摘要仅展示无凭证部分；留空保留当前地址。", secret=True),
    _field("dify_dataset_id", "默认 Dify 数据集 ID", "string", "Dify 与分类映射", "未匹配业务分类时使用的数据集。"),
    _field("cleanup_auto_delete", "自动执行清理", "boolean", "清理与筛选", "按已核验失效日或完整正文一致的规则自动清理；制度版本替换仍需人工审核。"),
    _field("cleanup_min_confidence", "清理最低置信度", "integer", "清理与筛选", "清理证据通过所需的最低模型置信度。", minimum=0, maximum=100),
    _field("cleanup_context_chars", "清理分析上下文长度", "integer", "清理与筛选", "发送给清理分析模型的正文上下文长度。", minimum=2000, maximum=1000000),
    _field("cleanup_ai_recheck_days", "不确定结果重查间隔（天）", "integer", "清理与筛选", "未知结论重新请求模型分析的间隔天数。", minimum=1, maximum=3650),
    _field("filter_keywords_common", "通用筛选关键字", "string", "清理与筛选", "所有业务分类共用的逗号分隔关键字。"),
    _field("filter_keywords_headquarters_issue", "总行发文筛选关键字", "string", "清理与筛选", "总行发文的逗号分隔关键字。"),
    _field("filter_keywords_retail_announcement", "零售公告筛选关键字", "string", "清理与筛选", "零售条线公告的逗号分隔关键字。"),
    _field("filter_keywords_publication_release", "刊物发布筛选关键字", "string", "清理与筛选", "刊物发布的逗号分隔关键字。"),
    _field("filter_keywords_branch_issue", "支行发文筛选关键字", "string", "清理与筛选", "支行发文的逗号分隔关键字。"),
    _field("filter_keywords_branch_receive", "支行收文筛选关键字", "string", "清理与筛选", "支行收文的逗号分隔关键字。"),
    _field("filter_keywords_public_standard", "公共规范筛选关键字", "string", "清理与筛选", "公共发布及规范文件的逗号分隔关键字。"),
    _field("filter_keywords_headquarters_receive", "总行收文筛选关键字", "string", "清理与筛选", "总行收文的逗号分隔关键字。"),
    _field("filter_keywords_corporate_announcement", "公司公告筛选关键字", "string", "清理与筛选", "公司条线公告的逗号分隔关键字。"),
    _field("filter_keywords_pdf", "PDF 筛选关键字", "string", "清理与筛选", "PDF 文件名的逗号分隔关键字。"),
    _field("filter_keywords_docx", "Word 筛选关键字", "string", "清理与筛选", "Word 文件名的逗号分隔关键字。"),
    _field("filter_keywords_txt", "文本筛选关键字", "string", "清理与筛选", "文本文件名的逗号分隔关键字。"),
    _field("filter_keywords_other", "其他格式筛选关键字", "string", "清理与筛选", "其他格式文件名的逗号分隔关键字。"),
    _field("filter_enable_keyword_filter", "启用关键字筛选", "boolean", "清理与筛选", "按文件名关键字跳过不需要处理的文档。"),
    _field("filter_case_sensitive_keywords", "关键字区分大小写", "boolean", "清理与筛选", "控制文件名关键字比较是否区分大小写。"),
    _field("filter_max_file_size_mb", "处理筛选上限（MB）", "integer", "清理与筛选", "处理筛选阈值；与 NAS 读取保护上限（字节）独立。文件必须同时满足读取保护和处理筛选上限。", minimum=1, maximum=100000),
    _field("filter_min_file_size_bytes", "最小文件大小（字节）", "integer", "清理与筛选", "允许处理的最小文件大小。", minimum=0, maximum=1000000000),
    _field("database_url", "数据库连接串", "string", "基础连接", "数据库连接串。保存后需重启 API、Worker 和 Beat。", secret=True, apply="restart"),
    _field("redis_url", "Redis 连接串", "string", "基础连接", "Celery/Redis 连接串。保存后需重启 API、Worker 和 Beat。", secret=True, apply="restart"),
    _field("secret_key", "应用密钥", "string", "基础连接", "应用签名密钥。保存后需重启 API、Worker 和 Beat。", secret=True, apply="restart"),
    _field("base_url", "应用基础地址", "string", "基础连接", "地址摘要仅展示无凭证部分；保存后需重启 API、Worker 和 Beat。", secret=True, apply="restart"),
]

FIELD_BY_KEY = {item["key"]: item for item in CONFIG_FIELDS}
# Older persisted files may contain this now-retired UI setting. Keep reading and
# preserving it for compatibility, but never expose or accept it in console PATCH.
LEGACY_STORED_KEYS = frozenset({"filter_enable_duplicate_filter"})
ENDPOINT_FIELD_KEYS = frozenset({
    "s3_endpoint_url", "document_parse_api_url", "openai_base_url", "dify_base_url", "base_url",
})
REQUIRED_ENDPOINT_FIELD_KEYS = frozenset({"document_parse_api_url", "dify_base_url", "base_url"})
REQUIRED_CONNECTION_FIELD_KEYS = frozenset({"database_url", "redis_url"})
_write_lock = threading.RLock()


def _empty_store():
    return {"version": 0, "values": {}, "updated_at": None}


def _read_store():
    path = runtime_config_path()
    try:
        with path.open("r", encoding="utf-8") as stream:
            document = json.load(stream)
    except FileNotFoundError:
        return _empty_store()
    except (OSError, json.JSONDecodeError, UnicodeError) as exc:
        raise RuntimeConfigError("无法读取运行时配置") from exc
    if (not isinstance(document, dict) or type(document.get("version")) is not int
            or document["version"] < 0 or not isinstance(document.get("values", {}), dict)):
        raise RuntimeConfigError("运行时配置格式无效")
    values = document.get("values", {})
    if any(key not in FIELD_BY_KEY and key not in LEGACY_STORED_KEYS for key in values):
        raise RuntimeConfigError("运行时配置包含未知字段")
    return {"version": document["version"], "values": dict(values),
            "updated_at": document.get("updated_at")}


@contextmanager
def _exclusive_file_lock(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = Path(str(path) + ".lock")
    fd = os.open(str(lock_path), os.O_CREAT | os.O_RDWR, 0o600)
    try:
        os.chmod(lock_path, 0o600)
        fcntl.flock(fd, fcntl.LOCK_EX)
        with _write_lock:
            yield
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)


def _atomic_write(document):
    path = runtime_config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent))
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(document, stream, ensure_ascii=False, separators=(",", ":"))
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp_name, path)
        os.chmod(path, 0o600)
        dir_fd = os.open(str(path.parent), os.O_RDONLY)
        try:
            os.fsync(dir_fd)
        finally:
            os.close(dir_fd)
    except Exception:
        try:
            os.unlink(temp_name)
        except OSError:
            pass
        raise


def _validate_value(key: str, value: Any):
    spec = FIELD_BY_KEY[key]
    kind = spec["type"]
    if value is None and spec.get("optional"):
        return None
    if kind == "boolean":
        valid = type(value) is bool
    elif kind == "integer":
        valid = type(value) is int
    elif kind in ("string", "secret"):
        valid = isinstance(value, str)
    elif kind == "enum":
        valid = isinstance(value, str) and value in {option["value"] for option in spec["options"]}
    else:
        valid = False
    if not valid:
        raise ValueError("invalid type")
    if isinstance(value, str) and len(value) > (20000 if spec["secret"] else 5000):
        raise ValueError("value too long")
    if value == "" and spec.get("optional"):
        return None
    if key in ENDPOINT_FIELD_KEYS and value not in (None, ""):
        try:
            parsed = urlsplit(value)
            # Accessing .port also rejects malformed or out-of-range ports.
            _ = parsed.port
            if (parsed.scheme.lower() not in {"http", "https"} or not parsed.hostname
                    or value != value.strip() or any(char.isspace() for char in value)):
                raise ValueError("invalid endpoint URL")
        except (AttributeError, TypeError, ValueError):
            raise ValueError("invalid endpoint URL") from None
    if key in {"nas_root", "nas_path_prefix", "dat_import_directory"} and value not in (None, ""):
        if "\x00" in value or not os.path.isabs(value):
            raise ValueError("path must be absolute")
    if key in {"nas_root", "dat_import_directory"} and value == "":
        raise ValueError("required path cannot be empty")
    if key == "database_url" and value:
        try:
            from sqlalchemy.engine import make_url
            parsed = make_url(value)
            if parsed.drivername.split("+")[0] not in {"postgresql", "sqlite"}:
                raise ValueError("unsupported database driver")
        except Exception:
            raise ValueError("invalid database URL") from None
    if key == "redis_url" and value:
        try:
            parsed = urlsplit(value)
            _ = parsed.port
            if parsed.scheme not in {"redis", "rediss", "unix"}:
                raise ValueError("unsupported queue URL")
            if parsed.scheme == "unix" and not os.path.isabs(parsed.path):
                raise ValueError("invalid unix socket")
            if parsed.scheme != "unix" and not parsed.hostname:
                raise ValueError("missing redis hostname")
        except Exception:
            raise ValueError("invalid queue URL") from None
    if spec.get("min") is not None and value < spec["min"]:
        raise ValueError("below minimum")
    if spec.get("max") is not None and value > spec["max"]:
        raise ValueError("above maximum")
    if key == "storage_backend" and value not in {"nas", "s3", "auto"}:
        raise ValueError("invalid option")
    return value


def get_runtime_config():
    """Return contract-safe config metadata; secret inputs are always blank."""
    store = _read_store()
    values = {}
    secrets = {}
    for spec in CONFIG_FIELDS:
        key = spec["key"]
        value = store["values"].get(key, getattr(settings, key))
        configured = value is not None and value != ""
        if spec["secret"]:
            values[key] = ""
            secrets[key] = bool(configured)
        else:
            values[key] = value
    fields = []
    for spec in CONFIG_FIELDS:
        item = {key: value for key, value in spec.items() if key != "optional"}
        item["clearable"] = spec["key"] not in REQUIRED_ENDPOINT_FIELD_KEYS | REQUIRED_CONNECTION_FIELD_KEYS
        if spec["key"] in ENDPOINT_FIELD_KEYS:
            value = store["values"].get(spec["key"], getattr(settings, spec["key"]))
            item["display_value"] = _safe_endpoint_display(value)
        fields.append(item)
    return {
        "version": store["version"],
        "values": values,
        "fields": fields,
        "secrets": secrets,
        "restart_required": restart_required_settings(store["values"]),
        "updated_at": store["updated_at"],
    }


def patch_runtime_config(expected_version, values, clear_secrets=None):
    """Validate and atomically persist a version-checked configuration patch."""
    if type(expected_version) is not int or expected_version < 0:
        raise ValueError("invalid version")
    if not isinstance(values, dict):
        raise ValueError("values must be an object")
    clear_secrets = [] if clear_secrets is None else clear_secrets
    if not isinstance(clear_secrets, list) or any(not isinstance(key, str) for key in clear_secrets):
        raise ValueError("clear_secrets must be an array")
    if len(set(clear_secrets)) != len(clear_secrets):
        raise ValueError("duplicate secret key")
    unknown_values = set(values) - FIELD_BY_KEY.keys()
    unknown_clear = set(clear_secrets) - FIELD_BY_KEY.keys()
    if unknown_values or unknown_clear:
        raise ValueError("unknown configuration field")
    for key in clear_secrets:
        if not FIELD_BY_KEY[key]["secret"]:
            raise ValueError("clear_secrets accepts only secret fields")
        if key in REQUIRED_ENDPOINT_FIELD_KEYS | REQUIRED_CONNECTION_FIELD_KEYS:
            raise ValueError("required endpoint cannot be empty")
        if key in values and values[key] not in ("", None):
            raise ValueError("cannot set and clear one secret together")

    normalized = {}
    for key, raw_value in values.items():
        try:
            normalized[key] = _validate_value(key, raw_value)
        except (TypeError, ValueError):
            raise ValueError("invalid configuration value") from None

    path = runtime_config_path()
    with _exclusive_file_lock(path):
        current = _read_store()
        if expected_version != current["version"]:
            raise VersionConflict("配置版本已更新，请刷新后重试")
        stored = dict(current["values"])
        for key, value in normalized.items():
            if FIELD_BY_KEY[key]["secret"] and value in ("", None):
                # Blank secret controls are intentionally a no-op; clear is explicit.
                continue
            if key in ENDPOINT_FIELD_KEYS:
                current_value = current["values"].get(key, getattr(settings, key))
                if value == _safe_endpoint_display(current_value):
                    # Treat a read-only address summary accidentally submitted by
                    # the UI as unchanged; it must never replace hidden URI secrets.
                    continue
            stored[key] = value
        for key in clear_secrets:
            stored[key] = ""
        updated = {
            "version": current["version"] + 1,
            "values": stored,
            "updated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        }
        try:
            _atomic_write(updated)
        except OSError:
            raise RuntimeConfigError("配置持久化失败") from None
    return updated


def _safe_endpoint_display(value):
    if not isinstance(value, str) or not value:
        return ""
    try:
        if value != value.strip() or any(char.isspace() for char in value):
            return ""
        parsed = urlsplit(value)
        _ = parsed.port
        if parsed.scheme.lower() not in {"http", "https"} or not parsed.hostname:
            return ""
        host = parsed.netloc.rsplit("@", 1)[-1]
        return urlunsplit((parsed.scheme.lower(), host, parsed.path, "", ""))
    except (TypeError, ValueError):
        return ""


def bump_runtime_revision():
    """Advance the shared revision to invalidate database-backed caches everywhere."""
    path = runtime_config_path()
    with _exclusive_file_lock(path):
        current = _read_store()
        updated = {
            "version": current["version"] + 1,
            "values": current["values"],
            "updated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        }
        try:
            _atomic_write(updated)
        except OSError:
            raise RuntimeConfigError("共享配置版本更新失败") from None
    return updated


_last_signature = runtime_config_signature()
_last_revision = _last_signature[3] if _last_signature else None


def refresh_runtime_settings():
    """Apply changed hot settings and refresh process-local service caches once."""
    global _last_signature, _last_revision
    signature = runtime_config_signature()
    if signature == _last_signature:
        return {"changed": [], "revision_changed": False}

    from config import refresh_settings

    changed = refresh_settings(include_restart=False)
    revision = signature[3] if signature else None
    revision_changed = revision != _last_revision
    if changed or revision_changed:
        _refresh_service_caches(changed, revision_changed)
    _last_signature = signature
    _last_revision = revision
    return {"changed": sorted(changed), "revision_changed": revision_changed}


def _refresh_service_caches(changed, revision_changed):
    """Update existing singleton objects without recreating them on no-op reads."""
    changed = set(changed)
    try:
        if changed & {"document_parse_api_url", "ai_analysis_max_length"}:
            from services.api_document_parser import api_document_parser
            api_document_parser.parse_api_url = settings.document_parse_api_url
            api_document_parser.ai_analysis_max_length = settings.ai_analysis_max_length

        if changed & {"openai_api_key", "openai_base_url", "openai_model_name", "ai_request_timeout", "ai_analysis_max_length"}:
            from services.ai_analyzer import ai_analyzer
            if changed & {"openai_api_key", "openai_base_url", "openai_model_name", "ai_request_timeout"}:
                ai_analyzer.client = _new_openai_client()
            ai_analyzer.model_name = settings.openai_model_name
            ai_analyzer.max_analysis_length = settings.ai_analysis_max_length
            ai_analyzer.processors.clear()

        if changed & {"openai_api_key", "openai_base_url", "openai_model_name", "ai_request_timeout", "cleanup_min_confidence", "cleanup_context_chars", "cleanup_ai_recheck_days"}:
            from services.version_manager import version_manager
            if changed & {"openai_api_key", "openai_base_url", "openai_model_name", "ai_request_timeout"}:
                version_manager.client = _new_openai_client()
            version_manager.model_name = settings.openai_model_name

        if changed & {"s3_access_key", "s3_secret_key", "s3_region", "s3_endpoint_url"}:
            from services.s3_service import s3_service
            s3_service.client = _new_s3_client()

        if changed & {"dify_api_key", "dify_base_url", "dify_dataset_id"}:
            from services.dify_service import dify_service, multi_kb_manager
            _refresh_dify_service(dify_service)
            multi_kb_manager.clear_cache()

        if revision_changed or changed & {
            "filter_keywords_common", "filter_keywords_headquarters_issue",
            "filter_keywords_retail_announcement", "filter_keywords_publication_release",
            "filter_keywords_branch_issue", "filter_keywords_branch_receive",
            "filter_keywords_public_standard", "filter_keywords_headquarters_receive",
            "filter_keywords_corporate_announcement", "filter_keywords_pdf",
            "filter_keywords_docx", "filter_keywords_txt", "filter_keywords_other",
            "filter_enable_keyword_filter", "filter_enable_duplicate_filter",
            "filter_case_sensitive_keywords", "filter_max_file_size_mb",
            "filter_min_file_size_bytes",
        }:
            from services.file_filter import file_filter
            file_filter._load_keywords_from_config()
            file_filter.config = {
                "enable_keyword_filter": settings.filter_enable_keyword_filter,
                "enable_duplicate_filter": settings.filter_enable_duplicate_filter,
                "case_sensitive_keywords": settings.filter_case_sensitive_keywords,
                "max_file_size_mb": settings.filter_max_file_size_mb,
                "min_file_size_bytes": settings.filter_min_file_size_bytes,
            }

        # Knowledge-base/category mapping records are database-backed and cached by
        # these services. The revision also reaches other workers through the file.
        if revision_changed:
            from services.ai_analyzer import ai_analyzer
            from services.dify_service import multi_kb_manager
            ai_analyzer.processors.clear()
            multi_kb_manager.clear_cache()
    except Exception:
        # Do not include config data or exception strings in logs; an SDK exception
        # can accidentally include connection credentials.
        logger.warning("服务配置热刷新失败")


def _refresh_dify_service(service):
    from requests import Session
    service.api_key = settings.dify_api_key
    service.base_url = settings.dify_base_url.rstrip("/")
    service.dataset_id = settings.dify_dataset_id
    service.knowledge_base = None
    service.session.close()
    service.session = Session()
    if service.api_key:
        service.session.headers.update({
            "Authorization": f"Bearer {service.api_key}",
            "Content-Type": "application/json",
        })


def _new_openai_client():
    if not settings.openai_api_key:
        return None
    try:
        from openai import OpenAI
        kwargs = {"api_key": settings.openai_api_key,
                  "timeout": settings.ai_request_timeout, "max_retries": 1}
        if settings.openai_base_url:
            kwargs["base_url"] = settings.openai_base_url
        return OpenAI(**kwargs)
    except Exception:
        # SDK exceptions may include request configuration. Keep secrets out of logs.
        logger.warning("模型客户端热刷新失败")
        return None


def _new_s3_client():
    if not settings.s3_access_key or not settings.s3_secret_key:
        return None
    try:
        import boto3
        client_kwargs = {}
        if settings.s3_endpoint_url:
            endpoint_url = settings.s3_endpoint_url.strip()
            if not endpoint_url.startswith("http"):
                endpoint_url = f"https://{endpoint_url}"
            client_kwargs["endpoint_url"] = endpoint_url
        session = boto3.Session(
            aws_access_key_id=settings.s3_access_key,
            aws_secret_access_key=settings.s3_secret_key,
            region_name=settings.s3_region,
        )
        return session.client("s3", **client_kwargs)
    except Exception:
        # boto3 errors can include a custom endpoint; do not emit exception text.
        logger.warning("S3 客户端热刷新失败")
        return None
