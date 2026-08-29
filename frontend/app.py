"""Streamlit 前端入口（多頁面應用）。"""

from __future__ import annotations

import streamlit as st

from utils.state import init_state, is_admin, is_authenticated, render_sidebar_user

st.set_page_config(
    page_title="即時資料分析與監控系統",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

init_state()

login_page = st.Page("views/login.py", title="登入 / 註冊", icon="🔐", default=True)
application_pages = [
    st.Page("views/dashboard.py", title="總覽儀表板", icon="📊"),
    st.Page("views/realtime.py", title="即時監控", icon="📡"),
    st.Page("views/records.py", title="資料管理", icon="🗂️"),
    st.Page("views/analytics.py", title="資料分析", icon="📈"),
    st.Page("views/profile.py", title="個人設定", icon="⚙️"),
    st.Page("views/admin.py", title="系統管理", icon="🛡️"),
]

if is_authenticated():
    render_sidebar_user()
    pages = application_pages if is_admin() else application_pages[:-1]
    st.navigation(pages).run()
else:
    st.navigation([login_page, *application_pages], position="hidden").run()
