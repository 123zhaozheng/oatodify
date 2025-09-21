import streamlit as st
import os
import requests
import json
import sys
from datetime import datetime
from typing import Any, Dict, List, Optional

# 添加utils目录到Python路径
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
from utils.api_config import get_statistics_api_url, get_system_api_url, get_files_api_url
from config import settings


def show_settings():
    """显示系统设置页面"""
    st.title("⚙️ 系统设置")
    st.markdown("配置和管理OA文档处理系统的各项参数")

    # 添加API连接测试
    st.markdown("### 🔗 API连接测试")
    col1, col2, col3 = st.columns([1, 1, 3])
    
    with col1:
        if st.button("🔄 刷新状态", key="settings_refresh"):
            st.rerun()
    
    with col2:
        if st.button("🧪 测试API连接", key="test_api_connection"):
            test_api_connection()
    
    st.markdown("---")

    system_snapshot = load_system_snapshot()
    s3_overview = load_s3_overview()
    dify_overview = load_dify_overview()

    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "🔧 基本配置",
        "☁️ S3存储",
        "🤖 AI配置",
        "📚 Dify集成",
        "🏥 系统健康",
    ])

    with tab1:
        show_basic_settings(system_snapshot, s3_overview, dify_overview)

    with tab2:
        show_s3_settings(system_snapshot, s3_overview)

    with tab3:
        show_ai_settings(system_snapshot)

    with tab4:
        show_dify_settings(dify_overview)

    with tab5:
        show_system_health(system_snapshot, s3_overview, dify_overview)


def load_system_snapshot() -> Dict[str, Any]:
    """调用后端获取系统状态快照"""
    try:
        url = get_system_api_url("status")
        response = requests.get(url, timeout=30)  # 增加超时时间
        response.raise_for_status()
        data = response.json()
        return data
    except requests.RequestException as exc:
        st.error(f"❌ 获取系统状态失败: {exc}")
        st.info("💡 提示：如果是超时错误，可能是数据库查询较慢，请稍后重试")
        return {}


def load_s3_overview() -> Dict[str, Any]:
    """获取S3状态和统计信息"""
    try:
        url = get_system_api_url("s3")
        response = requests.get(url, timeout=15)
        response.raise_for_status()
        data = response.json()
        return data
    except requests.RequestException as exc:
        st.error(f"❌ 获取S3状态失败: {exc}")
        return {}


def load_dify_overview() -> Dict[str, Any]:
    """获取Dify集成状态"""
    try:
        url = get_system_api_url("dify")
        response = requests.get(url, timeout=15)
        response.raise_for_status()
        data = response.json()
        return data
    except requests.RequestException as exc:
        st.error(f"❌ 获取Dify状态失败: {exc}")
        if "401" in str(exc) or "unauthorized" in str(exc).lower():
            st.info("💡 提示：Dify API密钥可能无效，请检查DIFY_API_KEY环境变量")
        return {}


def show_basic_settings(system_snapshot: Dict[str, Any], s3_overview: Dict[str, Any], dify_overview: Dict[str, Any]):
    """显示基本配置"""
    st.subheader("📋 基本配置")

    database_status = system_snapshot.get("database", {})
    redis_status = system_snapshot.get("redis", {})

    col1, col2 = st.columns(2)

    with col1:
        render_connection_status("数据库", database_status)

        db_url = os.getenv("DATABASE_URL", "未配置")
        if db_url != "未配置":
            st.code(f"数据库URL: {mask_sensitive_info(db_url)}")
        else:
            st.warning("⚠️ DATABASE_URL 未配置")

        st.markdown("**文档处理配置**")
        max_file_size_mb = settings.max_file_size / (1024 * 1024)
        st.info(f"📁 最大文件大小: {max_file_size_mb:.0f} MB")
        st.info(f"📄 支持的格式: {', '.join(settings.supported_formats)}")

    with col2:
        render_connection_status("Redis", redis_status)
        st.code(f"Redis URL: {mask_sensitive_info(settings.redis_url)}")

        if redis_status.get("connected"):
            redis_meta = []
            if redis_status.get("version"):
                redis_meta.append(f"版本: {redis_status['version']}")
            if redis_status.get("used_memory_human"):
                redis_meta.append(f"内存占用: {redis_status['used_memory_human']}")
            if redis_meta:
                st.caption(" | ".join(redis_meta))

        st.markdown("**环境变量检查**")
        required_vars = [
            "DATABASE_URL",
            "REDIS_URL",
            "S3_ACCESS_KEY",
            "S3_SECRET_KEY",
            "OPENAI_API_KEY",
            "DIFY_API_KEY",
        ]
        env_cols = st.columns(2)
        for idx, var in enumerate(required_vars):
            with env_cols[idx % 2]:
                value = os.getenv(var)
                if value:
                    st.success(f"✅ {var}")
                else:
                    st.error(f"❌ {var} - 未设置")

    st.markdown("**待办事项**")
    todo_items = build_todo_items(system_snapshot, s3_overview, dify_overview)
    if todo_items:
        for item in todo_items:
            st.warning(f"• {item}")
    else:
        st.success("暂无待办事项")


