"""系統管理頁（Admin 專用）：使用者管理、系統日誌、資料庫監控、即時資料歷史。"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta

import pandas as pd
import streamlit as st

from utils.api_client import APIError
from utils.state import get_client, guard, show_error

guard(require_admin=True)
st.title("系統管理")

client = get_client()

tab_overview, tab_users, tab_logs, tab_db, tab_metrics = st.tabs(
    ["系統概覽", "使用者管理", "系統日誌", "資料庫狀態", "即時資料歷史"]
)

# ------------------------------------------------------------------ 概覽
with tab_overview:
    try:
        overview = client.get("/admin/overview")
    except APIError as exc:
        show_error(exc)
        st.stop()

    cols = st.columns(5)
    cols[0].metric("使用者", f"{overview['users']['total']}", f"啟用 {overview['users']['active']}")
    cols[1].metric("資料筆數", f"{overview['records']:,}")
    cols[2].metric("即時資料", f"{overview['metrics']['total']:,}")
    cols[3].metric("告警筆數", f"{overview['metrics']['alerts']:,}")
    cols[4].metric("WS 連線", overview["realtime"]["websocket_connections"])

    st.caption(
        f"環境：{overview['environment']} ・ 版本：{overview['version']} ・ "
        f"產生器：{'運作中' if overview['realtime']['generator_running'] else '停止'} ・ "
        f"緩衝區：{overview['realtime']['buffered']} 筆"
    )

    if st.button("立即批次寫入緩衝資料"):
        try:
            result = client.post("/realtime/flush")
            st.success(result["message"])
        except APIError as exc:
            show_error(exc)

# ------------------------------------------------------------------ 使用者
with tab_users:
    filter_cols = st.columns(4)
    keyword = filter_cols[0].text_input("關鍵字（帳號 / Email）")
    role_filter = filter_cols[1].selectbox("角色", ["全部", "admin", "user", "viewer"])
    active_filter = filter_cols[2].selectbox("狀態", ["全部", "啟用", "停用"])
    page = filter_cols[3].number_input("頁碼", min_value=1, value=1, step=1)

    params: dict = {"page": int(page), "size": 20}
    if keyword:
        params["keyword"] = keyword
    if role_filter != "全部":
        params["role"] = role_filter
    if active_filter != "全部":
        params["is_active"] = active_filter == "啟用"

    try:
        result = client.get("/users", params)
    except APIError as exc:
        show_error(exc)
        st.stop()

    st.caption(f"共 {result['meta']['total']} 位使用者")
    if result["items"]:
        st.dataframe(
            pd.DataFrame(result["items"])[
                ["id", "username", "email", "full_name", "role", "is_active", "created_at"]
            ].rename(
                columns={
                    "id": "ID",
                    "username": "帳號",
                    "email": "Email",
                    "full_name": "名稱",
                    "role": "角色",
                    "is_active": "啟用",
                    "created_at": "建立時間",
                }
            ),
            use_container_width=True,
            hide_index=True,
        )

    st.divider()
    manage_left, manage_right = st.columns(2)

    with manage_left:
        st.subheader("調整權限")
        with st.form("role_form"):
            target_id = st.number_input("使用者 ID", min_value=1, step=1)
            new_role = st.selectbox("新角色", ["admin", "user", "viewer"])
            new_active = st.selectbox("帳號狀態", ["不變更", "啟用", "停用"])
            role_submitted = st.form_submit_button("更新權限", type="primary")

        if role_submitted:
            payload: dict = {"role": new_role}
            if new_active != "不變更":
                payload["is_active"] = new_active == "啟用"
            try:
                client.patch(f"/users/{int(target_id)}/role", payload)
                st.success("權限已更新")
                st.rerun()
            except APIError as exc:
                show_error(exc)

    with manage_right:
        st.subheader("建立帳號")
        with st.form("create_user_form"):
            username = st.text_input("帳號")
            email = st.text_input("Email")
            full_name = st.text_input("名稱")
            password = st.text_input("密碼", type="password")
            role = st.selectbox("角色", ["user", "viewer", "admin"])
            create_submitted = st.form_submit_button("建立")

        if create_submitted:
            try:
                client.post(
                    "/users",
                    {
                        "username": username,
                        "email": email,
                        "full_name": full_name or None,
                        "password": password,
                        "role": role,
                    },
                )
                st.success("帳號建立成功")
                st.rerun()
            except APIError as exc:
                show_error(exc)

        st.markdown("---")
        delete_id = st.number_input("刪除使用者 ID", min_value=1, step=1, key="del_user")
        if st.button("刪除使用者"):
            try:
                client.delete(f"/users/{int(delete_id)}")
                st.success("使用者已刪除")
                st.rerun()
            except APIError as exc:
                show_error(exc)

# ------------------------------------------------------------------ 日誌
with tab_logs:
    log_cols = st.columns(4)
    level = log_cols[0].selectbox("等級", ["全部", "INFO", "WARNING", "ERROR", "CRITICAL"])
    log_keyword = log_cols[1].text_input("關鍵字（動作 / 路徑）")
    log_page = log_cols[2].number_input("頁碼", min_value=1, value=1, step=1, key="log_page")
    log_size = log_cols[3].number_input("每頁筆數", min_value=10, max_value=200, value=50, step=10)

    log_params: dict = {"page": int(log_page), "size": int(log_size)}
    if level != "全部":
        log_params["level"] = level
    if log_keyword:
        log_params["keyword"] = log_keyword

    try:
        logs = client.get("/admin/logs", log_params)
        st.caption(f"共 {logs['meta']['total']:,} 筆日誌")
        if logs["items"]:
            st.dataframe(
                pd.DataFrame(logs["items"])[
                    ["created_at", "level", "action", "message", "method", "path",
                     "status_code", "duration_ms", "client_ip", "user_id"]
                ],
                use_container_width=True,
                hide_index=True,
            )
        else:
            st.info("查無日誌")
    except APIError as exc:
        show_error(exc)

# ------------------------------------------------------------------ 資料庫
with tab_db:
    try:
        db_status = client.get("/admin/database")
    except APIError as exc:
        show_error(exc)
        st.stop()

    status_cols = st.columns(3)
    status_cols[0].metric("連線狀態", "正常" if db_status["connected"] else "異常")
    status_cols[1].metric("資料庫方言", db_status["dialect"])
    status_cols[2].metric("伺服器時間", str(db_status["server_time"] or "-"))

    st.subheader("連接池狀態")
    st.json(db_status["pool"])

    st.subheader("資料表統計")
    st.dataframe(
        pd.DataFrame(db_status["tables"]).rename(columns={"table": "資料表", "rows": "筆數"}),
        use_container_width=True,
        hide_index=True,
    )

# ------------------------------------------------------------------ 即時資料歷史
with tab_metrics:
    metric_cols = st.columns(4)
    start_date = metric_cols[0].date_input(
        "起始日期", value=date.today() - timedelta(days=1), key="m_start"
    )
    end_date = metric_cols[1].date_input("結束日期", value=date.today(), key="m_end")
    sensor_id = metric_cols[2].text_input("感測器編號", placeholder="SENSOR-01")
    only_alert = metric_cols[3].checkbox("僅告警資料")

    metric_params: dict = {
        "start_time": datetime.combine(start_date, time.min).isoformat(),
        "end_time": datetime.combine(end_date, time.max).isoformat(),
        "size": 500,
        "only_alert": only_alert,
    }
    if sensor_id:
        metric_params["sensor_id"] = sensor_id

    try:
        metrics = client.get("/realtime/metrics", metric_params)
        summary_rows = client.get(
            "/realtime/metrics/summary",
            {"start_time": metric_params["start_time"], "end_time": metric_params["end_time"]},
        )
    except APIError as exc:
        show_error(exc)
        st.stop()

    if summary_rows:
        st.subheader("感測器統計")
        st.dataframe(pd.DataFrame(summary_rows), use_container_width=True, hide_index=True)

    st.subheader("歷史資料明細")
    if metrics["items"]:
        metrics_df = pd.DataFrame(metrics["items"])
        st.caption(f"共 {metrics['meta']['total']:,} 筆，顯示 {len(metrics_df)} 筆")
        st.dataframe(metrics_df, use_container_width=True, hide_index=True)
        st.download_button(
            "下載 CSV",
            data=metrics_df.to_csv(index=False).encode("utf-8-sig"),
            file_name="metric_history.csv",
            mime="text/csv",
        )
    else:
        st.info("查無即時資料")
