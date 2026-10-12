"""管理接口的鉴权依赖。"""

from typing import Optional

from fastapi import Header, Request

from ..admin import admin_auth
from ..errors import ApiError, ErrorCode


def _extract_token(
    authorization: Optional[str], admin_token: Optional[str]
) -> Optional[str]:
    """从请求头里取出令牌。

    ``Bearer <token>`` 是标准写法；不带 scheme 时按裸令牌处理，方便调试。
    ``Bearer`` 后面没有内容则视为未提供令牌。
    """
    if admin_token:
        return admin_token
    if not authorization:
        return None

    scheme, _, token = authorization.partition(" ")
    if not token:
        # 只有 scheme 而没有令牌（例如 "Bearer"），视为未提供
        if scheme.strip().lower() in ("bearer", "token", "basic"):
            return None
        return scheme.strip() or None
    if scheme.lower() == "bearer":
        return token.strip() or None
    return authorization.strip() or None


async def require_admin(
    request: Request,
    authorization: Optional[str] = Header(default=None),
    x_admin_token: Optional[str] = Header(default=None),
) -> str:
    """需要管理员登录的接口。返回校验通过的令牌。

    令牌也可以放在 ``?token=`` 查询参数里，方便浏览器直接打开预览图片。
    """
    token = _extract_token(authorization, x_admin_token) or request.query_params.get(
        "token"
    )

    if not admin_auth.initialized:
        raise ApiError(
            ErrorCode.ADMIN_NOT_INITIALIZED,
            "管理面板尚未初始化，请先设置管理员密码",
            status_code=403,
        )
    if not token:
        raise ApiError(ErrorCode.UNAUTHORIZED, "缺少访问令牌", status_code=401)
    if not admin_auth.verify_token(token):
        raise ApiError(
            ErrorCode.TOKEN_INVALID, "令牌无效或已过期，请重新登录", status_code=401
        )
    return token


async def optional_admin(
    request: Request,
    authorization: Optional[str] = Header(default=None),
    x_admin_token: Optional[str] = Header(default=None),
) -> bool:
    """可选鉴权：已登录返回 True，未登录返回 False 而不报错。"""
    token = _extract_token(authorization, x_admin_token) or request.query_params.get(
        "token"
    )
    if not token or not admin_auth.initialized:
        return False
    return admin_auth.verify_token(token)
