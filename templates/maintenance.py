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
    tab1, tab2, tab3, tab4 = st.tabs(["📋 版本去重", "🗑️ 过期清理", "📥 数据导入", "📊 任务监控"])

    with tab1:
        show_version_cleanup_tab()

    with tab2:
        show_expired_cleanup_tab()

    with tab3:
        show_data_import_tab()

    with tab4:
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
    st.header("🗑️ 过期文档和重复文档清理")

    st.markdown("""
    ### 功能说明
    自动检查和清理过期文档及重复文档：

    **过期文档清理：**
    1. 📅 检查ai_metadata中的expiration_date字段
    2. ⏰ 对比当前日期判断是否过期
    3. 🤖 如果没有元数据，使用AI判断有效期
    4. 🗑️ 删除已过期的文档

    **重复文档清理（增强）：**
    5. 🔍 查询指定天数内完成的文档
    6. 📝 通过文件名前缀匹配查找重复文档
    7. 🧹 保留最新版本，删除旧版本

    ### 当前设置
    """)

    col1, col2 = st.columns(2)

    with col1:
        st.info("**定时任务**: 每周日凌晨3点自动执行（每7天一次）")
        st.info("**默认处理**: 50个文档/次，重复检查5天")

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
            max_value=5000,
            value=50,
            step=10,
            help="一次性处理的文档数量",
            key="expired_limit"
        )

    with col2:
        days = st.slider(
            "重复检查天数",
            min_value=1,
            max_value=30,
            value=5,
            step=1,
            help="查询最近多少天内完成的文档进行重复检查",
            key="duplicate_days"
        )

    with col3:
        st.write("")  # 占位
        st.write("")  # 占位
        dry_run = st.checkbox("预览模式", value=False, help="不实际删除，仅显示会删除的文档", key="expired_dry_run")

    if st.button("🚀 开始清理", key="start_expired_cleanup", type="primary", use_container_width=True):
        if dry_run:
            st.warning("⚠️ 预览模式暂未实现，将直接执行清理操作")

        with st.spinner("正在提交清理任务..."):
            result = trigger_clean_expired_documents(limit, days)

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
                    'days': days,
                    'started_at': datetime.now().isoformat(),
                    'status': 'running'
                })

                st.success("💡 可以在【任务监控】标签页查看执行进度")
            else:
                st.error(f"❌ 任务提交失败: {result.get('error', '未知错误')}")


