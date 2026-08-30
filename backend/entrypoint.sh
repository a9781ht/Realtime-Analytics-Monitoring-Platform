#!/bin/sh
# 後端容器啟動流程：等待資料庫 -> 執行 Alembic 遷移 -> 啟動服務
set -e

echo "[entrypoint] 等待資料庫 ${DB_HOST}:${DB_PORT} 就緒..."
python - <<'PY'
import os, socket, time

host = os.getenv("DB_HOST", "mariadb")
port = int(os.getenv("DB_PORT", "3306"))

for attempt in range(1, 61):
    try:
        with socket.create_connection((host, port), timeout=2):
            print(f"[entrypoint] 資料庫已就緒（第 {attempt} 次嘗試）")
            break
    except OSError:
        time.sleep(2)
else:
    raise SystemExit("[entrypoint] 資料庫連線逾時")
PY

echo "[entrypoint] 執行 Alembic 資料庫遷移..."
alembic upgrade head

echo "[entrypoint] 啟動應用程式：$*"
exec "$@"
