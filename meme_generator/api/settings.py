"""管理面板的设置接口：读取与修改服务端配置。"""

from typing import Any, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from ..config import config_file_path, meme_config
from ..errors import ApiError, ErrorCode
from ..log import logger
from ..repos import normalize_proxy, repo_manager
from .deps import require_admin

router = APIRouter(prefix="/admin/settings", tags=["admin-settings"])


class ServerSettings(BaseModel):
    api_domain: str = Field(
        description="对外访问地址，用于 API 文档中的示例；留空则用当前地址"
    )
    host: str
    port: int


class RepoSettings(BaseModel):
    github_proxy: str = Field(
        description="全局 GitHub 加速源前缀，留空表示直连；单个仓库可以单独覆盖"
    )
    effective_proxy: str = Field(description="当前实际生效的加速源")
    proxy_presets: list[str] = Field(description="管理面板里可选的加速源")


class SettingsResponse(BaseModel):
    server: ServerSettings
    repo: RepoSettings
    config_file: str


class UpdateSettingsRequest(BaseModel):
    api_domain: Optional[str] = Field(
        default=None, description="留空字符串可清空为「使用当前地址」"
    )
    github_proxy: Optional[str] = Field(
        default=None, description="留空字符串可清空为直连"
    )


def _response() -> SettingsResponse:
    server = meme_config.server
    return SettingsResponse(
        server=ServerSettings(
            api_domain=server.api_domain,
            host=server.host,
            port=server.port,
        ),
        repo=RepoSettings(
            github_proxy=meme_config.repo.github_proxy,
            effective_proxy=repo_manager.default_proxy(),
            proxy_presets=list(meme_config.repo.proxy_presets),
        ),
        config_file=str(config_file_path),
    )


@router.get("", response_model=SettingsResponse)
def get_settings(_: str = Depends(require_admin)):
    return _response()


@router.patch("", response_model=SettingsResponse)
def update_settings(data: UpdateSettingsRequest, _: str = Depends(require_admin)):
    """更新可在线修改的设置项并写回配置文件。"""
    if data.api_domain is not None:
        value = data.api_domain.strip().rstrip("/")
        if value and not value.startswith(("http://", "https://")):
            raise ApiError(
                ErrorCode.VALIDATION_ERROR,
                "API 域名需要以 http:// 或 https:// 开头",
                status_code=400,
                context={"field": "api_domain"},
            )
        meme_config.server.api_domain = value
        logger.info(f"API domain set to {value or '(empty)'}")

    if data.github_proxy is not None:
        try:
            value = normalize_proxy(data.github_proxy)
        except ValueError as e:
            raise ApiError(
                ErrorCode.VALIDATION_ERROR,
                str(e),
                status_code=400,
                context={"field": "github_proxy"},
            )
        meme_config.repo.github_proxy = value
        logger.info(f"Global github proxy set to {value or '(direct)'}")

    try:
        meme_config.dump()
    except OSError as e:
        raise ApiError(
            ErrorCode.INTERNAL_ERROR,
            f"配置写入失败：{e}",
            status_code=500,
        ) from e

    return _response()


@router.get("/schema", include_in_schema=False)
def config_schema(_: str = Depends(require_admin)) -> dict[str, Any]:
    """当前配置的完整快照，便于排查问题。"""
    from ..compat import model_dump

    return model_dump(meme_config)
