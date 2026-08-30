"""資料管理頁：查詢、建立、更新、刪除、批量匯入。"""

from __future__ import annotations

from datetime import date, datetime, time

import pandas as pd
import streamlit as st

from utils.api_client import APIError
from utils.state import can_edit, get_client, guard, show_error

guard()
st.title("資料管理")

client = get_client()
user = st.session_state["user"]

if not can_edit():
    st.info("目前身分為唯讀使用者（viewer），僅可瀏覽資料。")

tab_list, tab_create, tab_import = st.tabs(["資料查詢", "新增資料", "批量匯入"])

# ------------------------------------------------------------------ 查詢
with tab_list:
    try:
        categories = client.get("/records/categories")
    except APIError as exc:
        show_error(exc)
        categories = []

    with st.form("filter_form"):
        row1 = st.columns(4)
        keyword = row1[0].text_input("標題關鍵字")
        category = row1[1].selectbox("分類", ["全部", *categories])
        sort_by = row1[2].selectbox(
            "排序欄位", ["recorded_at", "value", "title", "category", "id"]
        )
        order = row1[3].selectbox("排序方式", ["desc", "asc"])

        row2 = st.columns(4)
        start_date = row2[0].date_input("起始日期", value=None)
        end_date = row2[1].date_input("結束日期", value=None)
        min_value = row2[2].number_input("最小值", value=None, help="留空表示不限")
        max_value = row2[3].number_input("最大值", value=None, help="留空表示不限")

        row3 = st.columns([1, 1, 4])
        page = row3[0].number_input("頁碼", min_value=1, value=1, step=1)
        size = row3[1].number_input("每頁筆數", min_value=5, max_value=200, value=20, step=5)
        submitted = st.form_submit_button("查詢", type="primary")

    params: dict = {"page": int(page), "size": int(size), "sort_by": sort_by, "order": order}
    if keyword:
        params["keyword"] = keyword
    if category and category != "全部":
        params["category"] = category
    if start_date:
        params["start_time"] = datetime.combine(start_date, time.min).isoformat()
    if end_date:
        params["end_time"] = datetime.combine(end_date, time.max).isoformat()
    if min_value is not None:
        params["min_value"] = min_value
    if max_value is not None:
        params["max_value"] = max_value

    try:
        result = client.get("/records", params)
    except APIError as exc:
        show_error(exc)
        st.stop()

    meta = result["meta"]
    st.caption(f"共 {meta['total']:,} 筆，第 {meta['page']} / {max(meta['pages'], 1)} 頁")

    if result["items"]:
        df = pd.DataFrame(result["items"])[
            ["id", "title", "value", "category", "recorded_at", "owner_username", "description"]
        ].rename(
            columns={
                "id": "ID",
                "title": "標題",
                "value": "數值",
                "category": "分類",
                "recorded_at": "資料時間",
                "owner_username": "建立者",
                "description": "說明",
            }
        )
        st.dataframe(df, use_container_width=True, hide_index=True)

        st.download_button(
            "下載本頁 CSV",
            data=df.to_csv(index=False).encode("utf-8-sig"),
            file_name="records.csv",
            mime="text/csv",
        )

        if can_edit():
            st.divider()
            st.subheader("編輯 / 刪除")
            edit_cols = st.columns([1, 3])
            record_id = edit_cols[0].number_input("資料 ID", min_value=1, step=1)

            with st.expander("修改內容"):
                with st.form("edit_form"):
                    new_title = st.text_input("標題（留空不改）")
                    new_value = st.number_input("數值", value=None, help="留空表示不修改")
                    new_category = st.text_input("分類（留空不改）")
                    new_desc = st.text_area("說明（留空不改）")
                    update_submitted = st.form_submit_button("更新")

                if update_submitted:
                    payload = {}
                    if new_title:
                        payload["title"] = new_title
                    if new_value is not None:
                        payload["value"] = new_value
                    if new_category:
                        payload["category"] = new_category
                    if new_desc:
                        payload["description"] = new_desc
                    if not payload:
                        st.warning("未填寫任何要更新的欄位")
                    else:
                        try:
                            client.patch(f"/records/{int(record_id)}", payload)
                            st.success("更新成功")
                            st.rerun()
                        except APIError as exc:
                            show_error(exc)

            if st.button("刪除此筆資料", type="secondary"):
                try:
                    client.delete(f"/records/{int(record_id)}")
                    st.success("刪除成功")
                    st.rerun()
                except APIError as exc:
                    show_error(exc)
    else:
        st.info("查無資料")

# ------------------------------------------------------------------ 新增
with tab_create:
    if not can_edit():
        st.warning("唯讀使用者無法新增資料")
    else:
        with st.form("create_form"):
            title = st.text_input("標題 *")
            value = st.number_input("數值 *", value=0.0, step=0.1, format="%.2f")
            category_input = st.text_input("分類 *", value="temperature")
            description = st.text_area("說明")
            recorded_date = st.date_input("資料日期", value=date.today())
            recorded_time = st.time_input("資料時間", value=datetime.now().time())
            create_submitted = st.form_submit_button("建立資料", type="primary")

        if create_submitted:
            if not title or not category_input:
                st.warning("標題與分類為必填欄位")
            else:
                try:
                    client.post(
                        "/records",
                        {
                            "title": title,
                            "value": value,
                            "category": category_input,
                            "description": description or None,
                            "recorded_at": datetime.combine(
                                recorded_date, recorded_time
                            ).isoformat(),
                        },
                    )
                    st.success("資料建立成功")
                except APIError as exc:
                    show_error(exc)

# ------------------------------------------------------------------ 匯入
with tab_import:
    if not can_edit():
        st.warning("唯讀使用者無法匯入資料")
    else:
        st.markdown(
            """
            上傳 **CSV** 或 **JSON** 檔案批量匯入資料。

            必要欄位：`title`, `value`, `category`；選填欄位：`description`, `recorded_at`
            （格式：`YYYY-MM-DD HH:MM:SS`）。範例檔請見專案內 `samples/sample_records.csv`。
            """
        )
        uploaded = st.file_uploader("選擇檔案", type=["csv", "json"])
        if uploaded is not None:
            preview_placeholder = st.empty()
            if uploaded.name.lower().endswith(".csv"):
                try:
                    preview_placeholder.dataframe(
                        pd.read_csv(uploaded).head(10), use_container_width=True
                    )
                    uploaded.seek(0)
                except Exception as exc:  # noqa: BLE001
                    st.warning(f"預覽失敗：{exc}")

            if st.button("開始匯入", type="primary"):
                try:
                    files = {"file": (uploaded.name, uploaded.getvalue(), uploaded.type)}
                    result = client.post("/records/import", files=files)
                    st.success(f"匯入完成：成功 {result['inserted']} 筆，失敗 {result['failed']} 筆")
                    if result["errors"]:
                        st.warning("\n".join(result["errors"][:10]))
                except APIError as exc:
                    show_error(exc)
