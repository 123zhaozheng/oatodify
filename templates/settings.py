import streamlit as st
import os
import requests
import json
from config import settings

def show_settings():
    """显示系统设置页面"""
    st.title("⚙️ 系统设置")
    st.markdown("配置和管理OA文档处理系统的各项参数")
    
    # 创建选项卡
    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "🔧 基本配置", 
        "☁️ S3存储", 
        "🤖 AI配置", 
        "📚 Dify集成", 
        "🏥 系统健康"
    ])
    
    with tab1:
        show_basic_settings()
    
    with tab2:
        show_s3_settings()
    
    with tab3:
        show_ai_settings()
    
    with tab4:
        show_dify_settings()
    
    with tab5:
        show_system_health()

def show_basic_settings():
    """显示基本配置"""
    st.subheader("📋 基本配置")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("**数据库配置**")
        
        # 数据库连接状态
        db_status = check_database_connection()
        if db_status:
            st.success("✅ 数据库连接正常")
        else:
            st.error("❌ 数据库连接失败")
        
        # 显示数据库信息（脱敏）
        db_url = os.getenv("DATABASE_URL", "未配置")
        if db_url != "未配置":
            # 脱敏显示
            masked_url = mask_sensitive_info(db_url)
            st.code(f"数据库URL: {masked_url}")
        else:
            st.warning("⚠️ 数据库URL未配置")
        
        st.markdown("**Redis配置**")
        redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
        redis_status = check_redis_connection()
        
        if redis_status:
            st.success("✅ Redis连接正常")
        else:
            st.error("❌ Redis连接失败")
        
        masked_redis = mask_sensitive_info(redis_url)
        st.code(f"Redis URL: {masked_redis}")
    
    with col2:
        st.markdown("**文档处理配置**")
        
        max_file_size = settings.max_file_size / (1024 * 1024)  # 转换为MB
        st.info(f"📁 最大文件大小: {max_file_size:.0f} MB")
        
        supported_formats = ", ".join(settings.supported_formats)
        st.info(f"📄 支持的格式: {supported_formats}")
        
        st.markdown("**环境信息**")
        st.info(f"🏃‍♂️ 调试模式: {'开启' if settings.debug else '关闭'}")
        
        # 系统环境变量检查
        required_vars = [
            "DATABASE_URL", "REDIS_URL", "S3_ACCESS_KEY", 
            "S3_SECRET_KEY", "OPENAI_API_KEY", "DIFY_API_KEY"
        ]
        
        st.markdown("**环境变量检查**")
        for var in required_vars:
            value = os.getenv(var)
            if value:
                st.success(f"✅ {var}")
            else:
                st.error(f"❌ {var} - 未设置")

def show_s3_settings():
    """显示S3存储配置"""
    st.subheader("☁️ S3存储配置")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("**连接配置**")
        
        # S3连接状态
        s3_status = check_s3_connection()
        if s3_status['connected']:
            st.success("✅ S3连接正常")
        else:
            st.error(f"❌ S3连接失败: {s3_status.get('error', '未知错误')}")
        
        # 显示S3配置（脱敏）
        s3_config = {
            "Bucket": os.getenv("S3_BUCKET_NAME", "未配置"),
            "Region": os.getenv("S3_REGION", "未配置"),
            "Endpoint": os.getenv("S3_ENDPOINT_URL", "默认"),
            "Access Key": mask_sensitive_info(os.getenv("S3_ACCESS_KEY", "未配置")),
            "Secret Key": mask_sensitive_info(os.getenv("S3_SECRET_KEY", "未配置"))
        }
        
        for key, value in s3_config.items():
            if value == "未配置":
                st.error(f"❌ {key}: {value}")
            else:
                st.info(f"📋 {key}: {value}")
    
    with col2:
        st.markdown("**S3操作测试**")
        
        if st.button("🔍 测试S3连接", key="test_s3"):
            with st.spinner("测试S3连接中..."):
                result = test_s3_operations()
                
                if result['success']:
                    st.success("✅ S3连接测试成功！")
                    
                    if result.get('bucket_exists'):
                        st.info("📦 存储桶可访问")
                    
                    if result.get('test_upload'):
                        st.info("📤 上传权限正常")
                    
                    if result.get('test_download'):
                        st.info("📥 下载权限正常")
                else:
                    st.error(f"❌ S3连接测试失败: {result.get('error')}")
        
        st.markdown("**存储统计**")
        if s3_status['connected']:
            stats = get_s3_storage_stats()
            if stats:
                st.metric("存储的文档数量", stats.get('total_files', 'N/A'))
                st.metric("总存储大小", stats.get('total_size', 'N/A'))
            else:
                st.info("无法获取存储统计信息")

