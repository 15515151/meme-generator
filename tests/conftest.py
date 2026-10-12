"""测试环境隔离。

必须在导入 meme_generator 之前设置这些环境变量：模块导入时就会读取配置路径并
加载内置表情，之后再改就来不及了。
"""

import os
import shutil
import tempfile
from pathlib import Path

_TMP_ROOT = Path(tempfile.mkdtemp(prefix="meme-generator-tests-"))

os.environ["MEME_GENERATOR_CONFIG_FILE"] = str(_TMP_ROOT / "config" / "config.toml")
os.environ["MEME_GENERATOR_CONFIG_DIR"] = str(_TMP_ROOT / "config")
os.environ["MEME_GENERATOR_DATA_DIR"] = str(_TMP_ROOT / "data")
os.environ["MEME_GENERATOR_CACHE_DIR"] = str(_TMP_ROOT / "cache")

Path(os.environ["MEME_GENERATOR_CONFIG_FILE"]).parent.mkdir(parents=True, exist_ok=True)

import pytest  # noqa: E402


@pytest.fixture
def tmp_root() -> Path:
    return _TMP_ROOT


@pytest.fixture
def data_dir() -> Path:
    return Path(os.environ["MEME_GENERATOR_DATA_DIR"])


@pytest.fixture
def config_file() -> Path:
    return Path(os.environ["MEME_GENERATOR_CONFIG_FILE"])


@pytest.fixture(autouse=True)
def reset_admin_state():
    """每个测试都从「未初始化」开始。

    管理凭据是模块级单例并带内存缓存，不清掉的话测试顺序会互相影响。
    """
    from meme_generator.admin import admin_auth

    admin_file = Path(os.environ["MEME_GENERATOR_DATA_DIR"]) / "admin.json"
    admin_file.unlink(missing_ok=True)
    admin_auth.reload()
    yield
    admin_file.unlink(missing_ok=True)
    admin_auth.reload()


@pytest.fixture(autouse=True)
def reset_repo_state():
    """清掉已注册仓库，避免测试之间残留。"""
    yield
    from meme_generator.repos import repo_manager

    for state in repo_manager.list_repos():
        repo_manager.uninstall(state.identifier)


@pytest.fixture(autouse=True)
def reset_disabled_memes(config_file):
    """清掉表情禁用状态，避免污染对外接口的断言。"""
    yield
    from meme_generator import manager

    manager._disabled_memes.clear()
    config_file.write_text("", encoding="utf-8")


def pytest_sessionfinish(session, exitstatus):  # noqa: ANN001, ARG001
    shutil.rmtree(_TMP_ROOT, ignore_errors=True)
