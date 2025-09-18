import streamlit as st
import pandas as pd
import requests
import json
from datetime import datetime

def show_approval():
    """显示人工审核页面"""
    st.title("👥 人工审核")
    st.markdown("审核AI分析存疑的文档，决定是否加入知识库")
    
    # 刷新按钮
    col1, col2 = st.columns([1, 3])
    with col1:
        if st.button("🔄 刷新列表", key="refresh_approval"):
            st.rerun()
    
    # 获取待审核文档列表
    try:
        pending_files = get_pending_approval_files()
        
        if not pending_files:
            st.success("🎉 太好了！当前没有需要人工审核的文档")
            st.info("💡 系统会自动处理高置信度的文档，只有存疑的文档才需要人工审核")
            return
        
        st.info(f"📋 当前有 {len(pending_files)} 个文档等待审核")
        
        # 审核统计
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("待审核", len(pending_files))
        with col2:
            avg_confidence = sum(f.get('ai_confidence_score', 0) for f in pending_files) / len(pending_files)
            st.metric("平均置信度", f"{avg_confidence:.1f}%")
        with col3:
            high_priority = sum(1 for f in pending_files if f.get('ai_confidence_score', 0) > 70)
            st.metric("高优先级", high_priority)
        
        st.markdown("---")
        
        # 显示待审核文档列表
        for idx, file_info in enumerate(pending_files):
            show_approval_card(file_info, idx)
            st.markdown("---")
            
    except Exception as e:
        st.error(f"获取待审核文档失败: {str(e)}")
        st.info("请检查后端服务是否正常运行")

def show_approval_card(file_info, idx):
    """显示单个文档的审核卡片"""
    file_id = file_info.get('imagefileid', '')
    filename = file_info.get('filename', '未知文件')
    confidence = file_info.get('ai_confidence_score', 0)
    ai_analysis = file_info.get('ai_analysis', {})
    
    # 卡片标题
    col1, col2, col3 = st.columns([2, 1, 1])
    with col1:
        st.subheader(f"📄 {filename}")
        st.caption(f"文件ID: {file_id}")
    
    with col2:
        confidence_color = "green" if confidence > 70 else "orange" if confidence > 50 else "red"
        st.markdown(f"**置信度:** :{confidence_color}[{confidence}%]")
    
    with col3:
        category = file_info.get('business_category', '未知')
        st.markdown(f"**分类:** {category}")
    
    # 展开详细信息
    with st.expander(f"📋 查看详细分析 - {filename}", expanded=False):
        col1, col2 = st.columns(2)
        
        with col1:
            st.markdown("**文件信息:**")
            st.write(f"• 文件类型: {file_info.get('file_type', '未知')}")
            st.write(f"• 文件大小: {format_file_size(file_info.get('filesize', 0))}")
            st.write(f"• 业务分类: {file_info.get('business_category', '未知')}")
            
            if ai_analysis:
                st.markdown("**AI分析结果:**")
                st.write(f"• 内容分类: {ai_analysis.get('category', '未知')}")
                st.write(f"• 质量评分: {ai_analysis.get('quality_score', 0)}分")
                st.write(f"• 完整性: {ai_analysis.get('completeness', '未知')}")
        
        with col2:
            if ai_analysis.get('summary'):
                st.markdown("**内容摘要:**")
                st.write(ai_analysis['summary'])
            
            if ai_analysis.get('key_topics'):
                st.markdown("**关键主题:**")
                topics = ai_analysis['key_topics'][:5]  # 最多显示5个
                st.write("• " + " • ".join(topics))
            
            if ai_analysis.get('reasons'):
                st.markdown("**分析理由:**")
                for reason in ai_analysis['reasons'][:3]:  # 最多显示3个理由
                    st.write(f"• {reason}")
    
    # 审核操作
    col1, col2, col3, col4 = st.columns([2, 1, 1, 2])
    
    with col1:
        comment = st.text_input(
            "审核意见", 
            key=f"comment_{idx}_{file_id}",
            placeholder="请输入审核意见（可选）"
        )
    
    with col2:
        if st.button(
            "✅ 通过", 
            key=f"approve_{idx}_{file_id}",
            type="primary",
            help="通过审核，文档将加入知识库"
        ):
            handle_approval(file_id, True, comment, filename)
    
    with col3:
        if st.button(
            "❌ 拒绝", 
            key=f"reject_{idx}_{file_id}",
            help="拒绝文档，不加入知识库"
        ):
            handle_approval(file_id, False, comment, filename)
    
    with col4:
        if st.button(
            "📄 查看详情", 
            key=f"detail_{idx}_{file_id}",
            help="查看完整文档信息和处理日志"
        ):
            show_file_detail(file_id, filename)

