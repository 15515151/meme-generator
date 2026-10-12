"""统一的 API 错误响应。

所有错误（包括 FastAPI 自身抛出的 404/422）都会经由这里注册的异常处理器
转换成统一结构，方便调用方按 ``error.code`` 分支处理：

    {
      "error": {
        "code": "NO_SUCH_MEME",
        "message": "表情“xxx”不存在",
        "status_code": 531,
        "context": {"meme_key": "xxx"}
      },
      "detail": "表情“xxx”不存在"
    }

``detail`` 字段与历史响应保持一致，已有的下游调用无需改动。
"""

from typing import Any, Optional

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from .exception import MemeGeneratorException
from .log import logger

ERROR_CODE_BY_STATUS: dict[int, str] = {
    400: "BAD_REQUEST",
    401: "UNAUTHORIZED",
    403: "FORBIDDEN",
    404: "NOT_FOUND",
    405: "METHOD_NOT_ALLOWED",
    409: "CONFLICT",
    413: "PAYLOAD_TOO_LARGE",
    422: "VALIDATION_ERROR",
    429: "TOO_MANY_REQUESTS",
    500: "INTERNAL_ERROR",
    503: "SERVICE_UNAVAILABLE",
}


class ErrorCode:
    """业务错误码，会出现在响应的 ``error.code`` 字段中。"""

    NOT_FOUND = "NOT_FOUND"
    VALIDATION_ERROR = "VALIDATION_ERROR"
    INTERNAL_ERROR = "INTERNAL_ERROR"
    HTTP_ERROR = "HTTP_ERROR"

    NO_SUCH_MEME = "NO_SUCH_MEME"
    TEXT_OVER_LENGTH = "TEXT_OVER_LENGTH"
    OPEN_IMAGE_FAILED = "OPEN_IMAGE_FAILED"
    IMAGE_NUMBER_MISMATCH = "IMAGE_NUMBER_MISMATCH"
    TEXT_NUMBER_MISMATCH = "TEXT_NUMBER_MISMATCH"
    TEXT_OR_NAME_NOT_ENOUGH = "TEXT_OR_NAME_NOT_ENOUGH"
    ARG_PARSER_MISMATCH = "ARG_PARSER_MISMATCH"
    ARG_MODEL_MISMATCH = "ARG_MODEL_MISMATCH"
    MEME_FEEDBACK = "MEME_FEEDBACK"
    MEME_GENERATOR_ERROR = "MEME_GENERATOR_ERROR"

    MEME_DISABLED = "MEME_DISABLED"
    ADMIN_NOT_INITIALIZED = "ADMIN_NOT_INITIALIZED"
    ADMIN_ALREADY_INITIALIZED = "ADMIN_ALREADY_INITIALIZED"
    ADMIN_PASSWORD_INCORRECT = "ADMIN_PASSWORD_INCORRECT"
    ADMIN_PASSWORD_TOO_WEAK = "ADMIN_PASSWORD_TOO_WEAK"
    UNAUTHORIZED = "UNAUTHORIZED"
    TOKEN_INVALID = "TOKEN_INVALID"
    TOKEN_EXPIRED = "TOKEN_EXPIRED"

    REPO_NOT_FOUND = "REPO_NOT_FOUND"
    REPO_ALREADY_EXISTS = "REPO_ALREADY_EXISTS"
    REPO_INVALID = "REPO_INVALID"
    REPO_FETCH_FAILED = "REPO_FETCH_FAILED"
    REPO_INSTALL_FAILED = "REPO_INSTALL_FAILED"


def error_payload(
    code: str,
    message: str,
    status_code: int,
    context: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    error: dict[str, Any] = {
        "code": code,
        "message": message,
        "status_code": status_code,
    }
    if context:
        error["context"] = context
    return {"error": error, "detail": message}


class ApiError(Exception):
    """业务代码里主动抛出的 API 错误。"""

    def __init__(
        self,
        code: str,
        message: str,
        status_code: int = 400,
        context: Optional[dict[str, Any]] = None,
    ):
        self.code = code
        self.message = message
        self.status_code = status_code
        self.context = context or {}
        super().__init__(message)


def register_exception_handlers(api: FastAPI) -> None:
    @api.exception_handler(ApiError)
    async def _api_error(_: Request, exc: ApiError):
        return JSONResponse(
            status_code=exc.status_code,
            content=error_payload(exc.code, exc.message, exc.status_code, exc.context),
        )

    @api.exception_handler(MemeGeneratorException)
    async def _meme_error(_: Request, exc: MemeGeneratorException):
        return JSONResponse(
            status_code=exc.status_code,
            content=error_payload(
                exc.error_code,
                exc.message,
                exc.status_code,
                exc.context,
            ),
        )

    @api.exception_handler(StarletteHTTPException)
    async def _http_error(_: Request, exc: StarletteHTTPException):
        detail = exc.detail
        if isinstance(detail, dict):
            code = str(
                detail.get("code")
                or ERROR_CODE_BY_STATUS.get(exc.status_code, ErrorCode.HTTP_ERROR)
            )
            message = str(detail.get("message") or detail)
            context = detail.get("context")
        else:
            code = ERROR_CODE_BY_STATUS.get(exc.status_code, ErrorCode.HTTP_ERROR)
            message = str(detail)
            context = None
        return JSONResponse(
            status_code=exc.status_code,
            content=error_payload(code, message, exc.status_code, context),
        )

    @api.exception_handler(RequestValidationError)
    async def _validation_error(_: Request, exc: RequestValidationError):
        errors = []
        for item in exc.errors():
            errors.append(
                {
                    "loc": [str(part) for part in item.get("loc", [])],
                    "msg": str(item.get("msg", "")),
                    "type": str(item.get("type", "")),
                }
            )
        message = errors[0]["msg"] if errors else "请求参数校验失败"
        return JSONResponse(
            status_code=422,
            content=error_payload(
                ErrorCode.VALIDATION_ERROR, message, 422, {"errors": errors}
            ),
        )

    @api.exception_handler(Exception)
    async def _unhandled(_: Request, exc: Exception):
        logger.opt(exception=exc).error("Unhandled error while serving request")
        return JSONResponse(
            status_code=500,
            content=error_payload(ErrorCode.INTERNAL_ERROR, "服务器内部错误", 500),
        )