def show_data_import_tab():
    """显示数据导入标签页"""
    st.header("📥 DAT文件数据导入")

    st.markdown("""
    ### 功能说明
    从数据组提供的.dat文件中导入文件信息：

    1. 📄 读取DAT文件（使用ASCII码1作为字段分隔符）
    2. 🔍 检测已存在的记录
    3. ➕ 增量导入新记录
    4. ♻️ 可选择更新已存在的记录

    ### 当前设置
    """)

    col1, col2 = st.columns(2)

    with col1:
        st.info("**定时任务**: 每天凌晨2:10自动执行")
        st.info("**导入目录**: `/data/dat_files`")

    with col2:
        st.success("**字段分隔符**: ASCII码1（`\\x01`）")
        st.success("**导入模式**: 增量导入（默认跳过已存在）")

    st.divider()

    # 查询导入状态
    st.subheader("📊 导入历史")

    with st.spinner("正在加载导入统计..."):
        import_status = get_import_status()

        if import_status:
            col1, col2 = st.columns(2)

            with col1:
                st.metric("总导入记录数", import_status.get('total_imported', 0))

            with col2:
                recent = import_status.get('recent_imports', [])
                if recent:
                    last_import = recent[0]
                    st.metric("最近导入日期", last_import.get('date', 'N/A'))
                else:
                    st.metric("最近导入日期", "暂无记录")

            # 显示最近的导入记录
            if recent:
                st.markdown("#### 最近10次导入")
                import pandas as pd

                df = pd.DataFrame(recent)
                df.columns = ['日期', '来源', '数量']
                st.dataframe(df, use_container_width=True, hide_index=True)

    st.divider()

    # 手动触发区域
    st.subheader("⚡ 手动触发导入")

    col1, col2 = st.columns([3, 1])

    with col1:
        dat_file_path = st.text_input(
            "DAT文件路径（可选）",
            placeholder="留空则自动选择最新文件",
            help="输入完整的DAT文件路径，或留空让系统自动选择最新的文件"
        )

    with col2:
        st.write("")  # 占位
        st.write("")  # 占位
        update_existing = st.checkbox(
            "更新已存在记录",
            value=False,
            help="勾选则更新已存在的记录，不勾选则跳过已存在的记录"
        )

    col1, col2, col3 = st.columns([1, 1, 2])

    with col1:
        if st.button("🚀 开始导入", key="start_import", type="primary", use_container_width=True):
            with st.spinner("正在提交导入任务..."):
                # 准备请求参数
                import_params = {}
                if dat_file_path.strip():
                    import_params['dat_file_path'] = dat_file_path.strip()
                import_params['update_existing'] = update_existing

                result = trigger_import_dat_file(import_params)

                if result.get('success'):
                    st.success(f"✅ {result.get('message')}")

                    # 显示任务信息
                    task_id = result.get('task_id')
                    st.info(f"📝 **任务ID**: `{task_id}`")
                    st.info(f"📄 **更新模式**: {'是' if update_existing else '否'}")

                    # 保存到session state用于监控
                    if 'running_tasks' not in st.session_state:
                        st.session_state.running_tasks = []

                    st.session_state.running_tasks.append({
                        'task_id': task_id,
                        'type': 'dat_import',
                        'dat_file_path': dat_file_path or '自动选择',
                        'update_existing': update_existing,
                        'started_at': datetime.now().isoformat(),
                        'status': 'running'
                    })

                    st.success("💡 可以在【任务监控】标签页查看执行进度")
                else:
                    st.error(f"❌ 任务提交失败: {result.get('error', '未知错误')}")

    with col2:
        if st.button("🔄 刷新统计", key="refresh_import_stats", use_container_width=True):
            st.rerun()


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
        elif task_type == 'expired_cleanup':
            task_type_name = "🗑️ 过期清理"
        elif task_type == 'dat_import':
            task_type_name = "📥 数据导入"
        else:
            task_type_name = "❓ 未知任务"

        with st.expander(f"{task_type_name} - {task_id[:12]}...", expanded=(idx == len(st.session_state.running_tasks) - 1)):
            # 根据任务类型显示不同的信息
            if task_type == 'dat_import':
                st.markdown(f"""
                **任务ID**: `{task_id}`
                **任务类型**: {task_type_name}
                **DAT文件路径**: {task_info.get('dat_file_path', '自动选择')}
                **更新已存在记录**: {'是' if task_info.get('update_existing', False) else '否'}
                **开始时间**: {started_at}
                """)
            else:
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

                    # DAT导入任务的结果展示
                    if task_type == 'dat_import':
                        stats = result.get('stats', {})

                        col1, col2, col3, col4 = st.columns(4)

                        with col1:
                            st.metric("总行数", stats.get('total_lines', 0))

                        with col2:
                            st.metric("新增记录", stats.get('new_records', 0))

                        with col3:
                            st.metric("更新记录", stats.get('updated_records', 0))

                        with col4:
                            st.metric("错误数", stats.get('error_records', 0))

                        col1, col2 = st.columns(2)

                        with col1:
                            st.metric("解析成功", stats.get('parsed_lines', 0))

                        with col2:
                            st.metric("跳过记录", stats.get('skipped_records', 0))

                        # 显示错误信息
                        errors = stats.get('errors', [])
                        if errors:
                            st.markdown("### ⚠️ 错误信息")
                            for error in errors[:5]:  # 只显示前5条
                                st.warning(error)

                            if len(errors) > 5:
                                st.caption(f"... 还有 {len(errors) - 5} 条错误未显示")

                    # 其他任务的结果展示
                    else:
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


def trigger_clean_expired_documents(limit=50, days=5):
    """触发过期文档和重复文档清理"""
    try:
        base_url = get_files_api_url("").rstrip('/files/')
        url = f"{base_url}/maintenance/clean-expired-documents?limit={limit}&days={days}"
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


def trigger_import_dat_file(params):
    """触发DAT文件导入"""
    try:
        base_url = get_files_api_url("").rstrip('/files/')
        url = f"{base_url}/data/import-dat"
        response = requests.post(url, json=params, timeout=10)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        return {'success': False, 'error': f'API调用失败: {str(e)}'}
    except Exception as e:
        return {'success': False, 'error': str(e)}


def get_import_status():
    """获取导入状态统计"""
    try:
        base_url = get_files_api_url("").rstrip('/files/')
        url = f"{base_url}/data/import-status"
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        st.error(f"获取导入状态失败: {str(e)}")
        return None
    except Exception as e:
        st.error(f"获取失败: {str(e)}")
        return None