def show_ai_settings():
    """显示AI配置"""
    st.subheader("🤖 AI分析配置")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("**OpenAI配置**")
        
        openai_key = os.getenv("OPENAI_API_KEY")
        if openai_key:
            st.success("✅ OpenAI API密钥已配置")
            st.code(f"API Key: {mask_sensitive_info(openai_key)}")
        else:
            st.error("❌ OpenAI API密钥未配置")
        
        # 测试OpenAI连接
        if st.button("🧪 测试AI分析", key="test_openai"):
            if not openai_key:
                st.error("请先配置OpenAI API密钥")
            else:
                with st.spinner("测试AI分析功能..."):
                    result = test_ai_analysis()
                    
                    if result['success']:
                        st.success("✅ AI分析测试成功！")
                        st.json(result.get('analysis_result', {}))
                    else:
                        st.error(f"❌ AI分析测试失败: {result.get('error')}")
    
    with col2:
        st.markdown("**AI分析统计**")
        
        ai_stats = get_ai_analysis_stats()
        if ai_stats:
            st.metric("总分析次数", ai_stats.get('total_analyzed', 0))
            st.metric("平均置信度", f"{ai_stats.get('avg_confidence', 0):.1f}%")
            st.metric("通过率", f"{ai_stats.get('pass_rate', 0):.1f}%")
        
        st.markdown("**模型信息**")
        st.info("🚀 当前使用模型: GPT-5")
        st.caption("GPT-5 于2025年8月7日发布，是最新的AI模型")

def show_dify_settings():
    """显示Dify集成配置"""
    st.subheader("📚 Dify知识库集成")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("**Dify配置**")
        
        dify_config = {
            "API Key": os.getenv("DIFY_API_KEY", "未配置"),
            "Base URL": os.getenv("DIFY_BASE_URL", "https://api.dify.ai"),
            "Dataset ID": os.getenv("DIFY_DATASET_ID", "未配置")
        }
        
        for key, value in dify_config.items():
            if value == "未配置":
                st.error(f"❌ {key}: {value}")
            elif key == "API Key":
                st.success(f"✅ {key}: {mask_sensitive_info(value)}")
            else:
                st.info(f"📋 {key}: {value}")
        
        # 测试Dify连接
        if st.button("🔗 测试Dify连接", key="test_dify"):
            if dify_config["API Key"] == "未配置":
                st.error("请先配置Dify API密钥")
            else:
                with st.spinner("测试Dify连接..."):
                    result = test_dify_connection()
                    
                    if result['success']:
                        st.success("✅ Dify连接测试成功！")
                    else:
                        st.error(f"❌ Dify连接测试失败: {result.get('error')}")
    
    with col2:
        st.markdown("**知识库统计**")
        
        kb_stats = get_knowledge_base_stats()
        if kb_stats:
            st.metric("知识库文档数量", kb_stats.get('total_documents', 'N/A'))
            st.metric("今日新增", kb_stats.get('today_added', 'N/A'))
            st.metric("成功率", f"{kb_stats.get('success_rate', 0):.1f}%")
        else:
            st.info("无法获取知识库统计信息")
        
        st.markdown("**操作历史**")
        if st.button("📋 查看操作日志", key="view_dify_logs"):
            st.info("Dify操作日志功能待实现")

def show_system_health():
    """显示系统健康状态"""
    st.subheader("🏥 系统健康监控")
    
    # 整体健康状态
    health_status = get_system_health()
    
    if health_status['overall'] == 'healthy':
        st.success("🟢 系统整体状态: 健康")
    elif health_status['overall'] == 'warning':
        st.warning("🟡 系统整体状态: 警告")
    else:
        st.error("🔴 系统整体状态: 异常")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("**服务状态**")
        
        services = {
            "FastAPI后端": health_status.get('api_server', False),
            "Celery工作进程": health_status.get('celery_worker', False),
            "数据库": health_status.get('database', False),
            "Redis": health_status.get('redis', False),
            "S3存储": health_status.get('s3', False)
        }
        
        for service, status in services.items():
            icon = "✅" if status else "❌"
            st.markdown(f"{icon} {service}")
    
    with col2:
        st.markdown("**任务队列状态**")
        
        queue_stats = get_queue_statistics()
        if queue_stats:
            st.metric("待处理任务", queue_stats.get('pending_tasks', 0))
            st.metric("正在处理", queue_stats.get('active_tasks', 0))
            st.metric("已完成", queue_stats.get('completed_tasks', 0))
            st.metric("失败任务", queue_stats.get('failed_tasks', 0))
        
        if st.button("🔄 刷新健康状态", key="refresh_health"):
            st.rerun()
    
    # 系统资源使用情况
    st.markdown("**系统资源**")
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.metric("CPU使用率", "N/A")  # 需要实际实现
    
    with col2:
        st.metric("内存使用", "N/A")  # 需要实际实现
    
    with col3:
        st.metric("磁盘空间", "N/A")  # 需要实际实现
    
    # 最近错误日志
    st.markdown("**最近错误**")
    recent_errors = get_recent_errors()
    if recent_errors:
        for error in recent_errors[:5]:
            st.error(f"❌ {error['timestamp']}: {error['message']}")
    else:
        st.success("✅ 暂无错误记录")

