"""資料分析頁：統計、時間範圍查詢、分類聚合、趨勢圖與 Excel 下載。"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta

import pandas as pd
import plotly.express as px
import streamlit as st

from utils.api_client import APIError
from utils.state import get_client, guard, show_error

guard()
st.title("資料分析")

client = get_client()

try:
    categories = client.get("/records/categories")
except APIError as exc:
    show_error(exc)
    categories = []

with st.container(border=True):
    cols = st.columns(4)
    start_date = cols[0].date_input("起始日期", value=date.today() - timedelta(days=30))
    end_date = cols[1].date_input("結束日期", value=date.today())
    category = cols[2].selectbox("分類", ["全部", *categories])
    granularity = cols[3].selectbox("時間粒度", ["day", "hour", "month"], index=0)

params: dict = {
    "start_time": datetime.combine(start_date, time.min).isoformat(),
    "end_time": datetime.combine(end_date, time.max).isoformat(),
}
if category != "全部":
    params["category"] = category

try:
    summary = client.get("/analytics/summary", params)
    aggregates = client.get(
        "/analytics/categories",
        {k: v for k, v in params.items() if k != "category"},
    )
    trend = client.get("/analytics/trend", {**params, "granularity": granularity})
except APIError as exc:
    show_error(exc)
    st.stop()

st.subheader("統計摘要")
metric_cols = st.columns(5)
metric_cols[0].metric("筆數", f"{summary['count']:,}")
metric_cols[1].metric("總計", f"{summary['total'] or 0:,.2f}")
metric_cols[2].metric("平均", f"{summary['average'] or 0:,.2f}")
metric_cols[3].metric("最大值", f"{summary['maximum'] or 0:,.2f}")
metric_cols[4].metric("最小值", f"{summary['minimum'] or 0:,.2f}")

st.divider()

chart_left, chart_right = st.columns(2)

with chart_left:
    st.subheader("趨勢分析")
    if trend:
        trend_df = pd.DataFrame(trend)
        fig = px.line(
            trend_df, x="bucket", y=["average", "total"], markers=True,
            labels={"bucket": "時間", "value": "數值", "variable": "指標"},
        )
        fig.update_layout(height=380, margin=dict(t=20, b=10))
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("此區間無資料")

with chart_right:
    st.subheader("分類聚合")
    if aggregates:
        agg_df = pd.DataFrame(aggregates)
        fig = px.bar(
            agg_df, x="category", y="total", color="category", text="count",
            labels={"category": "分類", "total": "總計", "count": "筆數"},
        )
        fig.update_layout(height=380, margin=dict(t=20, b=10), showlegend=False)
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("此區間無資料")

st.divider()
st.subheader("分類統計表")
if aggregates:
    st.dataframe(
        pd.DataFrame(aggregates).rename(
            columns={
                "category": "分類",
                "count": "筆數",
                "total": "總計",
                "average": "平均",
                "minimum": "最小值",
                "maximum": "最大值",
            }
        ),
        use_container_width=True,
        hide_index=True,
    )

st.divider()
st.subheader("下載分析報表")
st.caption("報表包含四個工作表：資料明細、統計摘要、分類聚合、趨勢分析。")

if st.button("產生 Excel 報表", type="primary"):
    try:
        content = client.download("/analytics/export", {**params, "granularity": granularity})
        st.download_button(
            "點此下載 Excel",
            data=content,
            file_name=f"analytics_report_{datetime.now():%Y%m%d_%H%M%S}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            type="primary",
        )
        st.success("報表已產生")
    except APIError as exc:
        show_error(exc)