def show_s3_settings(system_snapshot: Dict[str, Any], s3_overview: Dict[str, Any]):
    """显示S3存储配置"""
    st.subheader("☁️ S3存储配置")

    status = system_snapshot.get("s3", {})
    render_connection_status("S3", status)

    config = s3_overview.get("config", {})
    st.markdown("**连接配置**")
    st.code(
        json.dumps(
            {
                "Bucket": config.get("bucket", "未配置"),
                "Region": config.get("region", "未配置"),
                "Endpoint": config.get("endpoint", "默认"),
                "Access Key": mask_sensitive_info(os.getenv("S3_ACCESS_KEY", "未配置")),
                "Secret Key": mask_sensitive_info(os.getenv("S3_SECRET_KEY", "未配置")),
            },
            ensure_ascii=False,
            indent=2,
        )
    )

    stats = s3_overview.get("stats")
    if stats and stats.get("success", True):
        st.markdown("**存储统计 (采样)**")
        metric_cols = st.columns(3)
        with metric_cols[0]:
            st.metric("对象数量 (采样)", stats.get("object_count_sample", 0))
        with metric_cols[1]:
            st.metric("总大小 (采样)", format_bytes(stats.get("total_size_bytes_sample", 0)))
        with metric_cols[2]:
            st.metric("是否完整扫描", "是" if stats.get("sample_complete") else "否")
    else:
        st.info("暂无S3存储统计数据")

    if st.button("🧪 运行S3诊断", key="s3_diagnostics"):
        result = trigger_s3_diagnostics()
        if result.get("success"):
            st.success("S3诊断完成")
            inspected = result.get("diagnostics", {}).get("inspected_object")
            if inspected:
                st.caption(
                    f"示例对象: {inspected.get('key')} | 大小: {format_bytes(inspected.get('size', 0))}"
                )
        else:
            st.error(f"诊断失败: {result.get('error', '未知错误')}")


def show_ai_settings(system_snapshot: Dict[str, Any]):
    """显示AI配置与统计"""
    st.subheader("🤖 AI配置")

    stats = get_ai_analysis_stats()
    if stats:
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("总文档数", stats.get("total_analyzed", 0))
        with col2:
            st.metric("平均置信度", f"{stats.get('avg_confidence', 0):.1f}%")
        with col3:
            st.metric("今日成功率", f"{stats.get('pass_rate', 0):.1f}%")
    else:
        st.info("暂无AI统计数据")

    st.markdown("**AI功能自检**")
    if st.button("🧪 运行AI分析自检", key="ai_self_test"):
        result = test_ai_analysis()
        if result.get("success"):
            st.success("AI分析组件运行正常")
            st.caption("已通过示例文本完成分析")
        else:
            st.error(f"AI分析自检失败: {result.get('error', '未知错误')}")


def show_dify_settings(dify_overview: Dict[str, Any]):
    """显示Dify集成信息"""
    st.subheader("📚 Dify集成")

    connection = dify_overview.get("connection", {})
    if connection.get("success"):
        st.success("✅ Dify API连接正常")
        st.caption(connection.get("message", "API返回成功"))
    else:
        st.error(f"❌ Dify API连接异常: {connection.get('error', '未知错误')}")

    if st.button("🔁 测试Dify连接", key="dify_test"):
        result = trigger_dify_test()
        if result.get("success"):
            st.success("Dify连接测试通过")
        else:
            st.error(f"连接失败: {result.get('error', '未知错误')}")

    dataset = dify_overview.get("dataset", {})
    document_total = dify_overview.get("document_total")
    pagination = dify_overview.get("pagination", {})

    st.markdown("**知识库信息**")
    info_items = {
        "知识库名称": dataset.get("name", "未配置"),
        "数据集ID": settings.dify_dataset_id or "未配置",
        "文档总数": document_total if document_total is not None else "未知",
        "最近更新": format_datetime(dataset.get("updated_at")) if dataset else "--",
    }
    st.code(json.dumps(info_items, ensure_ascii=False, indent=2))

    if pagination:
        st.caption(
            f"分页信息: 总数 {pagination.get('total', '未知')} | 每页 {pagination.get('limit', '未知')}"
        )


