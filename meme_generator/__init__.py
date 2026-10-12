from pathlib import Path

from meme_generator.config import meme_config as config
from meme_generator.manager import add_meme as add_meme
from meme_generator.manager import get_all_memes as get_all_memes
from meme_generator.manager import get_disabled_meme_keys as get_disabled_meme_keys
from meme_generator.manager import get_meme as get_meme
from meme_generator.manager import get_meme_keys as get_meme_keys
from meme_generator.manager import get_memes as get_memes
from meme_generator.manager import is_meme_disabled as is_meme_disabled
from meme_generator.manager import load_meme as load_meme
from meme_generator.manager import load_memes as load_memes
from meme_generator.manager import set_meme_disabled as set_meme_disabled
from meme_generator.meme import CommandShortcut as CommandShortcut
from meme_generator.meme import Meme as Meme
from meme_generator.meme import MemeArgsModel as MemeArgsModel
from meme_generator.meme import MemeArgsType as MemeArgsType
from meme_generator.meme import MemeParamsType as MemeParamsType
from meme_generator.meme import ParserArg as ParserArg
from meme_generator.meme import ParserOption as ParserOption
from meme_generator.version import __version__ as __version__


def _load_builtin_memes() -> None:
    memes_dir = Path(__file__).parent / "memes"
    for path in sorted(memes_dir.iterdir(), key=lambda item: item.name):
        if not path.is_dir() or path.name.startswith("_"):
            continue
        if not (path / "__init__.py").is_file():
            continue
        load_meme(f"meme_generator.memes.{path.name}")


if config.meme.load_builtin_memes:
    _load_builtin_memes()
for meme_dir in config.meme.meme_dirs:
    load_memes(meme_dir)


# 已同步的外部仓库在启动时一并加载，顺序放在配置的 meme_dirs 之后，
# 让显式配置的目录优先。
def _load_installed_repos() -> None:
    from meme_generator.repos import repo_manager

    for state in repo_manager.list_repos():
        if not state.enabled:
            continue
        try:
            repo_manager.load_repo_memes(state)
        except Exception as e:  # noqa: BLE001 - 单个仓库失败不应影响启动
            from meme_generator.log import logger

            logger.opt(exception=e).error(
                f"Failed to load memes from repo {state.identifier}"
            )


_load_installed_repos()
