import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
from templates.dashboard import show_dashboard
from templates.approval import show_approval
from templates.settings import show_settings
from templates.maintenance import show_maintenance

# 页面配置
st.set_page_config(
    page_title="OA文档处理系统",
    page_icon="📄",
    layout="wide",
    initial_sidebar_state="expanded"
)

# 侧边栏导航
st.sidebar.title("📄 OA文档处理系统")
st.sidebar.markdown("---")

page = st.sidebar.selectbox(
    "选择页面",
    ["📊 仪表板", "👥 人工审核", "🛠️ 系统维护", "⚙️ 系统设置"],
    key="page_selector"
)

# 显示对应页面
if page == "📊 仪表板":
    show_dashboard()
elif page == "👥 人工审核":
    show_approval()
elif page == "🛠️ 系统维护":
    show_maintenance()
elif page == "⚙️ 系统设置":
    show_settings()

# 底部信息
st.sidebar.markdown("---")
st.sidebar.markdown("**系统状态**")
st.sidebar.success("✅ 运行正常")
st.sidebar.info(f"最后更新: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
