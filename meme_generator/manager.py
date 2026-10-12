import importlib
import importlib.util
import pkgutil
import sys
from contextvars import ContextVar
from datetime import datetime
from pathlib import Path
from typing import Optional, Union

from .config import meme_config
from .exception import NoSuchMeme
from .log import logger
from .meme import CommandShortcut, Meme, MemeArgsType, MemeFunction, MemeParamsType

BUILTIN_SOURCE = "builtin"
REPO_SOURCE_PREFIX = "repo:"

_memes: dict[str, Meme] = {}

# 记录每个表情由谁加载，便于外部仓库移除时精确卸载其表情。
_meme_sources: dict[str, str] = {}

# 来源名 -> 磁盘目录，卸载时用来清理 sys.modules 中对应的模块。
_source_dirs: dict[str, str] = {}

# 加载外部仓库时临时标记来源，供 add_meme 读取。
_loading_source: ContextVar[str] = ContextVar("loading_source", default=BUILTIN_SOURCE)

# 运行时禁用列表，初始值来自配置文件的 meme_disabled_list。
# 被禁用的表情仍然注册，只是不参与对外接口，这样管理面板才能列出并重新启用它们。
_disabled_memes: set[str] = set(meme_config.meme.meme_disabled_list)


def path_to_module_name(path: Path) -> str:
    rel_path = path.resolve().relative_to(Path.cwd().resolve())
    if rel_path.stem == "__init__":
        return ".".join(rel_path.parts[:-1])
    else:
        return ".".join(rel_path.parts[:-1] + (rel_path.stem,))


def load_meme(module_path: Union[str, Path], source: str = BUILTIN_SOURCE):
    module_name = (
        path_to_module_name(module_path)
        if isinstance(module_path, Path)
        else module_path
    )
    token = _loading_source.set(source)
    try:
        importlib.import_module(module_name)
    except Exception as e:
        logger.opt(colors=True, exception=e).error(f"Failed to import {module_path}!")
    finally:
        _loading_source.reset(token)


def load_memes(dir_path: Union[str, Path], source: str = BUILTIN_SOURCE):
    if isinstance(dir_path, Path):
        dir_path = str(dir_path.resolve())

    for module_info in pkgutil.iter_modules([dir_path]):
        if module_info.name.startswith("_"):
            continue
        if not (
            module_spec := module_info.module_finder.find_spec(module_info.name, None)
        ):
            continue
        if not (module_path := module_spec.origin):
            continue
        if not (module_loader := module_spec.loader):
            continue
        token = _loading_source.set(source)
        try:
            module = importlib.util.module_from_spec(module_spec)
            module_loader.exec_module(module)
        except Exception as e:
            logger.opt(colors=True, exception=e).error(
                f"Failed to import {module_path}!"
            )
        finally:
            _loading_source.reset(token)


def add_meme(
    key: str,
    function: MemeFunction,
    *,
    min_images: int = 0,
    max_images: int = 0,
    min_texts: int = 0,
    max_texts: int = 0,
    default_texts: Optional[list[str]] = None,
    args_type: Optional[MemeArgsType] = None,
    keywords: Optional[list[str]] = None,
    shortcuts: Optional[list[CommandShortcut]] = None,
    tags: Optional[set[str]] = None,
    date_created: datetime = datetime(2021, 5, 4),
    date_modified: datetime = datetime.now(),
):
    if key in _memes:
        logger.warning(f'Meme with key "{key}" already exists!')
        return

    meme = Meme(
        key,
        function,
        MemeParamsType(
            min_images,
            max_images,
            min_texts,
            max_texts,
            list(default_texts or []),
            args_type,
        ),
        keywords=list(keywords or []),
        shortcuts=list(shortcuts or []),
        tags=set(tags or set()),
        date_created=date_created,
        date_modified=date_modified,
    )

    _memes[key] = meme
    _meme_sources[key] = _loading_source.get()

    if key in _disabled_memes:
        logger.debug(f'The key "{key}" is disabled.')


def get_meme(key: str) -> Meme:
    if key not in _memes:
        raise NoSuchMeme(key)
    return _memes[key]


def get_memes() -> list[Meme]:
    """已启用的表情，供生成、列表渲染等对外接口使用。"""
    return [meme for key, meme in _memes.items() if key not in _disabled_memes]


def get_all_memes() -> list[Meme]:
    """所有已注册的表情，包含被禁用的，供管理接口使用。"""
    return list(_memes.values())


def get_meme_keys() -> list[str]:
    return [meme.key for meme in get_memes()]


def is_meme_disabled(key: str) -> bool:
    return key in _disabled_memes


def get_disabled_meme_keys() -> list[str]:
    return sorted(_disabled_memes)


def get_meme_source(key: str) -> str:
    return _meme_sources.get(key, BUILTIN_SOURCE)


def get_meme_sources() -> dict[str, str]:
    return dict(_meme_sources)


def set_meme_disabled(key: str, disabled: bool, persist: bool = True) -> None:
    """启用/禁用一个表情，默认同时写回配置文件。"""
    if key not in _memes:
        raise NoSuchMeme(key)

    if disabled:
        _disabled_memes.add(key)
    else:
        _disabled_memes.discard(key)

    if persist:
        meme_config.meme.meme_disabled_list = sorted(_disabled_memes)
        meme_config.dump()


def register_source_dir(source: str, directory: Union[str, Path]) -> None:
    """登记来源名与它对应的磁盘目录，卸载时据此清理模块缓存。"""
    _source_dirs[source] = str(directory)


def get_source_dir(source: str) -> Optional[str]:
    return _source_dirs.get(source)


def unload_memes_by_source(source: str) -> list[str]:
    """卸载某个外部仓库加载的全部表情，返回被移除的 key。"""
    keys = [key for key, src in _meme_sources.items() if src == source]
    for key in keys:
        _memes.pop(key, None)
        _meme_sources.pop(key, None)
        _disabled_memes.discard(key)

    # 外部仓库以文件路径导入，需要清掉 sys.modules 里的缓存，
    # 否则重新安装同名表情时会拿到旧模块。
    source_path = _source_dirs.get(source, "")
    if source_path:
        for module_name, module in list(sys.modules.items()):
            module_file = getattr(module, "__file__", None)
            if module_file and source_path in str(module_file):
                sys.modules.pop(module_name, None)

    if keys:
        logger.info(
            f"Unloaded {len(keys)} meme(s) from {source}: {', '.join(sorted(keys))}"
        )
    return keys