def handle_approval(file_id, approved, comment, filename):
    """处理审核操作"""
    try:
        # 调用审核API
        result = submit_approval(file_id, approved, comment)
        
        if result.get('success'):
            action = "通过" if approved else "拒绝"
            st.success(f"✅ 文档 {filename} 已{action}审核")
            
            # 显示审核结果
            if approved:
                st.info("📤 文档正在加入知识库，请稍后刷新页面查看结果")
            else:
                st.info("📝 文档已标记为跳过，不会加入知识库")
            
            # 延迟刷新
            import time
            time.sleep(2)
            st.rerun()
            
        else:
            st.error(f"❌ 审核操作失败: {result.get('error', '未知错误')}")
            
    except Exception as e:
        st.error(f"❌ 提交审核失败: {str(e)}")

def show_file_detail(file_id, filename):
    """显示文件详细信息"""
    try:
        detail = get_file_detail(file_id)
        
        # 在新的容器中显示详细信息
        with st.container():
            st.markdown(f"### 📄 文档详情: {filename}")
            
            # 基本信息
            col1, col2 = st.columns(2)
            with col1:
                st.markdown("**基本信息:**")
                st.write(f"• 文件ID: {detail.get('imagefileid', '未知')}")
                st.write(f"• 文件名: {detail.get('filename', '未知')}")
                st.write(f"• 文件类型: {detail.get('file_type', '未知')}")
                st.write(f"• 文件大小: {format_file_size(detail.get('filesize', 0))}")
                st.write(f"• 业务分类: {detail.get('business_category', '未知')}")
                
            with col2:
                st.markdown("**处理信息:**")
                st.write(f"• 当前状态: {detail.get('processing_status', '未知')}")
                st.write(f"• 处理消息: {detail.get('processing_message', '无')}")
                st.write(f"• 错误次数: {detail.get('error_count', 0)}")
                
                if detail.get('processing_started_at'):
                    st.write(f"• 开始时间: {detail['processing_started_at']}")
            
            # AI分析结果
            if detail.get('ai_analysis'):
                ai_analysis = detail['ai_analysis']
                st.markdown("**AI分析结果:**")
                st.json(ai_analysis)
            
            # 处理日志
            if detail.get('processing_logs'):
                st.markdown("**处理日志:**")
                logs_df = pd.DataFrame(detail['processing_logs'])
                st.dataframe(logs_df, use_container_width=True)
            
    except Exception as e:
        st.error(f"获取文档详情失败: {str(e)}")

def get_pending_approval_files():
    """获取待审核文档列表"""
    try:
        response = requests.get(
            "http://localhost:18000/api/v1/files/?status=awaiting_approval&is_zw=true",
            timeout=10
        )
        response.raise_for_status()
        data = response.json()
        return data.get('items', [])
    except requests.exceptions.RequestException as e:
        st.error(f"获取待审核文档失败: {str(e)}")
        st.info("请检查后端服务是否正常运行")
        return []
    except Exception as e:
        st.error(f"处理待审核文档数据失败: {str(e)}")
        return []

def submit_approval(file_id, approved, comment):
    """提交审核结果"""
    try:
        data = {
            'approved': approved,
            'comment': comment
        }
        response = requests.post(
            f"http://localhost:18000/api/v1/files/{file_id}/approve",
            json=data,
            timeout=10
        )
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        return {'success': False, 'error': f'API调用失败: {str(e)}'}
    except Exception as e:
        return {'success': False, 'error': str(e)}

def get_file_detail(file_id):
    """获取文件详情"""
    try:
        response = requests.get(
            f"http://localhost:18000/api/v1/files/{file_id}",
            timeout=10
        )
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        st.error(f"获取文件详情失败: {str(e)}")
        st.info("请检查后端服务是否正常运行")
        return {}
    except Exception as e:
        st.error(f"处理文件详情数据失败: {str(e)}")
        return {}

def format_file_size(size_bytes):
    """格式化文件大小"""
    if size_bytes == 0:
        return "0 B"
    
    size_names = ["B", "KB", "MB", "GB"]
    import math
    i = int(math.floor(math.log(size_bytes, 1024)))
    p = math.pow(1024, i)
    s = round(size_bytes / p, 2)
    return f"{s} {size_names[i]}"
