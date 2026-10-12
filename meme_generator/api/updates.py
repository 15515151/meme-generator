"""外部表情更新检查接口。

除了管理面板使用，这个接口也面向下游：下游可以拉取「有哪些表情更新了、
更新了哪些文件、新代码长什么样」，据此把新表情或变更同步到自己的部署里。
"""

from typing import Any, Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from ..errors import ApiError, ErrorCode
from ..log import logger
from ..manager import get_all_memes, get_meme_sources, is_meme_disabled
from ..repos import BUILTIN_SOURCE, repo_manager
from .deps import optional_admin, require_admin

router = APIRouter(prefix="/admin/updates", tags=["admin-updates"])


class FileChange(BaseModel):
    path: str
    status: str
    meme_key: Optional[str] = None
    kind: str
    content: Optional[str] = None
    previous_content: Optional[str] = None
    content_error: Optional[str] = None


class RepoUpdateResult(BaseModel):
    identifier: str
    has_update: bool
    changes: dict[str, Any]
    files: list[FileChange] = []
    error: Optional[str] = None


@router.get("/check", response_model=RepoUpdateResult, include_in_schema=False)
async def check_one(
    identifier: str = Query(description="仓库标识，如 owner/repo"),
    include_content: bool = Query(default=True, description="是否返回文件内容"),
    _: str = Depends(require_admin),
):
    """检查单个仓库的更新情况。"""
    if not repo_manager.get_repo(identifier):
        raise ApiError(
            ErrorCode.REPO_NOT_FOUND, f"仓库不存在：{identifier}", status_code=404
        )
    try:
        result = await repo_manager.check_update(identifier)
    except Exception as e:  # noqa: BLE001
        logger.opt(exception=e).error(f"Failed to check update for {identifier}")
        raise ApiError(
            ErrorCode.REPO_FETCH_FAILED, f"检查更新失败：{e}", status_code=502
        )

    if not include_content:
        result["files"] = [
            {k: v for k, v in f.items() if k not in ("content", "previous_content")}
            for f in result["files"]
        ]
    return result


@router.get("/check-all")
async def check_all(_: str = Depends(require_admin)):
    """检查所有已注册仓库的更新。"""
    results = await repo_manager.check_all_updates()
    return {
        "total": len(results),
        "updated": sum(1 for r in results if r.get("has_update")),
        "results": results,
    }


@router.get("/memes")
async def meme_updates(
    identifiers: str = Query(
        default="",
        description="逗号分隔的仓库标识；留空时检查全部已注册仓库",
    ),
    _: Optional[bool] = Depends(optional_admin),
):
    """按表情汇总的更新列表，便于下游按 key 增量同步。

    响应里的每個表情都会列出它是新增还是变更、涉及哪些文件、以及代码内容，
    下游据此可以只拉取变化的表情，而不是整个仓库。
    """
    wanted = {i.strip() for i in identifiers.split(",") if i.strip()}
    states = [
        s
        for s in repo_manager.list_repos()
        if not wanted or s.identifier in wanted or s.url in wanted
    ]

    if not states:
        return {"total": 0, "memes_updated": 0, "items": []}

    known = {
        m.key: get_meme_sources().get(m.key, BUILTIN_SOURCE) for m in get_all_memes()
    }
    items = []
    for state in states:
        try:
            result = await repo_manager.check_update(state.identifier)
        except Exception as e:  # noqa: BLE001
            logger.opt(exception=e).warning(
                f"Failed to check memes for repo {state.identifier}"
            )
            continue

        grouped: dict[str, dict[str, Any]] = {}
        for file in result["files"]:
            key = file.get("meme_key")
            if not key:
                continue
            entry = grouped.setdefault(
                key,
                {
                    "meme_key": key,
                    "status": "new" if file["status"] == "added" else "updated",
                    "repo": state.identifier,
                    "files": [],
                    "installed": key in known,
                    "disabled": is_meme_disabled(key) if key in known else False,
                },
            )
            entry["files"].append(
                {
                    "path": file["path"],
                    "status": file["status"],
                    "kind": file["kind"],
                    "content": file.get("content"),
                    "previous_content": file.get("previous_content"),
                }
            )
            # 同一表情只要有一个新文件就按新增处理
            if file["status"] == "added":
                entry["status"] = "new"

        for key, entry in sorted(grouped.items()):
            entry["file_count"] = len(entry["files"])
            entry["code_files"] = sum(1 for f in entry["files"] if f["kind"] == "code")
            items.append(entry)

        if result.get("removed"):
            for key in result["changes"].get("removed_memes", []):
                items.append(
                    {
                        "meme_key": key,
                        "status": "removed",
                        "repo": state.identifier,
                        "files": [],
                        "file_count": 0,
                        "code_files": 0,
                        "installed": key in known,
                        "disabled": is_meme_disabled(key) if key in known else False,
                    }
                )

    return {
        "total": len(items),
        "memes_updated": len([i for i in items if i["status"] != "removed"]),
        "items": items,
    }
