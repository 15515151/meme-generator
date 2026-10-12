"""面向下游的公开接口。

管理接口挂在 ``/api/admin/*`` 下需要登录；这里的是只读的公开信息，
方便下游程序（比如另一个部署、机器人插件）查询表情清单与更新情况。
"""

from typing import Any

from fastapi import APIRouter, Query

from ..log import logger
from ..manager import (
    get_all_memes,
    get_disabled_meme_keys,
    get_meme_sources,
    is_meme_disabled,
)
from ..repos import BUILTIN_SOURCE, repo_manager
from ..version import __version__

router = APIRouter(prefix="/api", tags=["public"])


@router.get("/version")
def version():
    return {"version": __version__}


@router.get("/memes")
def list_memes(
    q: str = Query(default="", description="按 key / 关键词 / 标签搜索"),
    include_disabled: bool = Query(default=False, description="是否包含已禁用表情"),
    source: str = Query(default="", description="按来源过滤"),
):
    """表情清单，含参数约束与来源，供下游同步使用。"""
    sources = get_meme_sources()
    query = q.strip().lower()
    disabled_keys = set(get_disabled_meme_keys())

    items: list[dict[str, Any]] = []
    for meme in sorted(get_all_memes(), key=lambda m: m.key):
        source_name = sources.get(meme.key, BUILTIN_SOURCE)
        if not include_disabled and meme.key in disabled_keys:
            continue
        if source and source_name != source:
            continue
        if query:
            haystack = [
                meme.key.lower(),
                *(k.lower() for k in meme.keywords),
                *(t.lower() for t in meme.tags),
            ]
            if not any(query in item for item in haystack):
                continue

        params = meme.params_type
        items.append(
            {
                "key": meme.key,
                "keywords": list(meme.keywords),
                "tags": sorted(meme.tags),
                "source": source_name,
                "disabled": meme.key in disabled_keys,
                "params_type": {
                    "min_images": params.min_images,
                    "max_images": params.max_images,
                    "min_texts": params.min_texts,
                    "max_texts": params.max_texts,
                    "default_texts": list(params.default_texts),
                    "has_args": params.args_type is not None,
                },
                "date_created": meme.date_created.isoformat(),
                "date_modified": meme.date_modified.isoformat(),
            }
        )

    return {
        "version": __version__,
        "total": len(items),
        "items": items,
    }


@router.get("/repos")
def list_repos():
    """已注册的外部仓库及其表情数量。"""
    repos = []
    for state in repo_manager.list_repos():
        repos.append(
            {
                "identifier": state.identifier,
                "url": state.url,
                "ref": state.ref,
                "enabled": state.enabled,
                "meme_count": len(state.meme_keys),
                "meme_keys": state.meme_keys,
                "updated_at": state.updated_at,
            }
        )
    return {"total": len(repos), "items": repos}


@router.get("/updates")
async def check_updates(
    identifier: str = Query(
        default="", description="仓库标识；留空则检查全部已注册仓库"
    ),
    include_content: bool = Query(
        default=False, description="是否返回变更文件的内容，便于下游直接取用"
    ),
):
    """公开的更新查询：哪些表情有更新、更新了哪些文件。

    ``include_content=true`` 时会一并返回变更文件的新内容（以及被覆盖前的旧
    内容），下游可以据此把新表情直接落盘。
    """
    states = repo_manager.list_repos()
    if identifier:
        states = [
            s for s in states if s.identifier == identifier or s.url == identifier
        ]
        if not states:
            return {
                "total": 0,
                "updated": 0,
                "error": f"仓库不存在：{identifier}",
                "results": [],
            }

    results = []
    for state in states:
        try:
            result = await repo_manager.check_update(state.identifier)
        except Exception as e:  # noqa: BLE001 - 单个仓库失败不影响整体
            logger.opt(exception=e).warning(
                f"Failed to check updates for {state.identifier}"
            )
            results.append(
                {
                    "identifier": state.identifier,
                    "has_update": False,
                    "error": str(e),
                    "changes": {
                        "added": [],
                        "modified": [],
                        "removed": [],
                        "added_memes": [],
                        "modified_memes": [],
                        "removed_memes": [],
                    },
                    "files": [],
                }
            )
            continue

        if not include_content:
            result["files"] = [
                {k: v for k, v in f.items() if k not in ("content", "previous_content")}
                for f in result["files"]
            ]
        results.append(result)

    return {
        "total": len(results),
        "updated": sum(1 for r in results if r.get("has_update")),
        "results": results,
    }


@router.get("/updates/{meme_key}")
async def meme_update_detail(
    meme_key: str, include_content: bool = Query(default=True)
):
    """查询单个表情在所有已注册仓库中的更新情况。"""
    items = []
    for state in repo_manager.list_repos():
        try:
            result = await repo_manager.check_update(state.identifier)
        except Exception as e:  # noqa: BLE001
            logger.opt(exception=e).warning(
                f"Failed to check updates for {state.identifier}"
            )
            continue

        for file in result["files"]:
            if file.get("meme_key") != meme_key:
                continue
            entry = {
                "identifier": state.identifier,
                "path": file["path"],
                "status": file["status"],
                "kind": file["kind"],
            }
            if include_content:
                entry["content"] = file.get("content")
                entry["previous_content"] = file.get("previous_content")
            items.append(entry)

        if meme_key in result["changes"].get("removed_memes", []):
            items.append(
                {
                    "identifier": state.identifier,
                    "path": None,
                    "status": "removed",
                    "kind": "meme",
                }
            )

    installed = any(m.key == meme_key for m in get_all_memes())
    return {
        "meme_key": meme_key,
        "installed": installed,
        "disabled": is_meme_disabled(meme_key) if installed else False,
        "has_update": any(i["status"] != "removed" for i in items),
        "updates": items,
    }
