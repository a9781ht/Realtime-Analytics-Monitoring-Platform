"""API v1 路由彙整。"""

from fastapi import APIRouter

from app.api.v1 import admin, analytics, auth, realtime, records, users

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(users.router)
api_router.include_router(records.router)
api_router.include_router(analytics.router)
api_router.include_router(realtime.router)
api_router.include_router(admin.router)
