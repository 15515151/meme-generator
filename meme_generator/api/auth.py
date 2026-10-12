"""管理面板认证接口：首次初始化、登录、改密、登录状态。"""

from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from ..admin import MIN_PASSWORD_LENGTH, admin_auth
from ..errors import ApiError, ErrorCode
from ..log import logger
from .deps import optional_admin, require_admin

router = APIRouter(prefix="/admin", tags=["admin"])


class SetupRequest(BaseModel):
    # 长度下限交由处理函数校验，这样能返回统一的 ADMIN_PASSWORD_TOO_WEAK
    password: str


class LoginRequest(BaseModel):
    password: str


class ChangePasswordRequest(BaseModel):
    old_password: str
    new_password: str


class AuthStatusResponse(BaseModel):
    initialized: bool
    authenticated: bool
    min_password_length: int = MIN_PASSWORD_LENGTH


class TokenResponse(BaseModel):
    token: str
    expires_in: int
    initialized: bool = True


def _check_initialized() -> None:
    if not admin_auth.initialized:
        raise ApiError(
            ErrorCode.ADMIN_NOT_INITIALIZED,
            "管理面板尚未初始化，请先设置管理员密码",
            status_code=403,
            context={"setup_required": True},
        )


@router.get("/status", response_model=AuthStatusResponse)
def status(authenticated: bool = Depends(optional_admin)):
    """前端启动时调用：判断是首次初始化还是需要登录。"""
    return AuthStatusResponse(
        initialized=admin_auth.initialized,
        authenticated=authenticated,
    )


@router.post("/setup", response_model=TokenResponse)
def setup(data: SetupRequest):
    """首次设置管理员密码。已初始化后再次调用会失败。"""
    if admin_auth.initialized:
        raise ApiError(
            ErrorCode.ADMIN_ALREADY_INITIALIZED,
            "管理员密码已设置，请直接登录",
            status_code=409,
        )
    if len(data.password) < MIN_PASSWORD_LENGTH:
        raise ApiError(
            ErrorCode.ADMIN_PASSWORD_TOO_WEAK,
            f"密码长度至少为 {MIN_PASSWORD_LENGTH} 位",
            status_code=400,
            context={"min_length": MIN_PASSWORD_LENGTH},
        )

    try:
        admin_auth.setup(data.password)
    except ValueError as e:
        raise ApiError(ErrorCode.ADMIN_ALREADY_INITIALIZED, str(e), status_code=409)

    logger.info("Admin password initialized")
    token = admin_auth.create_token()
    from ..admin import TOKEN_TTL_SECONDS

    return TokenResponse(token=token, expires_in=TOKEN_TTL_SECONDS)


@router.post("/login", response_model=TokenResponse)
def login(data: LoginRequest):
    _check_initialized()
    if not admin_auth.verify_password(data.password):
        raise ApiError(
            ErrorCode.ADMIN_PASSWORD_INCORRECT, "密码不正确", status_code=401
        )
    from ..admin import TOKEN_TTL_SECONDS

    token = admin_auth.create_token()
    return TokenResponse(token=token, expires_in=TOKEN_TTL_SECONDS, initialized=True)


@router.post("/logout")
def logout(_: str = Depends(require_admin)):
    """令牌是无状态的，登出由前端丢弃令牌完成。"""
    return {"ok": True}


@router.post("/password", response_model=TokenResponse)
def change_password(data: ChangePasswordRequest, _: str = Depends(require_admin)):
    """修改密码。成功后旧令牌全部失效，返回新令牌。"""
    _check_initialized()
    if len(data.new_password) < MIN_PASSWORD_LENGTH:
        raise ApiError(
            ErrorCode.ADMIN_PASSWORD_TOO_WEAK,
            f"密码长度至少为 {MIN_PASSWORD_LENGTH} 位",
            status_code=400,
            context={"min_length": MIN_PASSWORD_LENGTH},
        )
    try:
        admin_auth.change_password(data.old_password, data.new_password)
    except ValueError as e:
        raise ApiError(ErrorCode.ADMIN_PASSWORD_INCORRECT, str(e), status_code=401)

    logger.info("Admin password changed")
    from ..admin import TOKEN_TTL_SECONDS

    return TokenResponse(token=admin_auth.create_token(), expires_in=TOKEN_TTL_SECONDS)


@router.get("/me")
def me(token: str = Depends(require_admin)):
    return {"authenticated": True, "token_prefix": token[:8]}


class HealthResponse(BaseModel):
    ok: bool = True
    version: str
    initialized: bool
    memes: int
    disabled: int
    repos: int


@router.get("/health", response_model=HealthResponse)
def health(_: Optional[bool] = Depends(optional_admin)):
    """管理端概览数据。"""
    from ..manager import get_all_memes, get_disabled_meme_keys
    from ..repos import repo_manager
    from ..version import __version__

    return HealthResponse(
        version=__version__,
        initialized=admin_auth.initialized,
        memes=len(get_all_memes()),
        disabled=len(get_disabled_meme_keys()),
        repos=len(repo_manager.list_repos()),
    )
