"""Session 狀態管理與共用 UI 元件。"""

from __future__ import annotations

from typing import Any

import streamlit as st

from utils.api_client import APIClient, APIError

ROLE_LABELS = {"admin": "系統管理員", "user": "一般使用者", "viewer": "唯讀使用者"}


def init_state() -> None:
    defaults: dict[str, Any] = {
        "access_token": None,
        "refresh_token": None,
        "user": None,
        "stream": None,
    }
    for key, value in defaults.items():
        st.session_state.setdefault(key, value)


def is_authenticated() -> bool:
    return bool(st.session_state.get("access_token") and st.session_state.get("user"))


def _store_tokens(tokens: dict) -> None:
    st.session_state["access_token"] = tokens.get("access_token")
    st.session_state["refresh_token"] = tokens.get("refresh_token")


def get_client() -> APIClient:
    """建立 API 用戶端；access token 過期時會自動以 refresh token 換發。"""
    return APIClient(
        token=st.session_state.get("access_token"),
        refresh_token=st.session_state.get("refresh_token"),
        on_token_refresh=_store_tokens,
    )


def current_role() -> str:
    user = st.session_state.get("user") or {}
    return user.get("role", "viewer")


def is_admin() -> bool:
    return current_role() == "admin"


def can_edit() -> bool:
    return current_role() in ("admin", "user")


def do_login(username: str, password: str) -> None:
    tokens = APIClient().login(username, password)
    _store_tokens(tokens)
    st.session_state["user"] = APIClient(token=tokens["access_token"]).me()


def do_logout() -> None:
    stream = st.session_state.get("stream")
    if stream is not None:
        stream.stop()
    try:
        get_client().logout()
    except APIError:
        pass
    for key in ("access_token", "refresh_token", "user", "stream"):
        st.session_state[key] = None


def render_sidebar_user() -> None:
    user = st.session_state.get("user") or {}
    with st.sidebar:
        st.markdown("### 👤 使用者")
        st.write(f"**{user.get('username', '-')}**")
        st.caption(f"角色：{ROLE_LABELS.get(user.get('role', ''), user.get('role', '-'))}")
        st.caption(f"Email：{user.get('email', '-')}")
        if st.button("登出", use_container_width=True, type="secondary"):
            do_logout()
            st.rerun()
        st.divider()


def guard(require_admin: bool = False) -> None:
    """頁面守衛：未登入導回登入頁，權限不足則中止。"""
    if not is_authenticated():
        st.warning("請先登入系統")
        st.stop()
    if require_admin and not is_admin():
        st.error("權限不足：此頁面僅限系統管理員存取")
        st.stop()


def show_error(exc: APIError) -> None:
    st.error(f"操作失敗（{exc.status_code or 'ERR'}）：{exc.message}")
