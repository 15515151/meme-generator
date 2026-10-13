import os
from pathlib import Path
from typing import Optional, Union

import toml
from pydantic import BaseModel, Field

from .compat import model_dump, type_validate_python
from .dirs import get_config_file


def get_config_file_path() -> Path:
    if path := os.getenv("MEME_GENERATOR_CONFIG_FILE"):
        return Path(path).expanduser()
    return get_config_file("config.toml")


config_file_path = get_config_file_path()

DEFAULT_RESOURCE_URLS = [
    "https://raw.githubusercontent.com/MemeCrafters/meme-generator/",
    "https://mirror.ghproxy.com/https://raw.githubusercontent.com/MemeCrafters/meme-generator/",
    "https://cdn.jsdelivr.net/gh/MemeCrafters/meme-generator@",
    "https://fastly.jsdelivr.net/gh/MemeCrafters/meme-generator@",
    "https://raw.gitmirror.com/MemeCrafters/meme-generator/",
]


# 内置的常用 GitHub 加速源，管理面板里可以直接点选。都是「前缀式」加速：
# 加速源 + 原始地址，例如 https://ghfast.top/https://github.com/owner/repo 。
# 想用自己的加速源（自建或别处的），在管理面板里直接填即可：只写进本机配置，
# 不会进代码仓库，也能随时换掉。
DEFAULT_PROXY_PRESETS = [
    "https://ghfast.top/",
    "https://gh-proxy.com/",
    "https://ghproxy.net/",
    "https://hub.gitmirror.com/",
    "https://gh.ddlc.top/",
    "https://ghproxy.cc/",
]


class MemeConfig(BaseModel):
    load_builtin_memes: bool = True
    meme_dirs: list[Path] = Field(default_factory=list)
    meme_disabled_list: list[str] = Field(default_factory=list)


class ResourceConfig(BaseModel):
    resource_url: Optional[str] = None
    resource_urls: list[str] = Field(
        default_factory=lambda: DEFAULT_RESOURCE_URLS.copy()
    )


class RepoConfig(BaseModel):
    """外部仓库（GitHub）相关的配置。"""

    # 全局 GitHub 加速源，形如 ``https://ghfast.top/``。它是纯粹的地址前缀，
    # 拼接后得到 ``https://ghfast.top/https://github.com/owner/repo``。
    # 可以用环境变量 GITHUB_PROXY 提供初始值；单个仓库还能在管理面板里单独覆盖。
    github_proxy: str = Field(default_factory=lambda: os.getenv("GITHUB_PROXY", ""))
    # 管理面板里可选用的加速源；想换成自己的，改这里即可。
    proxy_presets: list[str] = Field(
        default_factory=lambda: DEFAULT_PROXY_PRESETS.copy()
    )


class GifConfig(BaseModel):
    gif_max_size: float = 10
    gif_max_frames: int = 100


class TranslatorConfig(BaseModel):
    baidu_trans_appid: str = ""
    baidu_trans_apikey: str = ""


class ServerConfig(BaseModel):
    host: str = "127.0.0.1"
    port: int = 2233
    # 对外访问地址，用于在 API 文档里生成可直接复制的请求示例。
    # 留空时前端会退回当前浏览器地址。
    api_domain: str = ""


class LogConfig(BaseModel):
    log_level: Union[int, str] = "INFO"


class Config(BaseModel):
    meme: MemeConfig = Field(default_factory=MemeConfig)
    resource: ResourceConfig = Field(default_factory=ResourceConfig)
    repo: RepoConfig = Field(default_factory=RepoConfig)
    gif: GifConfig = Field(default_factory=GifConfig)
    translate: TranslatorConfig = Field(default_factory=TranslatorConfig)
    server: ServerConfig = Field(default_factory=ServerConfig)
    log: LogConfig = Field(default_factory=LogConfig)

    @classmethod
    def load(cls) -> "Config":
        return type_validate_python(cls, toml.load(config_file_path))

    def dump(self):
        config_file_path.parent.mkdir(parents=True, exist_ok=True)
        with open(config_file_path, "w", encoding="utf-8") as f:
            toml.dump(model_dump(self), f)


if not config_file_path.exists():
    config_file_path.parent.mkdir(parents=True, exist_ok=True)
    meme_config = Config()
    config_file_path.write_text("", encoding="utf8")
else:
    meme_config = Config.load()
