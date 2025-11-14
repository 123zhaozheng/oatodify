import streamlit as st
import requests
import time
import json
from datetime import datetime
import sys
import os

# 添加utils目录到Python路径
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
from utils.api_config import get_files_api_url


def show_maintenance():
    """显示维护管理页面"""
    st.title("🛠️ 系统维护管理")

    st.markdown("""
    这个页面提供文档清理和维护功能，帮助保持知识库的整洁和准确性。

    ⚠️ **注意**: 删除操作不可逆，请谨慎使用！
    """)

    # 创建两个标签页
    tab1, tab2, tab3 = st.tabs(["📋 版本去重", "🗑️ 过期清理", "📊 任务监控"])

    with tab1:
        show_version_cleanup_tab()

    with tab2:
        show_expired_cleanup_tab()

    with tab3:
        show_task_monitor_tab()


def show_version_cleanup_tab():
    """显示版本去重标签页"""
    st.header("🔄 总行发文版本去重")

    st.markdown("""
    ### 功能说明
    自动检测和清理总行发文中的旧版本文档：

    1. 🔍 检测文档名中的修订关键词（修订、修改、更新、废止等）
    2. 📝 提取《》中的标题进行模糊匹配
    3. 🤖 使用AI分析文档版本号（如：昆农商发【2025】xxx号）
    4. 🗑️ 删除旧版本，保留最新版本

    ### 当前设置
    """)

    col1, col2 = st.columns(2)

    with col1:
        st.info("**定时任务**: 每天凌晨2点自动执行")
        st.info("**默认处理**: 50个文档/次")

    with col2:
        st.warning("**修订关键词**")
        st.code("修订、修改、更新、调整、变更\n修正、补充、完善、废止、废除")

    st.divider()

    # 手动触发区域
    st.subheader("⚡ 手动触发")

    col1, col2, col3 = st.columns([2, 1, 1])

    with col1:
        limit = st.slider(
            "处理文档数量",
            min_value=10,
            max_value=200,
            value=50,
            step=10,
            help="一次性处理的文档数量，建议先从小数量开始测试"
        )

    with col2:
        st.write("")  # 占位
        st.write("")  # 占位
        dry_run = st.checkbox("预览模式", value=False, help="不实际删除，仅显示会删除的文档")

    with col3:
        st.write("")  # 占位
        st.write("")  # 占位

    if st.button("🚀 开始清理", key="start_version_cleanup", type="primary", use_container_width=True):
        if dry_run:
            st.warning("⚠️ 预览模式暂未实现，将直接执行清理操作")

        with st.spinner("正在提交清理任务..."):
            result = trigger_clean_version_duplicates(limit)

            if result.get('success'):
                st.success(f"✅ {result.get('message')}")

                # 显示任务信息
                task_id = result.get('task_id')
                st.info(f"📝 **任务ID**: `{task_id}`")
                st.info(f"📄 **处理数量**: {limit} 个文档")

                # 保存到session state用于监控
                if 'running_tasks' not in st.session_state:
                    st.session_state.running_tasks = []

                st.session_state.running_tasks.append({
                    'task_id': task_id,
                    'type': 'version_cleanup',
                    'limit': limit,
                    'started_at': datetime.now().isoformat(),
                    'status': 'running'
                })

                st.success("💡 可以在【任务监控】标签页查看执行进度")
            else:
                st.error(f"❌ 任务提交失败: {result.get('error', '未知错误')}")


def show_expired_cleanup_tab():
    """显示过期清理标签页"""
    st.header("🗑️ 过期文档清理")

    st.markdown("""
    ### 功能说明
    自动检查和清理过期文档：

    1. 📅 检查ai_metadata中的expiration_date字段
    2. ⏰ 对比当前日期判断是否过期
    3. 🤖 如果没有元数据，使用AI判断有效期
    4. 🗑️ 删除已过期的文档

    ### 当前设置
    """)

    col1, col2 = st.columns(2)

    with col1:
        st.info("**定时任务**: 每周日凌晨3点自动执行（每7天一次）")
        st.info("**默认处理**: 50个文档/次")

    with col2:
        st.success("**永久有效标识**")
        st.code("永久、无、permanent\nnone、never、长期")

    st.divider()

    # 手动触发区域
    st.subheader("⚡ 手动触发")

    col1, col2, col3 = st.columns([2, 1, 1])

    with col1:
        limit = st.slider(
            "处理文档数量",
            min_value=10,
            max_value=200,
            value=50,
            step=10,
            help="一次性处理的文档数量",
            key="expired_limit"
        )

    with col2:
        st.write("")  # 占位
        st.write("")  # 占位
        dry_run = st.checkbox("预览模式", value=False, help="不实际删除，仅显示会删除的文档", key="expired_dry_run")

    with col3:
        st.write("")  # 占位
        st.write("")  # 占位

    if st.button("🚀 开始清理", key="start_expired_cleanup", type="primary", use_container_width=True):
        if dry_run:
            st.warning("⚠️ 预览模式暂未实现，将直接执行清理操作")

        with st.spinner("正在提交清理任务..."):
            result = trigger_clean_expired_documents(limit)

            if result.get('success'):
                st.success(f"✅ {result.get('message')}")

                # 显示任务信息
                task_id = result.get('task_id')
                st.info(f"📝 **任务ID**: `{task_id}`")
                st.info(f"📄 **处理数量**: {limit} 个文档")

                # 保存到session state用于监控
                if 'running_tasks' not in st.session_state:
                    st.session_state.running_tasks = []

                st.session_state.running_tasks.append({
                    'task_id': task_id,
                    'type': 'expired_cleanup',
                    'limit': limit,
                    'started_at': datetime.now().isoformat(),
                    'status': 'running'
                })

                st.success("💡 可以在【任务监控】标签页查看执行进度")
            else:
                st.error(f"❌ 任务提交失败: {result.get('error', '未知错误')}")


