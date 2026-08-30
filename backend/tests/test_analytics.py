"""資料分析模組測試：統計、分類聚合、趨勢、時間範圍、Excel 匯出。"""

from __future__ import annotations

import io
import zipfile

from httpx import AsyncClient

XLSX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


async def _seed(client: AsyncClient, headers: dict) -> None:
    rows = [
        {"title": "溫度 1", "value": 10.0, "category": "temperature",
         "recorded_at": "2026-01-01T08:00:00"},
        {"title": "溫度 2", "value": 30.0, "category": "temperature",
         "recorded_at": "2026-01-02T08:00:00"},
        {"title": "濕度 1", "value": 50.0, "category": "humidity",
         "recorded_at": "2026-03-01T08:00:00"},
    ]
    response = await client.post("/api/v1/records/bulk", headers=headers, json={"items": rows})
    assert response.status_code == 201, response.text


async def test_summary_statistics(client: AsyncClient, registered_user: dict) -> None:
    headers = registered_user["headers"]
    await _seed(client, headers)

    response = await client.get("/api/v1/analytics/summary", headers=headers)
    assert response.status_code == 200
    body = response.json()
    assert body["count"] == 3
    assert body["total"] == 90.0
    assert body["average"] == 30.0
    assert body["minimum"] == 10.0
    assert body["maximum"] == 50.0


async def test_summary_filtered_by_category(client: AsyncClient, registered_user: dict) -> None:
    headers = registered_user["headers"]
    await _seed(client, headers)

    response = await client.get(
        "/api/v1/analytics/summary", headers=headers, params={"category": "temperature"}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["count"] == 2
    assert body["total"] == 40.0
    assert body["maximum"] == 30.0


async def test_summary_time_range_query(client: AsyncClient, registered_user: dict) -> None:
    headers = registered_user["headers"]
    await _seed(client, headers)

    response = await client.get(
        "/api/v1/analytics/summary",
        headers=headers,
        params={"start_time": "2026-01-01T00:00:00", "end_time": "2026-01-31T23:59:59"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["count"] == 2
    assert body["maximum"] == 30.0


async def test_category_aggregation(client: AsyncClient, registered_user: dict) -> None:
    headers = registered_user["headers"]
    await _seed(client, headers)

    response = await client.get("/api/v1/analytics/categories", headers=headers)
    assert response.status_code == 200
    buckets = {item["category"]: item for item in response.json()}
    assert buckets["temperature"]["count"] == 2
    assert buckets["temperature"]["total"] == 40.0
    assert buckets["temperature"]["average"] == 20.0
    assert buckets["humidity"]["count"] == 1


async def test_trend_groups_by_day(client: AsyncClient, registered_user: dict) -> None:
    headers = registered_user["headers"]
    await _seed(client, headers)

    response = await client.get(
        "/api/v1/analytics/trend", headers=headers, params={"granularity": "day"}
    )
    assert response.status_code == 200
    points = response.json()
    assert len(points) == 3
    assert all(point["count"] == 1 for point in points)


async def test_trend_groups_by_month(client: AsyncClient, registered_user: dict) -> None:
    headers = registered_user["headers"]
    await _seed(client, headers)

    response = await client.get(
        "/api/v1/analytics/trend", headers=headers, params={"granularity": "month"}
    )
    assert response.status_code == 200
    points = {point["bucket"]: point for point in response.json()}
    assert len(points) == 2
    january = next(point for bucket, point in points.items() if bucket.endswith("01"))
    assert january["count"] == 2


async def test_trend_rejects_invalid_granularity(client: AsyncClient, registered_user: dict) -> None:
    response = await client.get(
        "/api/v1/analytics/trend",
        headers=registered_user["headers"],
        params={"granularity": "week"},
    )
    assert response.status_code == 422


async def test_export_returns_excel_workbook(client: AsyncClient, registered_user: dict) -> None:
    headers = registered_user["headers"]
    await _seed(client, headers)

    response = await client.get("/api/v1/analytics/export", headers=headers)
    assert response.status_code == 200
    assert response.headers["content-type"] == XLSX_MEDIA_TYPE
    assert "attachment" in response.headers["content-disposition"]

    # xlsx 為 zip 容器，確認四個工作表皆已寫入
    with zipfile.ZipFile(io.BytesIO(response.content)) as workbook:
        sheets = [name for name in workbook.namelist() if name.startswith("xl/worksheets/sheet")]
    assert len(sheets) == 4


async def test_analytics_requires_authentication(client: AsyncClient) -> None:
    assert (await client.get("/api/v1/analytics/summary")).status_code == 401
    assert (await client.get("/api/v1/analytics/export")).status_code == 401


async def test_viewer_can_read_analytics(client: AsyncClient, viewer_user: dict) -> None:
    response = await client.get("/api/v1/analytics/summary", headers=viewer_user["headers"])
    assert response.status_code == 200
