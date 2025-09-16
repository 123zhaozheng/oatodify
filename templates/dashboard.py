import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta
import requests
import json

def show_dashboard():
    """显示仪表板页面"""
    st.title("📊 OA文档处理仪表板")
    
    # 刷新按钮
    col1, col2, col3 = st.columns([1, 1, 2])
    with col1:
        if st.button("🔄 刷新数据", key="refresh_dashboard"):
            st.rerun()
    
    with col2:
        auto_refresh = st.checkbox("自动刷新", value=False, key="auto_refresh")
        if auto_refresh:
            st.info("每30秒自动刷新")
    
    # 获取统计数据
    try:
        # 这里应该调用后端API，暂时使用模拟数据
        stats_data = get_dashboard_stats()
        trend_data = get_trend_data()
        
        # 概览卡片
        st.subheader("📈 今日概览")
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.metric(
                label="总文档数",
                value=stats_data.get('total_files', 0),
                delta=None
            )
        
        with col2:
            st.metric(
                label="今日处理",
                value=stats_data.get('today_processed', 0),
                delta=None
            )
        
        with col3:
            st.metric(
                label="处理成功",
                value=stats_data.get('today_completed', 0),
                delta=None
            )
        
        with col4:
            st.metric(
                label="成功率",
                value=f"{stats_data.get('success_rate', 0):.1f}%",
                delta=None
            )
        
        # 状态分布图表
        st.subheader("📋 处理状态分布")
        col1, col2 = st.columns(2)
        
        with col1:
            # 饼图显示状态分布
            status_data = stats_data.get('status_distribution', {})
            if status_data:
                fig_pie = px.pie(
                    values=list(status_data.values()),
                    names=list(status_data.keys()),
                    title="文档状态分布"
                )
                fig_pie.update_traces(textposition='inside', textinfo='percent+label')
                st.plotly_chart(fig_pie, use_container_width=True)
            else:
                st.info("暂无状态分布数据")
        
        with col2:
            # 柱状图显示分类分布
            category_data = stats_data.get('category_distribution', {})
            if category_data:
                fig_bar = px.bar(
                    x=list(category_data.keys()),
                    y=list(category_data.values()),
                    title="业务分类分布",
                    labels={'x': '分类', 'y': '数量'}
                )
                fig_bar.update_layout(xaxis_tickangle=-45)
                st.plotly_chart(fig_bar, use_container_width=True)
            else:
                st.info("暂无分类分布数据")
        
        # 处理趋势
        st.subheader("📊 7天处理趋势")
        if trend_data and trend_data.get('trend_data'):
            df_trend = pd.DataFrame(trend_data['trend_data'])
            df_trend['date'] = pd.to_datetime(df_trend['date'])
            
            fig_line = go.Figure()
            fig_line.add_trace(go.Scatter(
                x=df_trend['date'],
                y=df_trend['total'],
                mode='lines+markers',
                name='总处理量',
                line=dict(color='blue')
            ))
            fig_line.add_trace(go.Scatter(
                x=df_trend['date'],
                y=df_trend['completed'],
                mode='lines+markers',
                name='成功数量',
                line=dict(color='green')
            ))
            fig_line.add_trace(go.Scatter(
                x=df_trend['date'],
                y=df_trend['failed'],
                mode='lines+markers',
                name='失败数量',
                line=dict(color='red')
            ))
            
            fig_line.update_layout(
                title="文档处理趋势",
                xaxis_title="日期",
                yaxis_title="数量",
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
            )
            st.plotly_chart(fig_line, use_container_width=True)
        else:
            st.info("暂无趋势数据")
        
        # 关键指标
        st.subheader("🚨 关键指标")
        col1, col2, col3 = st.columns(3)
        
        with col1:
            pending_approval = stats_data.get('pending_approval', 0)
            if pending_approval > 0:
                st.error(f"⏳ 待审核文档: {pending_approval} 个")
            else:
                st.success("✅ 无待审核文档")
        
        with col2:
            error_files = stats_data.get('error_files', 0)
            if error_files > 0:
                st.warning(f"❌ 错误文档: {error_files} 个")
            else:
                st.success("✅ 无错误文档")
        
        with col3:
            # 计算处理队列积压
            pending_count = status_data.get('pending', 0)
            if pending_count > 10:
                st.warning(f"📥 积压队列: {pending_count} 个")
            else:
                st.success("✅ 处理队列正常")
        
        # 快速操作
        st.subheader("⚡ 快速操作")
        col1, col2, col3 = st.columns(3)
        
        with col1:
            if st.button("🚀 批量处理文档", key="batch_process"):
                try:
                    # 调用批量处理API
                    result = trigger_batch_process()
                    if result.get('success'):
                        st.success("批量处理任务已提交！")
                    else:
                        st.error(f"提交失败: {result.get('error', '未知错误')}")
                except Exception as e:
                    st.error(f"操作失败: {str(e)}")
        
        with col2:
            if st.button("📋 查看待审核", key="view_pending"):
                st.session_state.page_selector = "👥 人工审核"
                st.rerun()
        
        with col3:
            if st.button("⚙️ 系统设置", key="view_settings"):
                st.session_state.page_selector = "⚙️ 系统设置"
                st.rerun()
        
        # 实时活动日志
        st.subheader("📝 最新活动")
        show_recent_activity()
        
        # 自动刷新
        if auto_refresh:
            import time
            time.sleep(30)
            st.rerun()
        
    except Exception as e:
        st.error(f"加载仪表板数据失败: {str(e)}")
        st.info("请检查后端服务是否正常运行")

