"""個人設定頁。"""

from __future__ import annotations

import streamlit as st

from utils.api_client import APIError
from utils.state import ROLE_LABELS, get_client, guard, show_error

guard()
st.title("個人設定")

client = get_client()
user = st.session_state["user"]

with st.container(border=True):
    cols = st.columns(4)
    cols[0].metric("帳號", user["username"])
    cols[1].metric("角色", ROLE_LABELS.get(user["role"], user["role"]))
    cols[2].metric("狀態", "啟用" if user["is_active"] else "停用")
    cols[3].metric("ID", user["id"])
    st.caption(f"建立時間：{user['created_at']}")

st.subheader("更新個人資料")
with st.form("profile_form"):
    email = st.text_input("Email", value=user.get("email", ""))
    full_name = st.text_input("顯示名稱", value=user.get("full_name") or "")
    st.markdown("---")
    password = st.text_input("新密碼（留空表示不修改）", type="password")
    confirm = st.text_input("確認新密碼", type="password")
    submitted = st.form_submit_button("儲存變更", type="primary")

if submitted:
    if password and password != confirm:
        st.error("兩次輸入的密碼不一致")
    else:
        payload: dict = {"email": email, "full_name": full_name or None}
        if password:
            payload["password"] = password
        try:
            st.session_state["user"] = client.patch("/users/me", payload)
            st.success("個人資料已更新")
        except APIError as exc:
            show_error(exc)