def show_system_health(system_snapshot: Dict[str, Any], s3_overview: Dict[str, Any], dify_overview: Dict[str, Any]):
    """显示系统健康状态"""
    st.subheader("🏥 系统健康")

    overall = system_snapshot.get("overall", "unknown")
    status_emoji = {
        "healthy": "🟢",
        "warning": "🟡",
        "error": "🔴",
    }.get(overall, "⚪")
    st.markdown(f"### {status_emoji} 综合状态: {overall.upper()}")

    services = {
        "API": system_snapshot.get("database", {}),
        "Redis": system_snapshot.get("redis", {}),
        "S3": system_snapshot.get("s3", {}),
        "Celery": system_snapshot.get("celery", {}),
    }
    service_cols = st.columns(len(services))
    for col, (label, status) in zip(service_cols, services.items()):
        with col:
            render_connection_status(label, status)

    queue = system_snapshot.get("queue", {})
    st.markdown("**处理队列概览**")
    queue_cols = st.columns(4)
    queue_metrics = [
        ("待处理", queue.get("PENDING", 0)),
        ("处理中", queue.get("in_progress", 0)),
        ("待审核", queue.get("AWAITING_APPROVAL", 0)),
        ("失败", queue.get("FAILED", 0)),
    ]
    for col, (label, value) in zip(queue_cols, queue_metrics):
        with col:
            st.metric(label, value)

    st.markdown("**最近错误**")
    recent_errors = system_snapshot.get("recent_errors", [])
    if recent_errors:
        for item in recent_errors:
            message = item.get("message", "")
            timestamp = format_datetime(item.get("created_at"))
            st.error(f"{timestamp or '--'} — {message}")
    else:
        st.success("✅ 暂无错误记录")

    st.markdown("**最新活动**")
    recent_activity = system_snapshot.get("recent_activity", [])
    if recent_activity:
        activity_rows = []
        for row in recent_activity:
            activity_rows.append(
                {
                    "时间": format_datetime(row.get("created_at")),
                    "文件ID": row.get("file_id"),
                    "步骤": row.get("step"),
                    "状态": row.get("status"),
                    "耗时(s)": row.get("duration_seconds"),
                }
            )
        st.dataframe(activity_rows, use_container_width=True, hide_index=True)
    else:
        st.info("暂无活动日志")


# --- 辅助函数 ---

def render_connection_status(label: str, status: Dict[str, Any]):
    """统一渲染连接状态"""
    if status.get("connected"):
        extra = []
        if status.get("workers"):
            extra.append(f"Workers: {len(status['workers'])}")
        if status.get("active_tasks") is not None:
            extra.append(f"活跃任务: {status['active_tasks']}")
        message = " | ".join(extra) if extra else "运行正常"
        st.success(f"✅ {label} 连接正常")
        if message:
            st.caption(message)
    else:
        error = status.get("error") or "未知错误"
        st.error(f"❌ {label} 连接异常: {error}")


def build_todo_items(system_snapshot: Dict[str, Any], s3_overview: Dict[str, Any], dify_overview: Dict[str, Any]) -> List[str]:
    """根据当前状态生成待办事项"""
    items: List[str] = []

    if not system_snapshot.get("database", {}).get("connected"):
        items.append("检查数据库连接配置和服务状态")
    if not system_snapshot.get("redis", {}).get("connected"):
        items.append("确认Redis服务地址与凭证配置")
    if not system_snapshot.get("s3", {}).get("connected"):
        items.append("完善S3存储配置并确保Bucket可访问")
    if not system_snapshot.get("celery", {}).get("connected"):
        items.append("启动并注册Celery Worker 以处理后台任务")

    connection = dify_overview.get("connection", {})
    if connection and not connection.get("success"):
        items.append("校验Dify API密钥与知识库ID配置")

    if not os.getenv("OPENAI_API_KEY"):
        items.append("设置 OPENAI_API_KEY 以启用AI分析能力")

    return list(dict.fromkeys(items))


def trigger_s3_diagnostics() -> Dict[str, Any]:
    """调用后端执行S3诊断"""
    try:
        url = get_system_api_url("s3/test")
        st.write(f"Debug: 正在调用S3诊断API: {url}")  # 调试信息
        response = requests.post(url, timeout=20)
        response.raise_for_status()
        data = response.json()
        st.success(f"✅ S3诊断API调用成功")
        return data
    except requests.RequestException as exc:
        st.error(f"❌ S3诊断API调用失败: {exc}")
        st.write(f"Debug: S3诊断API URL: {url}")
        return {"success": False, "error": str(exc)}