def show_task_monitor_tab():
    """显示任务监控标签页"""
    st.header("📊 任务监控")

    # 刷新按钮
    col1, col2, col3 = st.columns([1, 1, 3])
    with col1:
        if st.button("🔄 刷新状态", key="refresh_tasks"):
            st.rerun()

    with col2:
        if st.button("🗑️ 清空历史", key="clear_tasks"):
            st.session_state.running_tasks = []
            st.rerun()

    st.divider()

    # 显示运行中的任务
    if 'running_tasks' not in st.session_state or not st.session_state.running_tasks:
        st.info("📭 暂无运行中的任务")
        st.markdown("""
        ### 💡 提示
        - 在【版本去重】或【过期清理】标签页提交任务后，会在这里显示
        - 可以实时查看任务执行状态和结果
        """)
        return

    st.success(f"📋 共有 {len(st.session_state.running_tasks)} 个任务")

    # 显示每个任务的状态
    for idx, task_info in enumerate(st.session_state.running_tasks):
        task_id = task_info['task_id']
        task_type = task_info['type']
        started_at = task_info['started_at']

        # 任务类型显示
        if task_type == 'version_cleanup':
            task_type_name = "🔄 版本去重"
        else:
            task_type_name = "🗑️ 过期清理"

        with st.expander(f"{task_type_name} - {task_id[:12]}...", expanded=(idx == len(st.session_state.running_tasks) - 1)):
            st.markdown(f"""
            **任务ID**: `{task_id}`
            **任务类型**: {task_type_name}
            **处理数量**: {task_info.get('limit', 'N/A')} 个文档
            **开始时间**: {started_at}
            """)

            # 查询任务状态
            status_result = check_task_status(task_id)

            if status_result:
                state = status_result.get('state', 'UNKNOWN')
                ready = status_result.get('ready', False)
                successful = status_result.get('successful')

                # 显示状态
                col1, col2 = st.columns(2)

                with col1:
                    if state == 'PENDING':
                        st.warning("⏳ 等待执行")
                    elif state == 'PROGRESS':
                        st.info("🔄 执行中...")
                    elif state == 'SUCCESS':
                        st.success("✅ 执行成功")
                    elif state == 'FAILURE':
                        st.error("❌ 执行失败")
                    else:
                        st.warning(f"❓ 未知状态: {state}")

                with col2:
                    if ready:
                        st.metric("状态", "已完成" if successful else "失败")
                    else:
                        st.metric("状态", "进行中")

                # 显示详细结果
                if ready and successful:
                    result = status_result.get('result', {})

                    st.success("### 📈 执行结果")

                    col1, col2, col3, col4 = st.columns(4)

                    with col1:
                        st.metric("处理文档", result.get('processed', 0))

                    with col2:
                        if task_type == 'version_cleanup':
                            st.metric("发现重复", result.get('duplicates_found', 0))
                        else:
                            st.metric("元数据过期", result.get('expired_by_metadata', 0))

                    with col3:
                        if task_type == 'version_cleanup':
                            st.metric("删除文档", result.get('deleted', 0))
                        else:
                            st.metric("AI判定过期", result.get('expired_by_ai', 0))

                    with col4:
                        st.metric("错误数", result.get('errors', 0))

                    # 显示详细信息
                    details = result.get('details', [])
                    if details:
                        st.markdown("### 📋 详细信息")
                        for detail in details[:5]:  # 只显示前5条
                            if task_type == 'version_cleanup':
                                st.info(f"""
                                **标题**: {detail.get('title')}
                                **最新版本**: {detail.get('latest_document')}
                                **删除数量**: {detail.get('deleted_count')}
                                **判断理由**: {detail.get('reasoning')}
                                """)
                            else:
                                st.info(f"""
                                **文件名**: {detail.get('filename')}
                                **检查方式**: {detail.get('check_method')}
                                **过期日期**: {detail.get('expiration_date', 'N/A')}
                                **判断理由**: {detail.get('reasoning', 'N/A')}
                                """)

                        if len(details) > 5:
                            st.caption(f"... 还有 {len(details) - 5} 条记录未显示")

                elif ready and not successful:
                    error = status_result.get('error', '未知错误')
                    st.error(f"### ❌ 执行错误\n{error}")

                else:
                    info = status_result.get('info', '任务正在执行中...')
                    st.info(f"💬 {info}")
            else:
                st.error("❌ 无法查询任务状态")


# API调用函数
def trigger_clean_version_duplicates(limit=50):
    """触发版本去重清理"""
    try:
        base_url = get_files_api_url("").rstrip('/files/')
        url = f"{base_url}/maintenance/clean-version-duplicates?limit={limit}"
        response = requests.post(url, timeout=10)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        return {'success': False, 'error': f'API调用失败: {str(e)}'}
    except Exception as e:
        return {'success': False, 'error': str(e)}


def trigger_clean_expired_documents(limit=50):
    """触发过期文档清理"""
    try:
        base_url = get_files_api_url("").rstrip('/files/')
        url = f"{base_url}/maintenance/clean-expired-documents?limit={limit}"
        response = requests.post(url, timeout=10)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        return {'success': False, 'error': f'API调用失败: {str(e)}'}
    except Exception as e:
        return {'success': False, 'error': str(e)}


def check_task_status(task_id):
    """查询任务状态"""
    try:
        base_url = get_files_api_url("").rstrip('/files/')
        url = f"{base_url}/maintenance/task-status/{task_id}"
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        st.error(f"查询任务状态失败: {str(e)}")
        return None
    except Exception as e:
        st.error(f"查询失败: {str(e)}")
        return None
