"""管理面板的表情管理接口：列表、搜索、详情、启停、预览。"""

import filetype
from fastapi import APIRouter, Depends, Query, Response
from pydantic import BaseModel

from ..errors import ApiError, ErrorCode
from ..exception import MemeGeneratorException, NoSuchMeme, TextOverLength
from ..log import logger
from ..manager import (
    get_all_memes,
    get_meme,
    get_meme_sources,
    is_meme_disabled,
    set_meme_disabled,
)
from ..utils import random_image, random_text, run_sync
from .deps import require_admin

router = APIRouter(prefix="/admin/memes", tags=["admin-memes"])


class MemeSummary(BaseModel):
    key: str
    keywords: list[str]
    tags: list[str]
    disabled: bool
    source: str
    min_images: int
    max_images: int
    min_texts: int
    max_texts: int
    default_texts: list[str]
    date_created: str
    date_modified: str
    has_preview_assets: bool


class MemeListResponse(BaseModel):
    total: int
    enabled: int
    disabled: int
    items: list[MemeSummary]
    sources: list[str]


class MemeToggleRequest(BaseModel):
    disabled: bool


class MemeToggleResponse(BaseModel):
    key: str
    disabled: bool
    message: str


class BatchToggleRequest(BaseModel):
    keys: list[str]
    disabled: bool


class BatchToggleResponse(BaseModel):
    updated: list[str]
    failed: dict[str, str]


def _summary(meme, source: str) -> MemeSummary:
    params = meme.params_type
    return MemeSummary(
        key=meme.key,
        keywords=list(meme.keywords),
        tags=sorted(meme.tags),
        disabled=is_meme_disabled(meme.key),
        source=source,
        min_images=params.min_images,
        max_images=params.max_images,
        min_texts=params.min_texts,
        max_texts=params.max_texts,
        default_texts=list(params.default_texts),
        date_created=meme.date_created.isoformat(),
        date_modified=meme.date_modified.isoformat(),
        has_preview_assets=params.min_images == 0,
    )


def _match(meme, query: str) -> bool:
    """按 key、关键词、标签模糊匹配。"""
    q = query.strip().lower()
    if not q:
        return True
    haystack = [
        meme.key.lower(),
        *(k.lower() for k in meme.keywords),
        *(t.lower() for t in meme.tags),
        *(s.key.lower() for s in meme.shortcuts),
    ]
    return any(q in item for item in haystack)


@router.get("", response_model=MemeListResponse)
def list_memes(
    q: str = Query(default="", description="搜索关键词，匹配 key / 关键词 / 标签"),
    status: str = Query(
        default="all",
        pattern="^(all|enabled|disabled)$",
        description="按启用状态过滤",
    ),
    source: str = Query(default="", description="按来源过滤，如 builtin 或仓库名"),
    _: str = Depends(require_admin),
):
    sources = get_meme_sources()
    all_memes = sorted(get_all_memes(), key=lambda m: m.key)

    items = []
    for meme in all_memes:
        meme_source = sources.get(meme.key, "builtin")
        if not _match(meme, q):
            continue
        if source and meme_source != source:
            continue
        disabled = is_meme_disabled(meme.key)
        if status == "enabled" and disabled:
            continue
        if status == "disabled" and not disabled:
            continue
        items.append(_summary(meme, meme_source))

    return MemeListResponse(
        total=len(all_memes),
        enabled=sum(1 for m in all_memes if not is_meme_disabled(m.key)),
        disabled=sum(1 for m in all_memes if is_meme_disabled(m.key)),
        items=items,
        sources=sorted(set(sources.values())),
    )


@router.get("/{key}")
def meme_detail(key: str, _: str = Depends(require_admin)):
    try:
        meme = get_meme(key)
    except NoSuchMeme as e:
        raise ApiError(
            ErrorCode.NO_SUCH_MEME, e.message, status_code=404, context=e.context
        )

    params = meme.params_type
    return {
        **_summary(meme, get_meme_sources().get(key, "builtin")).model_dump(),
        "params_type": {
            "min_images": params.min_images,
            "max_images": params.max_images,
            "min_texts": params.min_texts,
            "max_texts": params.max_texts,
            "default_texts": list(params.default_texts),
            "has_args": params.args_type is not None,
        },
        "shortcuts": [
            {"key": s.key, "args": s.args, "humanized": s.humanized}
            for s in meme.shortcuts
        ],
    }


