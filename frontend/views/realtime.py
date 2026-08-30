"""即時監控頁：WebSocket 即時推送 + 動態圖表 + 異常告警。"""

from __future__ import annotations

import pandas as pd
import plotly.express as px
import streamlit as st

from utils.api_client import APIError
from utils.state import get_client, guard, is_admin, show_error
from utils.stream import MetricStream

guard()
st.title("即時監控")

client = get_client()

# ---- 建立 / 取得 WebSocket 串流 ----
if st.session_state.get("stream") is None:
    st.session_state["stream"] = MetricStream(client.websocket_url())
stream: MetricStream = st.session_state["stream"]
# Token 可能已換發，重連時需帶上最新的 access token
stream.url = client.websocket_url()

control_cols = st.columns([1, 1, 1, 3])
if control_cols[0].button("連線", use_container_width=True):
    stream.start()
    st.rerun()
if control_cols[1].button("中斷", use_container_width=True):
    stream.stop()
    st.rerun()
if control_cols[2].button("清除", use_container_width=True):
    stream.points.clear()
    stream.alerts.clear()
    st.rerun()

if not stream.running:
    stream.start()

try:
    status = client.get("/realtime/status")
except APIError as exc:
    show_error(exc)
    st.stop()

threshold_high = status["threshold_high"]
threshold_low = status["threshold_low"]

st.caption(
    f"推送頻率：每 {status['interval_seconds']} 秒 ・ 批次寫入間隔：資料庫已寫入 "
    f"{status['total_persisted']:,} 筆 ・ 告警閾值：>= {threshold_high} 或 <= {threshold_low}"
)


@st.fragment(run_every="1s")
def render_realtime() -> None:
    points = stream.snapshot()

    state_cols = st.columns(4)
    state_cols[0].metric("連線狀態", "已連線" if stream.connected else "未連線")
    state_cols[1].metric("已接收筆數", f"{stream.received:,}")
    state_cols[2].metric("告警次數", len(stream.alert_list()))
    state_cols[3].metric("視窗資料點", len(points))

    if stream.error and not stream.connected:
        st.warning(f"WebSocket 連線異常，自動重試中：{stream.error}")

    if not points:
        st.info("等待即時資料中…（若長時間無資料，請確認後端產生器是否啟用）")
        return

    df = pd.DataFrame(points)
    df["generated_at"] = pd.to_datetime(df["generated_at"])
    recent = df.tail(300)

    line_fig = px.line(
        recent,
        x="generated_at",
        y="value",
        color="sensor_id",
        markers=False,
        labels={"generated_at": "時間", "value": "數值", "sensor_id": "感測器"},
        title="即時數值折線圖",
    )
    line_fig.add_hline(y=threshold_high, line_dash="dash", line_color="red", annotation_text="上限")
    line_fig.add_hline(y=threshold_low, line_dash="dash", line_color="orange", annotation_text="下限")
    line_fig.update_layout(height=380, margin=dict(t=50, b=20))
    st.plotly_chart(line_fig, use_container_width=True)

    chart_left, chart_right = st.columns(2)

    latest = df.sort_values("generated_at").groupby("sensor_id").tail(1)
    bar_fig = px.bar(
        latest,
        x="sensor_id",
        y="value",
        color="alert_level",
        text="value",
        labels={"sensor_id": "感測器", "value": "最新數值", "alert_level": "告警等級"},
        color_discrete_map={"normal": "#2E86DE", "warning": "#F39C12", "critical": "#E74C3C"},
        title="各感測器最新數值",
    )
    bar_fig.update_layout(height=340, margin=dict(t=50, b=20))
    chart_left.plotly_chart(bar_fig, use_container_width=True)

    alert_counts = df.groupby("alert_level").size().reset_index(name="count")
    pie_fig = px.pie(
        alert_counts, names="alert_level", values="count", hole=0.5, title="告警等級分佈",
        color="alert_level",
        color_discrete_map={"normal": "#2ECC71", "warning": "#F39C12", "critical": "#E74C3C"},
    )
    pie_fig.update_layout(height=340, margin=dict(t=50, b=20))
    chart_right.plotly_chart(pie_fig, use_container_width=True)

    st.subheader("異常告警清單")
    alerts = stream.alert_list()
    if alerts:
        alert_df = pd.DataFrame(alerts)[
            ["generated_at", "sensor_id", "metric_name", "value", "unit", "alert_level"]
        ].rename(
            columns={
                "generated_at": "時間",
                "sensor_id": "感測器",
                "metric_name": "指標",
                "value": "數值",
                "unit": "單位",
                "alert_level": "等級",
            }
        )
        st.dataframe(alert_df.head(20), use_container_width=True, hide_index=True)
    else:
        st.success("目前無異常資料")


render_realtime()

if is_admin():
    st.divider()
    st.subheader("即時資料歷史查詢")

    hist_cols = st.columns([1, 1, 1, 1])
    sensor_id = hist_cols[0].text_input("感測器編號", placeholder="SENSOR-01")
    only_alert = hist_cols[1].checkbox("僅顯示告警", value=False)
    size = hist_cols[2].number_input("查詢筆數", min_value=10, max_value=500, value=100, step=10)
    query = hist_cols[3].button("查詢", use_container_width=True)

    if query:
        try:
            params = {"size": int(size), "only_alert": only_alert}
            if sensor_id:
                params["sensor_id"] = sensor_id
            result = client.get("/realtime/metrics", params)
            if result["items"]:
                hist_df = pd.DataFrame(result["items"])
                st.caption(f"共 {result['meta']['total']:,} 筆，顯示最新 {len(hist_df)} 筆")
                st.dataframe(hist_df, use_container_width=True, hide_index=True)
            else:
                st.info("查無資料")
        except APIError as exc:
            show_error(exc)
