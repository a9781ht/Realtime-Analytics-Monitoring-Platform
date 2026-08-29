# API 端點文件

- Base URL：`http://localhost:8000`
- API 前綴：`/api/v1`
- 互動式文件：<http://localhost:8000/docs>（Swagger UI）、<http://localhost:8000/redoc>
- OpenAPI 規格：<http://localhost:8000/openapi.json>

## 認證方式

除公開端點外，所有請求需在標頭帶入 JWT：

```http
Authorization: Bearer <access_token>
```

於 Swagger UI 可點右上角 **Authorize**，輸入測試帳號（例如 `admin` / `Admin@1234`）自動帶入 Token。

## 統一錯誤格式

```json
{
  "error": {
    "code": "permission_denied",
    "message": "僅資料建立者或管理員可執行此操作"
  }
}
```

| HTTP 狀態 | code | 說明 |
| --- | --- | --- |
| 401 | `unauthorized` | 未登入、Token 無效或過期 |
| 403 | `permission_denied` | 角色權限不足 |
| 404 | `not_found` | 資源不存在 |
| 409 | `conflict` | 資料衝突（帳號 / Email 重複） |
| 422 | `validation_error` | 請求資料驗證失敗（含欄位明細） |
| 500 | `internal_server_error` / `database_error` | 伺服器或資料庫錯誤 |

## 分頁回應格式

```json
{
  "items": [ ... ],
  "meta": { "total": 128, "page": 1, "size": 20, "pages": 7 }
}
```

---

## 1. Auth 認證

| 方法 | 路徑 | 權限 | 說明 |
| --- | --- | --- | --- |
| POST | `/auth/register` | 公開 | 註冊（固定 `user` 角色） |
| POST | `/auth/login` | 公開 | 登入（JSON） |
| POST | `/auth/login/form` | 公開 | 登入（OAuth2 表單，供 Swagger Authorize） |
| POST | `/auth/refresh` | 公開 | 以 refresh token 換發新 token |
| GET | `/auth/me` | 已登入 | 取得個人資訊 |
| POST | `/auth/logout` | 已登入 | 登出（記錄事件） |

```bash
curl -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"Admin@1234"}'
```

```json
{
  "access_token": "eyJhbGciOi...",
  "refresh_token": "eyJhbGciOi...",
  "token_type": "bearer",
  "expires_in": 7200
}
```

---

## 2. Users 使用者

| 方法 | 路徑 | 權限 | 說明 |
| --- | --- | --- | --- |
| GET | `/users/me` | 已登入 | 個人資料 |
| PATCH | `/users/me` | 已登入 | 更新 Email / 名稱 / 密碼 |
| GET | `/users` | admin | 使用者列表（`page`, `size`, `keyword`, `role`, `is_active`） |
| POST | `/users` | admin | 建立使用者（可指定角色） |
| GET | `/users/{id}` | admin 或本人 | 查詢單一使用者 |
| PATCH | `/users/{id}/role` | admin | 調整角色 / 啟用狀態 |
| DELETE | `/users/{id}` | admin | 刪除使用者 |

---

## 3. Records 資料管理

| 方法 | 路徑 | 權限 | 說明 |
| --- | --- | --- | --- |
| GET | `/records` | 已登入 | 分頁查詢 |
| GET | `/records/categories` | 已登入 | 取得所有分類 |
| GET | `/records/{id}` | 已登入 | 單筆查詢 |
| POST | `/records` | admin, user | 建立 |
| PUT | `/records/{id}` | 建立者 / admin | 整筆更新 |
| PATCH | `/records/{id}` | 建立者 / admin | 部分更新 |
| DELETE | `/records/{id}` | 建立者 / admin | 刪除 |
| POST | `/records/bulk` | admin, user | JSON 批量匯入 |
| POST | `/records/import` | admin, user | 上傳 CSV / JSON 匯入 |

### `GET /records` 查詢參數

