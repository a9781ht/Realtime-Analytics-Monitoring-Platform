# 系統架構文件

> 本文件所有圖表以 [Mermaid](https://mermaid.js.org/) 撰寫，GitHub 可直接渲染。

---

## 1. 系統整體架構圖

```mermaid
graph TB
    subgraph Client["使用者端"]
        Browser["瀏覽器<br/>Chrome / Edge"]
    end

    subgraph DockerNet["Docker Network: analytics-net"]
        subgraph FE["Streamlit 前端容器 :8501"]
            direction TB
            Login["登入 / 註冊頁"]
            Dash["總覽儀表板"]
            RT["即時監控頁<br/>(WebSocket Client Thread)"]
            Rec["資料管理頁"]
            Ana["資料分析頁"]
            Adm["系統管理頁 (Admin)"]
        end

        subgraph BE["FastAPI 後端容器 :8000"]
            direction TB
            MW["Middleware<br/>RequestLog / CORS"]
            Auth["Auth Router<br/>JWT 簽發與驗證"]
            API["REST Routers<br/>users / records / analytics / admin"]
            WS["WebSocket Router<br/>/realtime/ws"]
            SVC["Service Layer<br/>business logic"]
            GEN["Realtime Generator<br/>asyncio background task"]
            BUF["記憶體緩衝區<br/>Batch Buffer"]
            ORM["SQLAlchemy 2.0 Async ORM<br/>Connection Pool"]
        end

        subgraph DB["MariaDB 11.7 容器 :3306"]
            Tables[("users<br/>data_records<br/>metric_points<br/>system_logs")]
        end
    end

    Vol[("Docker Volume<br/>mariadb_data")]

    Browser -->|HTTP| FE
    FE -->|REST API + JWT| MW
    RT -.->|WebSocket + token| WS
    MW --> Auth
    MW --> API
    Auth --> SVC
    API --> SVC
    WS --> GEN
    GEN -->|每秒產生| BUF
    GEN -->|廣播| WS
    BUF -->|定期 / 條件觸發<br/>批次寫入| ORM
    SVC --> ORM
    ORM -->|asyncmy| Tables
    Tables --- Vol
```

---

## 2. 分層架構

```mermaid
graph LR
    A["Presentation<br/>Streamlit Views"] --> B["API Layer<br/>FastAPI Routers"]
    B --> C["Dependency Layer<br/>認證 / 權限 / Session"]
    C --> D["Service Layer<br/>user / record / analytics / metric / log"]
    D --> E["Data Layer<br/>SQLAlchemy ORM Models"]
    E --> F[("MariaDB 11.7")]

    style A fill:#E8F5E9
    style B fill:#E3F2FD
    style C fill:#FFF3E0
    style D fill:#F3E5F5
    style E fill:#FCE4EC
    style F fill:#ECEFF1
```

---

## 3. 資料庫 ER 圖

```mermaid
erDiagram
    USERS ||--o{ DATA_RECORDS : "建立"
    USERS ||--o{ SYSTEM_LOGS : "產生"

    USERS {
        int id PK
        string username UK "唯一帳號"
        string email UK
        string full_name
        string hashed_password "bcrypt"
        string role "admin / user / viewer"
        bool is_active
        datetime created_at
        datetime updated_at
    }

    DATA_RECORDS {
        int id PK
        string title
        float value
        string category
        text description
        datetime recorded_at
        int owner_id FK
        datetime created_at
        datetime updated_at
    }

    METRIC_POINTS {
        int id PK
        string sensor_id
        string metric_name
        float value
        string unit
        bool is_alert
        string alert_level "normal / warning / critical"
        datetime generated_at
        datetime created_at
    }

    SYSTEM_LOGS {
        int id PK
        string level
        string action
        text message
        string method
        string path
        int status_code
        int duration_ms
        string client_ip
        int user_id FK
        datetime created_at
    }
```

---

## 4. JWT 認證流程

```mermaid
sequenceDiagram
    participant U as 使用者
    participant S as Streamlit
    participant A as FastAPI
    participant D as MariaDB

    U->>S: 輸入帳號密碼
    S->>A: POST /api/v1/auth/login
    A->>D: SELECT User WHERE username (ORM)
    D-->>A: User row
    A->>A: bcrypt.checkpw 驗證密碼
    A-->>S: access_token + refresh_token
    S->>S: 存入 st.session_state

    Note over S,A: 之後每次請求皆帶入 Authorization: Bearer

    S->>A: GET /api/v1/records (Bearer token)
    A->>A: decode_token → 取得 sub / role
    A->>D: 查詢使用者狀態
    A->>A: require_roles 權限檢查
    A-->>S: 200 分頁資料

    Note over S,A: Token 過期時
    S->>A: POST /api/v1/auth/refresh
    A-->>S: 新的 access_token
```

---

## 5. 即時資料推送與批次寫入流程

```mermaid
sequenceDiagram
    participant G as Generator<br/>(asyncio task)
    participant B as Buffer<br/>(in-memory list)
    participant M as ConnectionManager
    participant W as WebSocket Clients
    participant F as Flusher<br/>(asyncio task)
    participant D as MariaDB

    loop 每 GENERATOR_INTERVAL_SECONDS 秒
        G->>G: 隨機產生感測器資料
        G->>G: classify() 依閾值標記告警等級
        G->>B: 加入緩衝區
        G->>M: broadcast(JSON)
        M->>W: 推送 {"type":"metrics", payload:[...]}
        alt 緩衝筆數 >= GENERATOR_FLUSH_SIZE
            G->>D: 條件觸發：ORM add_all 批次寫入
        end
    end

    loop 每 GENERATOR_FLUSH_INTERVAL 秒
        F->>B: 取出全部緩衝資料
        F->>D: 定期觸發：ORM add_all + commit
        D-->>F: 寫入完成
    end
```

---

## 6. 權限矩陣

```mermaid
graph TD
    subgraph Roles["角色權限"]
        Admin["admin"]
        User["user"]
        Viewer["viewer"]
    end

    Admin --> P1["資料 CRUD（全部資料）"]
    Admin --> P2["使用者管理 / 權限調整"]
    Admin --> P3["系統日誌 / 資料庫監控"]
    Admin --> P4["即時資料歷史查詢"]
    Admin --> P5["資料分析與 Excel 下載"]

    User --> P6["資料 CRUD（僅限自己建立）"]
    User --> P5
    User --> P4

    Viewer --> P7["資料唯讀查詢"]
    Viewer --> P5
    Viewer --> P4

    style Admin fill:#FFCDD2
    style User fill:#C8E6C9
    style Viewer fill:#BBDEFB
```

---

## 7. 容器部署拓撲

```mermaid
graph TB
    subgraph Host["Docker Host"]
        subgraph Net["bridge network: analytics-net"]
            FE["analytics-frontend<br/>streamlit:8501"]
            BE["analytics-backend<br/>uvicorn:8000"]
            DB["analytics-mariadb<br/>mariadb:3306"]
        end
        V1[("volume<br/>mariadb_data")]
        V2[("volume<br/>backend_logs")]
    end

    P1["host :8501"] --> FE
    P2["host :8000"] --> BE
    P3["host :3306"] --> DB

    FE -->|http://backend:8000| BE
    FE -.->|ws://backend:8000| BE
    BE -->|mysql+asyncmy://mariadb:3306| DB
    DB --- V1
    BE --- V2

    FE -.->|healthcheck<br/>/_stcore/health| FE
    BE -.->|healthcheck<br/>/health| BE
    DB -.->|healthcheck.sh<br/>--connect| DB
```

---

## 8. 技術決策說明

| 項目 | 選擇 | 理由 |
| --- | --- | --- |
| ORM | SQLAlchemy 2.0 Async | 需求明確禁止原生 SQL；2.0 typing 支援佳，`Mapped[]` 型別安全 |
| DB Driver | asyncmy | MariaDB / MySQL 的高效能 asyncio 驅動，與 SQLAlchemy async 相容 |
| 遷移 | Alembic（async env） | 版本化 schema 管理，容器啟動時自動 `upgrade head` |
| 密碼雜湊 | bcrypt (cost=12) | 業界標準、抗暴力破解；避免 passlib 版本相依問題 |
| Token | PyJWT (HS256) | 無狀態認證，access + refresh 雙 token |
| 即時推送 | FastAPI WebSocket + asyncio task | 與 API 共用事件迴圈，免額外 broker |
| 批次寫入 | 記憶體緩衝 + 雙觸發 | 降低單筆 INSERT 造成的 IO 壓力 |
| 前端 | Streamlit `st.navigation` | 原生多頁架構、`st.fragment(run_every)` 局部刷新不整頁重載 |
| 容器 | 多階段建構 + 非 root 使用者 | 縮小映像體積、降低安全風險 |