def get_dashboard_stats():
    """获取仪表板统计数据"""
    try:
        # TODO: 替换为实际的API调用
        # response = requests.get("http://localhost:8000/api/v1/statistics/dashboard")
        # return response.json()
        
        # 模拟数据
        return {
            'total_files': 1250,
            'today_processed': 45,
            'today_completed': 38,
            'today_failed': 7,
            'success_rate': 84.4,
            'status_distribution': {
                'pending': 125,
                'completed': 856,
                'failed': 89,
                'awaiting_approval': 23,
                'processing': 12,
                'skipped': 145
            },
            'category_distribution': {
                'contract': 234,
                'report': 456,
                'notice': 189,
                'policy': 267,
                'other': 104
            },
            'pending_approval': 23,
            'error_files': 89
        }
    except Exception as e:
        st.error(f"获取统计数据失败: {str(e)}")
        return {}

def get_trend_data(days=7):
    """获取趋势数据"""
    try:
        # TODO: 替换为实际的API调用
        # response = requests.get(f"http://localhost:8000/api/v1/statistics/trend?days={days}")
        # return response.json()
        
        # 模拟数据
        import random
        from datetime import datetime, timedelta
        
        trend_data = []
        for i in range(days):
            date = (datetime.now() - timedelta(days=days-1-i)).date()
            total = random.randint(30, 80)
            completed = int(total * random.uniform(0.7, 0.9))
            failed = total - completed
            
            trend_data.append({
                'date': date.isoformat(),
                'total': total,
                'completed': completed,
                'failed': failed
            })
        
        return {'trend_data': trend_data}
    except Exception as e:
        st.error(f"获取趋势数据失败: {str(e)}")
        return {}

def trigger_batch_process():
    """触发批量处理"""
    try:
        # TODO: 替换为实际的API调用
        # response = requests.post("http://localhost:8000/api/v1/files/batch-process?limit=20")
        # return response.json()
        
        # 模拟返回
        return {'success': True, 'message': '批量处理任务已提交'}
    except Exception as e:
        return {'success': False, 'error': str(e)}

def show_recent_activity():
    """显示最近活动"""
    try:
        # 模拟最近活动数据
        activities = [
            {"time": "2 分钟前", "action": "文档处理完成", "file": "合同-20240901.pdf", "status": "success"},
            {"time": "5 分钟前", "action": "AI分析完成", "file": "报告-季度总结.docx", "status": "pending"},
            {"time": "8 分钟前", "action": "文档下载失败", "file": "政策-新规定.doc", "status": "error"},
            {"time": "12 分钟前", "action": "人工审核通过", "file": "通知-重要事项.pdf", "status": "success"},
            {"time": "15 分钟前", "action": "批量处理开始", "file": "20个文档", "status": "info"}
        ]
        
        for activity in activities[:5]:  # 只显示最近5条
            status_icon = {
                'success': '✅',
                'pending': '⏳',
                'error': '❌',
                'info': 'ℹ️'
            }.get(activity['status'], 'ℹ️')
            
            st.markdown(
                f"{status_icon} **{activity['action']}** - {activity['file']} - *{activity['time']}*"
            )
        
        if st.button("查看更多活动", key="more_activity"):
            st.info("完整活动日志功能待实现")
            
    except Exception as e:
        st.error(f"加载活动日志失败: {str(e)}")
