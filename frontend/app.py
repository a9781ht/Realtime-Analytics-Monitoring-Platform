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

if not is_authenticated():
    pages = [st.Page("views/login.py", title="登入 / 註冊", default=True)]
else:
    render_sidebar_user()
    pages = [
        st.Page("views/dashboard.py", title="總覽儀表板", default=True),
        st.Page("views/realtime.py", title="即時監控"),
        st.Page("views/records.py", title="資料管理"),
        st.Page("views/analytics.py", title="資料分析"),
        st.Page("views/profile.py", title="個人設定"),
    ]
    if is_admin():
        pages.append(st.Page("views/admin.py", title="系統管理"))

st.navigation(pages).run()
