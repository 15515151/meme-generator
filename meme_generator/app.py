import asyncio
import json
from contextlib import asynccontextmanager, suppress
from datetime import datetime
from pathlib import Path
from typing import Any, Literal, Optional

import filetype
from fastapi import FastAPI, File, Form, Response, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, ValidationError

from meme_generator.compat import model_dump, model_json_schema, type_validate_python
from meme_generator.config import meme_config
from meme_generator.errors import (
    ApiError,
    ErrorCode,
    error_payload,
    register_exception_handlers,
)
from meme_generator.exception import (
    MemeGeneratorException,
    NoSuchMeme,
)
from meme_generator.log import LOGGING_CONFIG, setup_logger
from meme_generator.manager import (
    get_meme,
    get_meme_keys,
    get_memes,
    is_meme_disabled,
)
from meme_generator.meme import (
    CommandShortcut,
    Meme,
    MemeArgsModel,
    ParserOption,
)
from meme_generator.utils import MemeProperties, render_meme_list, run_sync
from meme_generator.version import __version__

WEB_DIST_DIR = Path(__file__).parent / "web_dist"


class MemeArgsResponse(BaseModel):
    args_model: dict[str, Any]
    args_examples: list[dict[str, Any]]
    parser_options: list[ParserOption]


class MemeParamsResponse(BaseModel):
    min_images: int
    max_images: int
    min_texts: int
    max_texts: int
    default_texts: list[str]
    args_type: Optional[MemeArgsResponse] = None


class MemeInfoResponse(BaseModel):
    key: str
    params_type: MemeParamsResponse
    keywords: list[str]
    shortcuts: list[CommandShortcut]
    tags: set[str]
    date_created: datetime
    date_modified: datetime


def _ensure_meme_enabled(key: str) -> Meme:
    """取表情并确认它未被管理员禁用。"""
    meme = get_meme(key)
    if is_meme_disabled(key):
        raise ApiError(
            ErrorCode.MEME_DISABLED,
            f"表情“{key}”已被禁用",
            status_code=403,
            context={"meme_key": key},
        )
    return meme


async def _generate_meme(
    key: str,
    images: Optional[list[UploadFile]],
    texts: Optional[list[str]],
    args: Optional[str] = None,
):
    try:
        meme = _ensure_meme_enabled(key)
    except NoSuchMeme as e:
        raise ApiError(
            ErrorCode.NO_SUCH_MEME,
            e.message,
            status_code=e.status_code,
            context=e.context,
        )

    imgs: list[bytes] = []
    for image in images or []:
        imgs.append(await image.read())

    if texts:
        text_list = [text for text in texts if text]
    else:
        text_list = list(meme.params_type.default_texts)

    args_model = (
        meme.params_type.args_type.args_model
        if meme.params_type.args_type
        else MemeArgsModel
    )
    if args:
        try:
            model = type_validate_python(args_model, json.loads(args))
        except (ValidationError, ValueError) as e:
            raise ApiError(
                ErrorCode.ARG_MODEL_MISMATCH,
                f"参数模型验证失败（{e}）",
                status_code=552,
            ) from e
    else:
        model = args_model()

    try:
        result = await run_sync(meme)(
            images=imgs, texts=text_list, args=model_dump(model)
        )
    except MemeGeneratorException as e:
        raise ApiError(
            e.error_code, e.message, status_code=e.status_code, context=e.context
        )

    content = result.getvalue()
    media_type = str(filetype.guess_mime(content)) or "text/plain"
    return Response(content=content, media_type=media_type)


class MemeKeyWithProperties(BaseModel):
    meme_key: str
    disabled: bool = False
    labels: list[Literal["new", "hot"]] = Field(default_factory=list)


def default_meme_list() -> list[MemeKeyWithProperties]:
    return [
        MemeKeyWithProperties(meme_key=meme.key)
        for meme in sorted(get_memes(), key=lambda meme: meme.key)
    ]


class RenderMemeListRequest(BaseModel):
    meme_list: list[MemeKeyWithProperties] = Field(default_factory=default_meme_list)
    text_template: str = "{keywords}"
    add_category_icon: bool = True