@router.post("/{key}/toggle", response_model=MemeToggleResponse)
def toggle_meme(key: str, data: MemeToggleRequest, _: str = Depends(require_admin)):
    """启用/禁用一个表情。禁用后它仍然存在，只是不再出现在对外接口里。"""
    try:
        set_meme_disabled(key, data.disabled)
    except NoSuchMeme as e:
        raise ApiError(
            ErrorCode.NO_SUCH_MEME, e.message, status_code=404, context=e.context
        )

    action = "禁用" if data.disabled else "启用"
    logger.info(
        f"Meme '{key}' {'disabled' if data.disabled else 'enabled'} via admin panel"
    )
    return MemeToggleResponse(
        key=key, disabled=data.disabled, message=f"已{action}表情“{key}”"
    )


@router.post("/batch-toggle", response_model=BatchToggleResponse)
def batch_toggle(data: BatchToggleRequest, _: str = Depends(require_admin)):
    updated: list[str] = []
    failed: dict[str, str] = {}
    for key in data.keys:
        try:
            set_meme_disabled(key, data.disabled)
            updated.append(key)
        except NoSuchMeme:
            failed[key] = "表情不存在"
    return BatchToggleResponse(updated=updated, failed=failed)


@router.get("/{key}/preview")
async def preview_meme(
    key: str,
    texts: str = Query(default="", description="用逗号分隔的文本，留空用默认文本"),
    _: str = Depends(require_admin),
):
    """生成预览图。禁用状态也能预览，方便决定是否重新启用。"""
    try:
        meme = get_meme(key)
    except NoSuchMeme as e:
        raise ApiError(
            ErrorCode.NO_SUCH_MEME, e.message, status_code=404, context=e.context
        )

    params = meme.params_type
    text_list = [t for t in texts.split(",") if t] if texts else None
    if text_list is None:
        text_list = (
            params.default_texts.copy()
            if params.default_texts
            else [random_text() for _ in range(params.min_texts)]
        )
    elif len(text_list) < params.min_texts:
        raise ApiError(
            ErrorCode.TEXT_NUMBER_MISMATCH,
            f"文本数量不符，至少需要 {params.min_texts} 段文本",
            status_code=400,
            context={"min_texts": params.min_texts, "provided": len(text_list)},
        )

    images = [random_image() for _ in range(params.min_images)]
    try:
        result = await run_sync(meme)(images=images, texts=text_list)
    except TextOverLength:
        # 有些表情自带的默认文本超出它自己的长度限制，退回占位文本再试一次，
        # 否则管理面板里这些表情永远显示预览失败。
        try:
            fallback = ["示例文本" for _ in range(max(params.min_texts, 1))]
            result = await run_sync(meme)(images=images, texts=fallback)
        except Exception as e:  # noqa: BLE001
            logger.opt(exception=e).warning(f"Preview generation failed for '{key}'")
            raise ApiError(
                ErrorCode.MEME_GENERATOR_ERROR, f"预览生成失败：{e}", status_code=500
            ) from e
    except MemeGeneratorException as e:
        raise ApiError(
            e.error_code, e.message, status_code=e.status_code, context=e.context
        )
    except Exception as e:  # noqa: BLE001 - 预览失败要转成规范错误
        logger.opt(exception=e).warning(f"Preview generation failed for '{key}'")
        raise ApiError(
            ErrorCode.MEME_GENERATOR_ERROR,
            f"预览生成失败：{e}",
            status_code=500,
        )

    content = result.getvalue()
    media_type = str(filetype.guess_mime(content)) or "image/png"
    return Response(
        content=content,
        media_type=media_type,
        headers={"Cache-Control": "no-store"},
    )


@router.get("/{key}/assets")
def meme_assets(key: str, _: str = Depends(require_admin)):
    """列出表情目录下的资源文件，便于确认仓库同步是否完整。"""
    from ..repos import list_meme_files

    try:
        get_meme(key)
    except NoSuchMeme as e:
        raise ApiError(
            ErrorCode.NO_SUCH_MEME, e.message, status_code=404, context=e.context
        )

    files = list_meme_files(key)
    return {"key": key, "files": files, "count": len(files)}
