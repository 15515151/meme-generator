"""管理面板 API 路由的组装。"""

from fastapi import APIRouter

from . import auth, memes, repos, settings, updates


def build_admin_router() -> APIRouter:
    router = APIRouter(prefix="/api")
    router.include_router(auth.router)
    router.include_router(memes.router)
    router.include_router(repos.router)
    router.include_router(updates.router)
    router.include_router(settings.router)
    return router


__all__ = ["build_admin_router"]
