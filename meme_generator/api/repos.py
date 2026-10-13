"""管理面板的外部表情仓库接口。"""

from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from ..config import meme_config
from ..errors import ApiError, ErrorCode
from ..log import logger
from ..repos import (
    PRESET_REPOS,
    normalize_proxy,
    normalize_repo_url,
    probe_proxy,
    repo_manager,
    repo_source_name,
    split_accelerated_url,
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
    proxy: str = Field(
        default="",
        description="GitHub 加速源前缀，留空则用全局默认；空字符串表示直连",
    )


class RepoPreviewRequest(BaseModel):
    url: str = Field(description="待探测的仓库地址")
    ref: str = Field(default="", description="分支，留空自动探测")
    proxy: str = Field(default="", description="探测时使用的加速源前缀")


class RepoUpdateRequest(BaseModel):
    apply: bool = Field(default=False, description="是否立即应用变更")


class RepoSettingsRequest(BaseModel):
    proxy: Optional[str] = Field(
        default=None, description="加速源前缀；空字符串表示跟随全局默认"
    )
    name: Optional[str] = Field(default=None, description="显示名称")
    apply: bool = Field(default=False, description="改完后是否立即重新拉取一次")


class ProxyTestRequest(BaseModel):
    proxy: str = Field(default="", description="待测试的加速源，留空只测直连")
    identifier: str = Field(
        default="", description="用于测试的仓库，留空用内置示例仓库"
    )
    ref: str = Field(default="", description="分支，留空用 main")


class RepoInfo(BaseModel):
    identifier: str
    name: str
    display_name: str
    url: str
    ref: str
    enabled: bool
    meme_dir: str
    proxy: str = ""
    effective_proxy: str = ""
    accelerated_url: str = ""
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
        proxy=state.proxy,
        effective_proxy=repo_manager.effective_proxy(state),
        accelerated_url=repo_manager.accelerated_url(state),
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


@router.get("/proxies")
def list_proxies(_: str = Depends(require_admin)):
    """可选的加速源：全局默认值 + 配置文件里的预设列表。"""
    items = []
    for preset in meme_config.repo.proxy_presets:
        try:
            normalized = normalize_proxy(preset)
        except ValueError:
            continue
        if normalized and normalized not in items:
            items.append(normalized)
    return {"default": repo_manager.default_proxy(), "items": items}


@router.post("/proxy-test")
async def check_proxy(data: ProxyTestRequest, _: str = Depends(require_admin)):
    """测试加速源：分别访问 GitHub 接口与 raw 内容，并给出直连耗时对比。"""
    try:
        return await probe_proxy(data.proxy, data.identifier, data.ref)
    except ValueError as e:
        raise ApiError(
            ErrorCode.VALIDATION_ERROR,
            str(e),
            status_code=400,
            context={"proxy": data.proxy},
        )


@router.post("/preview")
async def preview_repo(data: RepoPreviewRequest, _: str = Depends(require_admin)):
    """添加前探测仓库：自动识别表情目录、统计表情数量。"""
    # 允许直接把「加速源 + 仓库地址」整串粘进来
    target, embedded_proxy = split_accelerated_url(data.url)
    proxy = data.proxy.strip() or embedded_proxy
    try:
        return await repo_manager.preview(target, data.ref, proxy=proxy)
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
    target, embedded_proxy = split_accelerated_url(data.url)
    proxy = data.proxy.strip() or embedded_proxy
    try:
        normalized = normalize_repo_url(target)
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
            target,
            ref=data.ref,
            name=data.name,
            meme_dir=data.meme_dir,
            proxy=proxy,
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
        + (f" via proxy {state.proxy}" if state.proxy else "")
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


@router.patch("/{identifier:path}", response_model=RepoInfo)
async def update_repo_settings(
    identifier: str, data: RepoSettingsRequest, _: str = Depends(require_admin)
):
    """修改仓库的加速源或显示名称；``apply=true`` 时立即用新加速源重新拉取。"""
    state = repo_manager.get_repo(identifier)
    if not state:
        raise ApiError(
            ErrorCode.REPO_NOT_FOUND, f"仓库不存在：{identifier}", status_code=404
        )

    if data.proxy is not None:
        try:
            state = repo_manager.set_proxy(state.identifier, data.proxy)
        except ValueError as e:
            raise ApiError(
                ErrorCode.VALIDATION_ERROR,
                str(e),
                status_code=400,
                context={"proxy": data.proxy},
            )
        logger.info(
            f"Repo {state.identifier} proxy set to {state.proxy or '(跟随全局默认)'}"
        )

    if data.name is not None and data.name.strip():
        state.name = data.name.strip()
        repo_manager.save(state)

    if data.apply and data.proxy is not None:
        try:
            state, _changes = await repo_manager.update(state.identifier)
        except Exception as e:  # noqa: BLE001 - 网络异常统一转成规范错误
            logger.opt(exception=e).error(f"Failed to update repo {identifier}")
            raise ApiError(
                ErrorCode.REPO_FETCH_FAILED,
                f"按新加速源重新拉取失败：{e}",
                status_code=502,
            )

    return _info(state)


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
