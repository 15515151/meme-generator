"""管理面板的设置接口：读取与修改服务端配置。"""

from typing import Any, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from ..config import config_file_path, meme_config
from ..errors import ApiError, ErrorCode
from ..log import logger
from .deps import require_admin

router = APIRouter(prefix="/admin/settings", tags=["admin-settings"])


class ServerSettings(BaseModel):
    api_domain: str = Field(
        description="对外访问地址，用于 API 文档中的示例；留空则用当前地址"
    )
    host: str
    port: int


class SettingsResponse(BaseModel):
    server: ServerSettings
    config_file: str


class UpdateSettingsRequest(BaseModel):
    api_domain: Optional[str] = Field(
        default=None, description="留空字符串可清空为「使用当前地址」"
    )


def _response() -> SettingsResponse:
    server = meme_config.server
    return SettingsResponse(
        server=ServerSettings(
            api_domain=server.api_domain,
            host=server.host,
            port=server.port,
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
