"""總覽儀表板。"""

from __future__ import annotations

import pandas as pd
import plotly.express as px
import streamlit as st

from utils.api_client import APIError
from utils.state import get_client, guard, show_error

guard()
st.title("📊 總覽儀表板")

client = get_client()

try:
    summary = client.get("/analytics/summary")
    categories = client.get("/analytics/categories")
    trend = client.get("/analytics/trend", {"granularity": "day"})
    realtime_status = client.get("/realtime/status")
except APIError as exc:
    show_error(exc)
    st.stop()

col1, col2, col3, col4 = st.columns(4)
col1.metric("資料總筆數", f"{summary['count']:,}")
col2.metric("數值總計", f"{summary['total'] or 0:,.2f}")
col3.metric("平均值", f"{summary['average'] or 0:,.2f}")
col4.metric("最大 / 最小", f"{summary['maximum'] or 0:,.1f} / {summary['minimum'] or 0:,.1f}")

st.divider()

left, right = st.columns([3, 2])

with left:
    st.subheader("📈 每日資料趨勢")
    if trend:
        trend_df = pd.DataFrame(trend)
        fig = px.line(
            trend_df, x="bucket", y="average", markers=True,
            labels={"bucket": "日期", "average": "平均值"},
        )
        fig.update_layout(height=360, margin=dict(t=20, b=10))
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("目前尚無資料")

with right:
    st.subheader("🗂️ 分類佔比")
    if categories:
        cat_df = pd.DataFrame(categories)
        fig = px.pie(cat_df, names="category", values="count", hole=0.45)
        fig.update_layout(height=360, margin=dict(t=20, b=10))
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("目前尚無資料")

st.divider()
st.subheader("📡 即時監控狀態")

status_cols = st.columns(4)
status_cols[0].metric("產生器", "運作中" if realtime_status["running"] else "停止")
status_cols[1].metric("WebSocket 連線數", realtime_status["active_connections"])
status_cols[2].metric("累積產生", f"{realtime_status['total_generated']:,}")
status_cols[3].metric("已寫入資料庫", f"{realtime_status['total_persisted']:,}")

st.caption(
    f"緩衝區暫存 {realtime_status['buffered']} 筆 ・ "
    f"告警閾值：>= {realtime_status['threshold_high']} 或 <= {realtime_status['threshold_low']}"
)

with st.expander("📋 分類統計明細"):
    if categories:
        st.dataframe(
            pd.DataFrame(categories).rename(
                columns={
                    "category": "分類",
                    "count": "筆數",
                    "total": "總計",
                    "average": "平均",
                    "minimum": "最小",
                    "maximum": "最大",
                }
            ),
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.write("無資料")
