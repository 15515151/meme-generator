"""管理面板的外部表情仓库接口。"""

from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from ..errors import ApiError, ErrorCode
from ..log import logger
from ..repos import (
    PRESET_REPOS,
    normalize_repo_url,
    repo_manager,
    repo_source_name,
)
from .deps import require_admin

router = APIRouter(prefix="/admin/repos", tags=["admin-repos"])


class RepoAddRequest(BaseModel):
    url: str = Field(description="GitHub 仓库地址或 owner/repo，也支持本地绝对路径")
    ref: str = Field(default="", description="分支、标签或提交，留空自动探测")
    name: str = Field(default="", description="显示名称，留空用仓库名")
    meme_dir: str = Field(
        default="", description="仓库内表情目录，留空自动探测（memes/ 或 emoji/）"
    )


class RepoPreviewRequest(BaseModel):
    url: str = Field(description="待探测的仓库地址")
    ref: str = Field(default="", description="分支，留空自动探测")


class RepoUpdateRequest(BaseModel):
    apply: bool = Field(default=False, description="是否立即应用变更")


class RepoInfo(BaseModel):
    identifier: str
    name: str
    display_name: str
    url: str
    ref: str
    enabled: bool
    meme_dir: str
    installed_at: Optional[float] = None
    updated_at: Optional[float] = None
    file_count: int
    meme_keys: list[str]
    meme_count: int
    installed: bool = True
    source: str


def _info(state) -> RepoInfo:
    keys = state.meme_keys
    return RepoInfo(
        identifier=state.identifier,
        name=state.name,
        display_name=state.display_name,
        url=state.url,
        ref=state.ref,
        enabled=state.enabled,
        meme_dir=state.meme_dir,
        installed_at=state.installed_at,
        updated_at=state.updated_at,
        file_count=len(state.files),
        meme_keys=keys,
        meme_count=len(keys),
        source=repo_source_name(state.identifier),
    )


@router.get("")
def list_repos(_: str = Depends(require_admin)):
    repos = [_info(state) for state in repo_manager.list_repos()]
    return {"total": len(repos), "items": repos}


@router.get("/presets")
def list_presets(_: str = Depends(require_admin)):
    """内置的常用仓库，附带「是否已添加」状态。"""
    items = []
    for preset in PRESET_REPOS:
        identifier = normalize_repo_url(preset["url"])
        existing = repo_manager.get_repo(identifier)
        items.append(
            {
                **preset,
                "identifier": identifier,
                "installed": existing is not None,
                "installed_id": existing.identifier if existing else None,
                "meme_count": len(existing.meme_keys) if existing else 0,
            }
        )
    return {"total": len(items), "items": items}


@router.post("/preview")
async def preview_repo(data: RepoPreviewRequest, _: str = Depends(require_admin)):
    """添加前探测仓库：自动识别表情目录、统计表情数量。"""
    try:
        return await repo_manager.preview(data.url, data.ref)
    except ValueError as e:
        raise ApiError(
            ErrorCode.REPO_INVALID, str(e), status_code=400, context={"url": data.url}
        )
    except Exception as e:  # noqa: BLE001 - 网络/解析异常统一转换
        logger.opt(exception=e).error(f"Failed to preview repo {data.url}")
        raise ApiError(
            ErrorCode.REPO_FETCH_FAILED,
            f"仓库探测失败：{e}",
            status_code=502,
            context={"url": data.url},
        )


@router.post("", response_model=RepoInfo, status_code=201)
async def add_repo(data: RepoAddRequest, _: str = Depends(require_admin)):
    """注册并下载一个外部表情仓库，随后立即加载其中的表情。"""
    try:
        normalized = normalize_repo_url(data.url)
    except ValueError as e:
        raise ApiError(ErrorCode.REPO_INVALID, str(e), status_code=400)

    if repo_manager.get_repo(normalized):
        raise ApiError(
            ErrorCode.REPO_ALREADY_EXISTS,
            f"仓库已存在：{normalized}",
            status_code=409,
            context={"identifier": normalized},
        )

    try:
        state = await repo_manager.install(
            data.url, ref=data.ref, name=data.name, meme_dir=data.meme_dir
        )
    except ValueError as e:
        raise ApiError(
            ErrorCode.REPO_INVALID, str(e), status_code=400, context={"url": data.url}
        )
    except Exception as e:  # noqa: BLE001 - 网络/解析异常统一转成规范错误
        logger.opt(exception=e).error(f"Failed to install repo {data.url}")
        raise ApiError(
            ErrorCode.REPO_FETCH_FAILED,
            f"仓库拉取失败：{e}",
            status_code=502,
            context={"url": data.url},
        )

    logger.info(
        f"Installed repo {state.identifier} with {len(state.meme_keys)} meme(s)"
    )
    return _info(state)


@router.delete("/{identifier:path}")
def remove_repo(identifier: str, _: str = Depends(require_admin)):
    """移除仓库，并卸载它带来的表情。"""
    state = repo_manager.get_repo(identifier)
    if not state:
        raise ApiError(
            ErrorCode.REPO_NOT_FOUND,
            f"仓库不存在：{identifier}",
            status_code=404,
        )

    removed = repo_manager.uninstall(state.identifier)
    logger.info(f"Removed repo {state.identifier}, unloaded {len(removed)} meme(s)")
    return {
        "identifier": state.identifier,
        "removed_memes": removed,
        "message": f"已移除仓库，卸载 {len(removed)} 个表情",
    }


@router.post("/{identifier:path}/update")
async def update_repo(
    identifier: str, data: RepoUpdateRequest, _: str = Depends(require_admin)
):
    """更新仓库。``apply=false`` 时只检查并返回变更，不写入。"""
    state = repo_manager.get_repo(identifier)
    if not state:
        raise ApiError(
            ErrorCode.REPO_NOT_FOUND, f"仓库不存在：{identifier}", status_code=404
        )

    if not data.apply:
        try:
            result = await repo_manager.check_update(state.identifier)
        except Exception as e:  # noqa: BLE001
            logger.opt(exception=e).error(f"Failed to check repo {identifier}")
            raise ApiError(
                ErrorCode.REPO_FETCH_FAILED,
                f"检查更新失败：{e}",
                status_code=502,
            )
        return {"applied": False, **result}

    try:
        updated_state, changes = await repo_manager.update(state.identifier)
    except Exception as e:  # noqa: BLE001
        logger.opt(exception=e).error(f"Failed to update repo {identifier}")
        raise ApiError(
            ErrorCode.REPO_FETCH_FAILED,
            f"更新失败：{e}",
            status_code=502,
        )

    return {
        "applied": True,
        "identifier": updated_state.identifier,
        "has_update": bool(
            changes["added"] or changes["modified"] or changes["removed"]
        ),
        "changes": changes,
    }


@router.post("/{identifier:path}/reload")
def reload_repo(identifier: str, _: str = Depends(require_admin)):
    """从本地已下载的内容重新加载表情，用于加载失败后重试。"""
    state = repo_manager.get_repo(identifier)
    if not state:
        raise ApiError(
            ErrorCode.REPO_NOT_FOUND, f"仓库不存在：{identifier}", status_code=404
        )

    from ..manager import unload_memes_by_source
    from ..repos import repo_source_name

    unload_memes_by_source(repo_source_name(state.identifier))
    loaded = repo_manager.load_repo_memes(state)
    return {
        "identifier": state.identifier,
        "loaded_memes": loaded,
        "message": f"已重新加载 {len(loaded)} 个表情",
    }