| 參數 | 型別 | 預設 | 說明 |
| --- | --- | --- | --- |
| `page` | int | 1 | 頁碼 |
| `size` | int | 20 | 每頁筆數（上限 200） |
| `keyword` | string | - | 標題關鍵字 |
| `category` | string | - | 分類篩選 |
| `owner_id` | int | - | 建立者篩選 |
| `min_value` / `max_value` | float | - | 數值區間 |
| `start_time` / `end_time` | datetime | - | 時間範圍（ISO 8601） |
| `sort_by` | enum | recorded_at | `id` / `title` / `value` / `category` / `recorded_at` / `created_at` |
| `order` | enum | desc | `asc` / `desc` |

```bash
curl -X POST http://localhost:8000/api/v1/records \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"title":"生產線A-爐溫","value":78.42,"category":"temperature","description":"早班量測"}'
```

---

## 4. Analytics 資料分析

| 方法 | 路徑 | 權限 | 說明 |
| --- | --- | --- | --- |
| GET | `/analytics/summary` | 已登入 | 總計 / 平均 / 最大 / 最小 / 筆數 |
| GET | `/analytics/categories` | 已登入 | 分類聚合 |
| GET | `/analytics/trend` | 已登入 | 趨勢（`granularity` = `hour` / `day` / `month`） |
| GET | `/analytics/export` | 已登入 | 下載 Excel 報表（四個工作表） |

共用篩選參數：`category`、`owner_id`、`start_time`、`end_time`。

```bash
curl -X GET "http://localhost:8000/api/v1/analytics/export?granularity=day" \
  -H "Authorization: Bearer $TOKEN" -o report.xlsx
```

---

## 5. Realtime 即時監控

| 方法 | 路徑 | 權限 | 說明 |
| --- | --- | --- | --- |
| WS | `/realtime/ws?token=<access_token>` | 已登入 | 即時資料推送通道 |
| GET | `/realtime/status` | 已登入 | 產生器狀態、連線數、緩衝筆數 |
| GET | `/realtime/latest` | 已登入 | 最新一批資料（WebSocket 備援） |
| GET | `/realtime/metrics` | 已登入 | 即時資料歷史查詢（分頁） |
| GET | `/realtime/metrics/summary` | 已登入 | 各感測器統計 |
| POST | `/realtime/flush` | admin | 立即批次寫入緩衝資料 |

### WebSocket 訊息格式

連線成功：

```json
{
  "type": "welcome",
  "timestamp": "2026-08-29T10:00:00+00:00",
  "payload": { "username": "admin", "role": "admin", "threshold_high": 90.0, "threshold_low": 10.0 }
}
```

即時資料（每秒推送）：

```json
{
  "type": "metrics",
  "timestamp": "2026-08-29T10:00:01+00:00",
  "payload": [
    {
      "sensor_id": "SENSOR-01",
      "metric_name": "temperature",
      "unit": "°C",
      "value": 93.42,
      "is_alert": true,
      "alert_level": "warning",
      "generated_at": "2026-08-29T10:00:01"
    }
  ]
}
```

用戶端可傳送 `ping`，伺服器回覆 `{"type": "pong", ...}`。

---

## 6. Admin 系統管理（全部僅限 admin）

| 方法 | 路徑 | 說明 |
| --- | --- | --- |
| GET | `/admin/overview` | 系統概覽（使用者 / 資料 / 即時資料 / 告警統計） |
| GET | `/admin/logs` | 系統日誌查詢（`level`, `keyword`, `user_id`, 時間範圍、分頁） |
| GET | `/admin/database` | 資料庫狀態（連線、連接池、各表筆數、伺服器時間） |

---

## 7. System 系統端點

| 方法 | 路徑 | 說明 |
| --- | --- | --- |
| GET | `/` | 服務資訊 |
| GET | `/health` | 健康檢查（資料庫連線、產生器狀態） |
