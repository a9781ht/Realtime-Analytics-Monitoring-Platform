"""登入 / 註冊頁。"""

from __future__ import annotations

import streamlit as st

from utils.api_client import APIClient, APIError
from utils.state import do_login

st.title("即時資料分析與監控系統")
st.caption("FastAPI × Streamlit × MariaDB × Docker")

login_tab, register_tab = st.tabs(["登入", "註冊"])

with login_tab:
    with st.form("login_form"):
        username = st.text_input("使用者名稱", value="", placeholder="admin")
        password = st.text_input("密碼", type="password", placeholder="Admin@1234")
        submitted = st.form_submit_button("登入", use_container_width=True, type="primary")

    if submitted:
        if not username or not password:
            st.warning("請輸入使用者名稱與密碼")
        else:
            try:
                do_login(username, password)
                st.success("登入成功，正在載入系統…")
                st.rerun()
            except APIError as exc:
                st.error(f"登入失敗：{exc.message}")

    with st.expander("測試帳號"):
        st.markdown(
            """
            | 角色 | 帳號 | 密碼 | 權限 |
            | --- | --- | --- | --- |
            | Admin | `admin` | `Admin@1234` | 全部功能 + 系統管理 |
            | User | `user` | `User@1234` | 資料 CRUD（自己的資料） |
            | Viewer | `viewer` | `Viewer@1234` | 僅可瀏覽與分析 |
            """
        )

with register_tab:
    with st.form("register_form"):
        new_username = st.text_input("使用者名稱", key="reg_username")
        new_email = st.text_input("Email", key="reg_email")
        new_fullname = st.text_input("顯示名稱（選填）", key="reg_fullname")
        new_password = st.text_input("密碼（至少 8 碼，需含英文與數字）", type="password", key="reg_pw")
        confirm_password = st.text_input("確認密碼", type="password", key="reg_pw2")
        register_submitted = st.form_submit_button("建立帳號", use_container_width=True)

    if register_submitted:
        if new_password != confirm_password:
            st.error("兩次輸入的密碼不一致")
        else:
            try:
                APIClient().register(
                    {
                        "username": new_username,
                        "email": new_email,
                        "full_name": new_fullname or None,
                        "password": new_password,
                    }
                )
                st.success("註冊成功，請切換至登入頁登入")
            except APIError as exc:
                st.error(f"註冊失敗：{exc.message}")