def trigger_dify_test() -> Dict[str, Any]:
    """调用后端测试Dify连接"""
    try:
        url = get_system_api_url("dify/test")
        st.write(f"Debug: 正在调用Dify测试API: {url}")  # 调试信息
        response = requests.post(url, timeout=10)
        response.raise_for_status()
        data = response.json()
        st.success(f"✅ Dify测试API调用成功")
        return data
    except requests.RequestException as exc:
        st.error(f"❌ Dify测试API调用失败: {exc}")
        st.write(f"Debug: Dify测试API URL: {url}")
        return {"success": False, "error": str(exc)}


def format_bytes(size_in_bytes: Optional[int]) -> str:
    """将字节大小转换为可读格式"""
    if not size_in_bytes:
        return "0 B"
    units = ["B", "KB", "MB", "GB", "TB"]
    size = float(size_in_bytes)
    for unit in units:
        if size < 1024:
            return f"{size:.2f} {unit}"
        size /= 1024
    return f"{size:.2f} PB"


def format_datetime(value: Optional[str]) -> Optional[str]:
    """格式化ISO日期字符串"""
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    except ValueError:
        return value


def mask_sensitive_info(text: Optional[str], mask_char: str = "*", show_last: int = 4) -> Optional[str]:
    """脱敏显示敏感信息"""
    if not text or text == "未配置":
        return text
    if len(text) <= show_last:
        return mask_char * len(text)
    return mask_char * (len(text) - show_last) + text[-show_last:]


def get_ai_analysis_stats() -> Optional[Dict[str, Any]]:
    """获取AI分析统计数据"""
    try:
        url = get_statistics_api_url("dashboard")
        response = requests.get(url, timeout=15)
        response.raise_for_status()
        data = response.json()

        total_files = data.get("total_files", 0)
        completed = data.get("today_completed", 0)
        total_processed = data.get("today_processed", 1)

        files_url = f"{get_files_api_url()}?page=1&size=50"
        files_resp = requests.get(files_url, timeout=15)
        files_resp.raise_for_status()
        files_data = files_resp.json()
        items = files_data.get("items", [])
        confidences = [item.get("ai_confidence_score") for item in items if item.get("ai_confidence_score") is not None]
        avg_confidence = sum(confidences) / len(confidences) if confidences else 0

        return {
            "total_analyzed": total_files,
            "avg_confidence": avg_confidence,
            "pass_rate": (completed / max(total_processed, 1)) * 100,
        }
    except requests.RequestException as exc:
        st.error(f"❌ 获取AI统计数据失败: {exc}")
        return None


def test_ai_analysis() -> Dict[str, Any]:
    """测试AI分析功能"""
    try:
        from services.ai_analyzer import ai_analyzer

        test_content = """
        这是一个测试文档，用于验证AI分析功能是否正常工作。
        文档包含了一些基本的业务信息和操作指南。
        该文档用于测试系统的文档分析能力。
        """

        test_metadata = {
            'file_type': 'txt',
            'pages': 1
        }

        result = ai_analyzer.analyze_document_content(
            content=test_content,
            filename="test_document.txt",
            metadata=test_metadata
        )

        return {
            'success': True,
            'analysis_result': result
        }
    except Exception as exc:
        return {'success': False, 'error': str(exc)}


def test_api_connection():
    """测试API连接"""
    st.markdown("**API连接测试结果：**")
    
    # 测试基础健康检查
    try:
        from utils.api_config import get_health_check_url
        health_url = get_health_check_url()
        response = requests.get(health_url, timeout=10)
        response.raise_for_status()
        st.success("✅ 基础API连接正常")
    except Exception as e:
        st.error(f"❌ 基础API连接失败: {e}")
    
    # 测试系统状态API
    try:
        url = get_system_api_url("status")
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        st.success("✅ 系统状态API连接正常")
    except Exception as e:
        st.error(f"❌ 系统状态API连接失败: {e}")
        if "timeout" in str(e).lower():
            st.info("💡 提示：系统状态API超时，可能是数据库查询较慢")
    
    # 显示当前API配置
    from utils.api_config import api_config
    st.markdown("**当前API配置：**")
    st.code(f"""
API基础URL: {api_config.base_url}
运行环境: {'Docker容器' if api_config._is_running_in_docker() else '开发环境'}
环境变量API_BASE_URL: {os.getenv('API_BASE_URL', '未设置')}
    """)


def format_file_size(size_bytes: int) -> str:
    """格式化文件大小"""
    if size_bytes == 0:
        return "0 B"

    size_names = ["B", "KB", "MB", "GB"]
    import math
    i = int(math.floor(math.log(size_bytes, 1024)))
    p = math.pow(1024, i)
    s = round(size_bytes / p, 2)
    return f"{s} {size_names[i]}"