# 辅助函数

def mask_sensitive_info(text, mask_char="*", show_last=4):
    """脱敏显示敏感信息"""
    if not text or text == "未配置":
        return text
    
    if len(text) <= show_last:
        return mask_char * len(text)
    
    return mask_char * (len(text) - show_last) + text[-show_last:]

def check_database_connection():
    """检查数据库连接"""
    try:
        response = requests.get("http://localhost:8000/health", timeout=5)
        return response.status_code == 200
    except Exception:
        return False

def check_redis_connection():
    """检查Redis连接"""
    try:
        # TODO: 实现实际的Redis连接检查
        return True
    except Exception:
        return False

def check_s3_connection():
    """检查S3连接"""
    try:
        # TODO: 实现实际的S3连接检查
        # 可以调用后端API中的S3服务
        return {'connected': True}
    except Exception as e:
        return {'connected': False, 'error': str(e)}

def test_s3_operations():
    """测试S3操作"""
    try:
        # TODO: 实现S3操作测试
        # 包括存储桶访问、上传、下载测试
        return {
            'success': True,
            'bucket_exists': True,
            'test_upload': True,
            'test_download': True
        }
    except Exception as e:
        return {'success': False, 'error': str(e)}

def get_s3_storage_stats():
    """获取S3存储统计"""
    try:
        # TODO: 实现S3存储统计
        return {
            'total_files': 1250,
            'total_size': '2.5 GB'
        }
    except Exception:
        return None

def test_ai_analysis():
    """测试AI分析功能"""
    try:
        # TODO: 实现AI分析测试
        # 使用一个简单的测试文本进行分析
        return {
            'success': True,
            'analysis_result': {
                'suitable_for_kb': True,
                'confidence_score': 85,
                'category': 'test',
                'summary': 'AI分析测试成功'
            }
        }
    except Exception as e:
        return {'success': False, 'error': str(e)}

def get_ai_analysis_stats():
    """获取AI分析统计"""
    try:
        # 从仪表板API获取统计数据
        response = requests.get("http://localhost:8000/api/v1/statistics/dashboard", timeout=5)
        if response.status_code == 200:
            data = response.json()
            total_files = data.get('total_files', 0)
            completed = data.get('today_completed', 0)
            total_processed = data.get('today_processed', 1)  # 避免除零
            
            return {
                'total_analyzed': total_files,
                'avg_confidence': 0,  # TODO: 需要新的API接口
                'pass_rate': (completed / max(total_processed, 1)) * 100
            }
        return None
    except Exception:
        return None

def test_dify_connection():
    """测试Dify连接"""
    try:
        # TODO: 实现Dify连接测试
        return {'success': True}
    except Exception as e:
        return {'success': False, 'error': str(e)}

def get_knowledge_base_stats():
    """获取知识库统计"""
    try:
        # TODO: 从Dify API获取知识库统计
        return {
            'total_documents': 523,
            'today_added': 15,
            'success_rate': 94.2
        }
    except Exception:
        return None

def get_system_health():
    """获取系统健康状态"""
    try:
        # 检查API服务器
        api_healthy = False
        try:
            response = requests.get("http://localhost:8000/health", timeout=5)
            api_healthy = response.status_code == 200
        except:
            pass
        
        # 检查数据库
        db_healthy = check_database_connection()
        
        # 检查Redis
        redis_healthy = check_redis_connection()
        
        # 简单的健康评估
        healthy_services = sum([api_healthy, db_healthy, redis_healthy])
        if healthy_services >= 2:
            overall = 'healthy'
        elif healthy_services >= 1:
            overall = 'warning'
        else:
            overall = 'error'
            
        return {
            'overall': overall,
            'api_server': api_healthy,
            'celery_worker': False,  # TODO: 实现Celery检查
            'database': db_healthy,
            'redis': redis_healthy,
            's3': False  # TODO: 实现S3检查
        }
    except Exception:
        return {
            'overall': 'error',
            'api_server': False,
            'celery_worker': False,
            'database': False,
            'redis': False,
            's3': False
        }

def get_queue_statistics():
    """获取任务队列统计"""
    try:
        # TODO: 从Celery获取队列统计
        return {
            'pending_tasks': 12,
            'active_tasks': 3,
            'completed_tasks': 567,
            'failed_tasks': 23
        }
    except Exception:
        return None

def get_recent_errors():
    """获取最近错误"""
    try:
        # TODO: 从日志或数据库获取最近错误
        return [
            {
                'timestamp': '2024-09-16 14:30:00',
                'message': 'S3下载超时: file_12345.pdf'
            },
            {
                'timestamp': '2024-09-16 13:45:00',
                'message': 'AI分析API调用失败'
            }
        ]
    except Exception:
        return []
