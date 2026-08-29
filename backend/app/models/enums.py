"""共用列舉型別。"""

from __future__ import annotations

from enum import Enum


class UserRole(str, Enum):
    """使用者角色。

    - ADMIN：系統管理員，可管理所有資料與使用者
    - USER：一般使用者，可建立/維護自己的資料
    - VIEWER：唯讀使用者，僅能瀏覽與分析
    """

    ADMIN = "admin"
    USER = "user"
    VIEWER = "viewer"


class AlertLevel(str, Enum):
    """即時資料告警等級。"""

    NORMAL = "normal"
    WARNING = "warning"
    CRITICAL = "critical"