def register_routes(api: FastAPI) -> None:
    @api.post("/memes/render_list", tags=["memes"])
    def _(params: RenderMemeListRequest = RenderMemeListRequest()):
        try:
            meme_list = [
                (
                    get_meme(p.meme_key),
                    MemeProperties(disabled=p.disabled, labels=p.labels),
                )
                for p in params.meme_list
            ]
        except NoSuchMeme as e:
            raise ApiError(
                ErrorCode.NO_SUCH_MEME,
                e.message,
                status_code=e.status_code,
                context=e.context,
            )

        result = render_meme_list(
            meme_list,
            text_template=params.text_template,
            add_category_icon=params.add_category_icon,
        )
        content = result.getvalue()
        media_type = str(filetype.guess_mime(content)) or "text/plain"
        return Response(content=content, media_type=media_type)

    @api.get("/meme/version", tags=["meta"])
    def _():
        return __version__

    @api.get("/memes/keys", tags=["memes"])
    def _():
        return get_meme_keys()

    @api.get("/memes/{key}/info", tags=["memes"])
    def _(key: str):
        try:
            meme = _ensure_meme_enabled(key)
        except NoSuchMeme as e:
            raise ApiError(
                ErrorCode.NO_SUCH_MEME,
                e.message,
                status_code=e.status_code,
                context=e.context,
            )

        args_type_response = None
        if args_type := meme.params_type.args_type:
            args_model = args_type.args_model
            args_type_response = MemeArgsResponse(
                args_model=model_json_schema(args_model),
                args_examples=[
                    model_dump(example) for example in args_type.args_examples
                ],
                parser_options=args_type.parser_options,
            )

        return MemeInfoResponse(
            key=meme.key,
            params_type=MemeParamsResponse(
                min_images=meme.params_type.min_images,
                max_images=meme.params_type.max_images,
                min_texts=meme.params_type.min_texts,
                max_texts=meme.params_type.max_texts,
                default_texts=meme.params_type.default_texts,
                args_type=args_type_response,
            ),
            keywords=meme.keywords,
            shortcuts=meme.shortcuts,
            tags=meme.tags,
            date_created=meme.date_created,
            date_modified=meme.date_modified,
        )

    @api.get("/memes/{key}/preview", tags=["memes"])
    async def _(key: str):
        try:
            meme = _ensure_meme_enabled(key)
            result = await run_sync(meme.generate_preview)()
        except NoSuchMeme as e:
            raise ApiError(
                ErrorCode.NO_SUCH_MEME,
                e.message,
                status_code=e.status_code,
                context=e.context,
            )
        except MemeGeneratorException as e:
            raise ApiError(
                e.error_code, e.message, status_code=e.status_code, context=e.context
            )

        content = result.getvalue()
        media_type = str(filetype.guess_mime(content)) or "text/plain"
        return Response(content=content, media_type=media_type)

    # 通用生成路由：注册在具体字面量路径之后，运行时新增的表情无需重启即可使用。
    @api.post("/memes/{key}/", tags=["memes"])
    async def _(
        key: str,
        images: Optional[list[UploadFile]] = File(default=None),
        texts: Optional[list[str]] = Form(default=None),
        args: Optional[str] = Form(default=None),
    ):
        return await _generate_meme(key, images, texts, args)


def register_admin_and_public_routes(api: FastAPI) -> None:
    from meme_generator.api import build_admin_router
    from meme_generator.api.public import router as public_router

    api.include_router(build_admin_router())
    api.include_router(public_router)


def register_web_ui(api: FastAPI) -> None:
    """挂载管理面板静态资源。

    前端构建产物放在 ``meme_generator/web_dist``。未构建时给出提示而不是 404，
    方便开发阶段直接跑 API。
    """
    index_file = WEB_DIST_DIR / "index.html"
    if not index_file.is_file():

        @api.get("/", include_in_schema=False)
        def _no_ui():
            return JSONResponse(
                {
                    "message": "管理面板尚未构建，开发模式下请运行前端 dev server",
                    "docs": "/docs",
                    "api": "/api/memes",
                }
            )

        return

    assets_dir = WEB_DIST_DIR / "assets"
    if assets_dir.is_dir():
        api.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

    @api.get("/", include_in_schema=False)
    def _index():
        return FileResponse(index_file)

    @api.get("/{path:path}", include_in_schema=False)
    def _spa(path: str):
        # 静态文件优先，其余路径交给前端路由（单页应用刷新时用）
        candidate = (WEB_DIST_DIR / path).resolve()
        if WEB_DIST_DIR in candidate.parents and candidate.is_file() and path:
            return FileResponse(candidate)
        if path.startswith(("api/", "memes/", "meme/", "docs", "openapi.json")):
            return JSONResponse(
                status_code=404,
                content=error_payload(ErrorCode.NOT_FOUND, "接口不存在", 404),
            )
        return FileResponse(index_file)


REPO_UPDATE_INTERVAL = 5 * 60


async def _auto_update_repos() -> None:
    from meme_generator.log import logger
    from meme_generator.repos import repo_manager

    loop = asyncio.get_running_loop()
    next_check = loop.time() + REPO_UPDATE_INTERVAL
    delay = REPO_UPDATE_INTERVAL
    while True:
        await asyncio.sleep(delay)
        try:
            await repo_manager.update_all_repos()
        except Exception as e:  # noqa: BLE001 - 一轮失败不终止后续检查
            logger.opt(exception=e).warning("Failed to automatically update repos")
        # 以启动时刻为基准；耗时超过周期时跳过错过的时点，不补跑或重叠。
        now = loop.time()
        next_check += REPO_UPDATE_INTERVAL
        if next_check <= now:
            missed = int((now - next_check) // REPO_UPDATE_INTERVAL) + 1
            next_check += missed * REPO_UPDATE_INTERVAL
        delay = next_check - now


@asynccontextmanager
async def lifespan(api: FastAPI):
    task = asyncio.create_task(_auto_update_repos(), name="repo-auto-update")
    api.state.repo_update_task = task
    try:
        yield
    finally:
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task


def create_app() -> FastAPI:
    api = FastAPI(
        lifespan=lifespan,
        title="meme-generator",
        version=__version__,
        description=(
            "表情包生成服务，自带管理面板。\n\n"
            "- `/memes/*`：生成与查询接口\n"
            "- `/api/*`：公开的清单与更新查询接口\n"
            "- `/api/admin/*`：管理面板接口，需要登录"
        ),
    )
    register_exception_handlers(api)
    register_routes(api)
    register_admin_and_public_routes(api)
    register_web_ui(api)
    return api


app = create_app()


def run_server():
    import uvicorn

    uvicorn.run(
        app,
        host=meme_config.server.host,
        port=meme_config.server.port,
        log_config=LOGGING_CONFIG,
    )


if __name__ == "__main__":
    setup_logger()
    run_server()
