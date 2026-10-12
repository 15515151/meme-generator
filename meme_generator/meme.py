from dataclasses import dataclass, field
from datetime import datetime
from io import BytesIO
from pathlib import Path
from typing import Any, Callable, Literal, Optional, TypeVar, Union

from arclet.alconna import ArgFlag, Args, Empty, Option
from arclet.alconna.action import Action
from pil_utils import BuildImage
from pydantic import BaseModel, ValidationError

from .compat import type_validate_python
from .exception import (
    ArgModelMismatch,
    ImageNumberMismatch,
    OpenImageFailed,
    TextNumberMismatch,
    TextOrNameNotEnough,
    TextOverLength,
)

ELLIPSIS = "…"


def _truncate_texts(texts: list[str], offending: str) -> Optional[list[str]]:
    """把超长的那段文本截短并加省略号。

    优先按换行分段截断（保留第一行），否则按字符数减半。返回 ``None`` 表示
    已经无法再截短。
    """
    result = list(texts)
    target = offending
    index = next((i for i, text in enumerate(result) if text == target), None)

    # 报错文本可能只是其中一段，找不到时退而修改最长的一段
    if index is None:
        if not result:
            return None
        index = max(range(len(result)), key=lambda i: len(result[i]))
        target = result[index]

    if "\n" in target:
        shortened = target.split("\n", 1)[0].rstrip()
        if shortened and shortened != target:
            result[index] = shortened + ELLIPSIS
            return result
        # 只有一个换行且首行为空时按字符截断
        target = shortened or target.strip()

    limit = max(len(target) // 2, 1)
    if len(target) <= limit:
        return None
    shortened = target[:limit].rstrip() + ELLIPSIS
    if shortened == result[index]:
        return None
    result[index] = shortened
    return result


from .utils import random_image, random_text


class UserInfo(BaseModel):
    name: str = ""
    gender: Literal["male", "female", "unknown"] = "unknown"


class MemeArgsModel(BaseModel):
    user_infos: list[UserInfo] = []


ArgsModel = TypeVar("ArgsModel", bound=MemeArgsModel)

MemeFunction = Callable[[list[BuildImage], list[str], ArgsModel], BytesIO]


class ParserArg(BaseModel):
    name: str
    value: str
    default: Optional[Any] = None
    flags: Optional[list[ArgFlag]] = None


class ParserOption(BaseModel):
    names: list[str]
    args: Optional[list[ParserArg]] = None
    dest: Optional[str] = None
    default: Optional[Any] = None
    action: Optional[Action] = None
    help_text: Optional[str] = None
    compact: bool = False

    def option(self) -> Option:
        args = Args()
        for arg in self.args or []:
            args.add(
                name=arg.name,
                value=arg.value,
                default=arg.default or Empty,
                flags=arg.flags,
            )

        return Option(
            name="|".join(self.names),
            args=args,
            dest=self.dest,
            default=self.default or Empty,
            action=self.action,
            help_text=self.help_text,
            compact=self.compact,
        )


class CommandShortcut(BaseModel):
    key: str
    args: Optional[list[str]] = None
    humanized: Optional[str] = None


@dataclass
class MemeArgsType:
    args_model: type[MemeArgsModel]
    args_examples: list[MemeArgsModel] = field(default_factory=list)
    parser_options: list[ParserOption] = field(default_factory=list)


@dataclass
class MemeParamsType:
    min_images: int = 0
    max_images: int = 0
    min_texts: int = 0
    max_texts: int = 0
    default_texts: list[str] = field(default_factory=list)
    args_type: Optional[MemeArgsType] = None


@dataclass
class Meme:
    key: str
    function: MemeFunction
    params_type: MemeParamsType
    keywords: list[str] = field(default_factory=list)
    shortcuts: list[CommandShortcut] = field(default_factory=list)
    tags: set[str] = field(default_factory=set)
    date_created: datetime = datetime(2021, 5, 4)
    date_modified: datetime = datetime.now()

    def __call__(
        self,
        *,
        images: Optional[
            Union[list[str], list[Path], list[bytes], list[BytesIO]]
        ] = None,
        texts: Optional[list[str]] = None,
        args: Optional[dict[str, Any]] = None,
    ) -> BytesIO:
        images = images or []
        texts = texts or []
        args = args or {}

        if not (
            self.params_type.min_images <= len(images) <= self.params_type.max_images
        ):
            raise ImageNumberMismatch(
                self.params_type.min_images, self.params_type.max_images
            )

        if not (self.params_type.min_texts <= len(texts) <= self.params_type.max_texts):
            raise TextNumberMismatch(
                self.params_type.min_texts, self.params_type.max_texts
            )

        if args_type := self.params_type.args_type:
            args_model = args_type.args_model
        else:
            args_model = MemeArgsModel

        try:
            model = type_validate_python(args_model, args)
        except ValidationError as e:
            raise ArgModelMismatch(str(e))

        imgs: list[BuildImage] = []
        try:
            for image in images:
                if isinstance(image, bytes):
                    image = BytesIO(image)
                imgs.append(BuildImage.open(image))
        except Exception as e:
            raise OpenImageFailed(str(e))

        return self.function(imgs, texts, model)

    def generate_preview(self, *, args: Optional[dict[str, Any]] = None) -> BytesIO:
        args = args or {}
        default_images = [random_image() for _ in range(self.params_type.min_images)]
        default_texts = (
            self.params_type.default_texts.copy()
            if (
                self.params_type.min_texts
                <= len(self.params_type.default_texts)
                <= self.params_type.max_texts
            )
            else [random_text() for _ in range(self.params_type.min_texts)]
        )

        # 预览最多重试的次数，避免极端情况下无限循环
        remaining = 12
        # 截断也救不回来时（例如文本区域太窄，连单个汉字都放不下）用的占位文本。
        # 预览只用于管理面板展示，出图比文案准确更重要。
        ascii_fallbacks = ["preview", "abc", "a"]

        def _generate_preview(images: list[bytes], texts: list[str]):
            nonlocal remaining
            try:
                return self.__call__(images=images, texts=texts, args=args)
            except TextOrNameNotEnough:
                texts.append(random_text())
                return _generate_preview(images, texts)
            except TextOverLength as e:
                # 有些表情自带的默认文本超过它自身的长度限制（例如把渲染高度
                # 限制在固定像素的表情），这里逐次截断并加省略号重试，让预览
                # 始终能出图，而不是把这类表情永久标记为“预览失败”。
                remaining -= 1
                if remaining <= 0:
                    raise
                shortened = _truncate_texts(texts, e.text)
                if shortened is not None:
                    return _generate_preview(images, shortened)
                # 截断已到极限（只剩一个字还是过长），改用短 ASCII 占位
                if ascii_fallbacks:
                    count = max(len(texts), self.params_type.min_texts, 1)
                    placeholder = ascii_fallbacks.pop(0)
                    return _generate_preview(images, [placeholder] * count)
                raise

        return _generate_preview(default_images, default_texts)
