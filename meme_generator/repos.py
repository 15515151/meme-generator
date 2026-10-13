"""外部表情仓库管理。

把「拉取额外表情仓库并更新」这件事收进主项目：注册仓库后，可以同步下载它的
表情目录到本地数据目录，再由服务加载。同步状态记录在仓库目录里的
``.meme_repo.json``，据此计算新增/更新/删除，供更新检查 API 使用。

仓库来源支持两种：GitHub 仓库（``owner/repo`` 或完整 URL）与本地绝对路径。

GitHub 访问受限时可以为仓库配置「加速源」：一个纯粹的前缀，套到 GitHub 地址前面，
例如加速源 ``https://ghfast.top/`` 会把
``https://github.com/owner/repo`` 变成
``https://ghfast.top/https://github.com/owner/repo``。
加速源可以在配置文件里全局指定（``[repo] github_proxy``），也可以逐个仓库覆盖，
自建加速源同样只是配置项，不需要改代码。
请求时「加速源优先、直连兜底」：加速源不可用会自动退回直连，不会让同步失败。

表情目录会自动探测（``memes/``、``emoji/`` 或仓库根目录），因为社区仓库的
约定并不统一，例如 ``anyliew/meme_emoji`` 用的是 ``emoji/``。

下载策略按「读多写少」设计：

* 比对差异走 GitHub tree API，一次请求拿到全部文件与 sha，不下载内容。
  大型仓库（400+ 表情、500MB+）用归档比对会非常慢。
* 首次安装或应用更新时下载 GitHub 归档（单个请求，流式落盘），避免逐文件
  请求几百次。
"""

import asyncio
import hashlib
import json
import os
import re
import shutil
import tarfile
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urlparse

import httpx

from .config import meme_config
from .dirs import get_data_dir
from .log import logger
from .manager import (
    BUILTIN_SOURCE,
    load_memes,
    register_source_dir,
    unload_memes_by_source,
)

STATE_FILE_NAME = ".meme_repo.json"
REPOS_DIR_NAME = "repos"
DEFAULT_BRANCH = "main"

# 打包进 wheel 时表情目录只保留代码，图片由资源接口单独下载，
# 因此仓库同步同样只取这些文本/代码类文件。
CODE_SUFFIXES = {".py", ".json", ".toml", ".txt", ".md", ".yaml", ".yml"}
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"}
SYNC_SUFFIXES = CODE_SUFFIXES | IMAGE_SUFFIXES

# 常见表情目录名，用于探测时优先匹配。
COMMON_MEME_DIRS = ("memes", "emoji")

# 内置的常用仓库，方便在管理面板里一键添加。
PRESET_REPOS: list[dict[str, str]] = [
    {
        "name": "meme-generator 额外表情仓库",
        "url": "MemeCrafters/meme-generator-contrib",
        "branch": "main",
    },
    {
        "name": "太子的仓库",
        "url": "anyliew/meme_emoji",
        "branch": "main",
    },
    {
        "name": "jinjiao007的仓库",
        "url": "jinjiao007/meme-generator-jj",
        "branch": "master",
    },
    {
        "name": "太子的仓库2",
        "url": "anyliew/meme_emoji_nsfw",
        "branch": "main",
    },
]


def repo_source_name(identifier: str) -> str:
    """表情来源的展示名，形如 ``repo:owner/name``。"""
    return f"repo:{identifier}"


# 加速源占位符：写成 ``https://example.com/{url}`` 时替换原地址，
# 否则一律做前缀拼接。
PROXY_URL_PLACEHOLDER = "{url}"

_SCHEME_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.\-]*://")
# 匹配「加速源 + 原始地址」里把两者分开的那个斜杠
_ACCELERATED_URL_RE = re.compile(r"/(?=https?://)")


def normalize_proxy(proxy: str) -> str:
    """规范化加速源，返回不带尾部斜杠的前缀；空字符串表示不使用加速源。

    三种写法都支持：

    * 前缀式：``https://ghfast.top/``
    * 占位符式：``https://example.com/proxy/{url}``
    * 只填域名：``ghfast.top``（自动补 ``https://``）
    """
    proxy = (proxy or "").strip()
    if not proxy:
        return ""
    if not _SCHEME_RE.match(proxy):
        proxy = f"https://{proxy}"
    if not urlparse(proxy).hostname:
        raise ValueError(f"无法识别的加速源地址：{proxy}")
    return proxy.rstrip("/")


def apply_proxy(proxy: str, url: str) -> str:
    """把加速源套到 GitHub 地址上。"""
    normalized = normalize_proxy(proxy)
    if not normalized:
        return url
    if PROXY_URL_PLACEHOLDER in normalized:
        return normalized.replace(PROXY_URL_PLACEHOLDER, url)
    return f"{normalized}/{url}"


def split_accelerated_url(url: str) -> tuple[str, str]:
    """拆出「加速源 + 原始地址」形式的仓库地址。

    ``https://ghfast.top/https://github.com/owner/repo``
    → ``("https://github.com/owner/repo", "https://ghfast.top")``

    不是这种形式的地址原样返回，加速源为空字符串，因此把整串加速地址
    粘进输入框也能正常添加仓库。
    """
    text = (url or "").strip()
    match = _ACCELERATED_URL_RE.search(text)
    if not match:
        return text, ""
    prefix, target = text[: match.start()], text[match.start() + 1 :]
    if not target.startswith(("http://", "https://")):
        return text, ""
    try:
        return target.rstrip("/"), normalize_proxy(prefix)
    except ValueError:
        return text, ""


def _proxy_error_page(content: bytes, path: str) -> bool:
    """加速源对不支持的地址可能返回 HTML 错误页，代码文件一眼就能看出来。"""
    if Path(path).suffix.lower() not in {".py", ".json", ".toml", ".yaml", ".yml"}:
        return False
    head = content[:256].lstrip().lower()
    return head.startswith(b"<!doctype") or head.startswith(b"<html")


@dataclass
class RepoFile:
    """仓库里的一个文件。"""

    path: str
    sha: str
    size: int = 0

    @property
    def suffix(self) -> str:
        return Path(self.path).suffix.lower()

    @property
    def is_code(self) -> bool:
        return self.suffix in CODE_SUFFIXES

    @property
    def is_binary(self) -> bool:
        return self.suffix in IMAGE_SUFFIXES

    @property
    def is_syncable(self) -> bool:
        return self.suffix in SYNC_SUFFIXES

    def meme_key(self, meme_dir: str = "") -> Optional[str]:
        """返回文件所属的表情 key。

        ``meme_dir`` 是仓库内的表情目录（如 ``memes``、``emoji``）。
        """
        parts = Path(self.path).parts
        prefix = tuple(Path(meme_dir).parts) if meme_dir else ()
        if prefix:
            if parts[: len(prefix)] != prefix or len(parts) <= len(prefix) + 1:
                return None
            return parts[len(prefix)]
        if len(parts) > 1:
            return parts[0]
        return None


def _stable_hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _json_or_none(resp: httpx.Response) -> Optional[dict[str, Any]]:
    """解析 JSON 对象；不是 JSON（例如加速源的错误页）时返回 ``None``。"""
    try:
        data = resp.json()
    except ValueError:
        return None
    return data if isinstance(data, dict) else None


def _repo_dir(identifier: str) -> Path:
    safe = identifier.replace("/", "__").replace(":", "_").replace("\\", "_")
    return get_data_dir() / REPOS_DIR_NAME / safe


def _state_file(identifier: str) -> Path:
    return _repo_dir(identifier) / STATE_FILE_NAME


def normalize_repo_url(url: str) -> str:
    """把用户输入统一成 ``owner/repo`` 或本地绝对路径。

    支持 ``https://github.com/owner/repo``、``git@github.com:owner/repo.git``、
    ``owner/repo``，以及本地 ``/path/to/repo`` / ``C:\\path`` 形式。
    """
    url = url.strip().rstrip("/")
    if not url:
        raise ValueError("仓库地址不能为空")

    if url.endswith(".git"):
        url = url[: -len(".git")]

    local = Path(url).expanduser()
    if local.is_absolute():
        return str(local.resolve())

    if url.startswith(("http://", "https://")):
        parsed = urlparse(url)
        if "github.com" in (parsed.hostname or ""):
            return parsed.path.strip("/")
        return f"{parsed.hostname}{parsed.path}".strip("/")

    if url.startswith("git@"):
        # git@github.com:owner/repo
        _, _, rest = url.partition(":")
        return rest.strip("/")

    if "/" in url:
        return url

    raise ValueError(f"无法识别的仓库地址：{url}")


def _is_local(identifier: str) -> bool:
    return Path(identifier).is_absolute()


def detect_meme_dir(paths: list[str]) -> str:
    """从文件路径列表里推断表情目录。

    统计每个目录下「子目录中含 ``__init__.py``」的数量，取最多的那个作为表情
    目录；社区仓库有的用 ``memes/``、有的用 ``emoji/``，也有的直接放在根目录。
    常见目录名优先，避免 ``docs/`` 之类的目录碰巧胜出。
    """
    candidates: dict[str, set[str]] = {}
    for path in paths:
        parts = path.split("/")
        if not parts or not parts[-1].endswith(".py"):
            continue
        if parts[-1] != "__init__.py" or len(parts) < 2:
            continue
        parent = "/".join(parts[:-2])
        candidates.setdefault(parent, set()).add(parts[-2])

    if not candidates:
        return ""

    def score(item: tuple[str, set[str]]) -> tuple[int, int]:
        directory, keys = item
        # 先比表情数量，再让常见目录名占优
        preferred = 1 if directory in COMMON_MEME_DIRS or directory == "" else 0
        return (len(keys), preferred)

    directory, _ = max(candidates.items(), key=score)
    return directory


class RepositoryClient:
    """读取远端（GitHub）或本地仓库的内容。

    ``proxy`` 是加速源前缀；一旦配置，所有 GitHub 请求都会先走加速地址，
    失败再退回直连。每个 GitHub 主机的可用性只探测一次，后续请求不再重复尝试。
    """

    def __init__(
        self,
        identifier: str,
        ref: str = DEFAULT_BRANCH,
        token: Optional[str] = None,
        proxy: str = "",
        transport: Optional[httpx.AsyncBaseTransport] = None,
    ):
        self.identifier = identifier
        self.ref = ref or DEFAULT_BRANCH
        self.token = token or os.getenv("GITHUB_TOKEN") or os.getenv("GH_TOKEN") or ""
        self.proxy = normalize_proxy(proxy)
        self._files_cache: Optional[list[RepoFile]] = None
        self._transport = transport
        # 每个 GitHub 主机上加速源是否可用；False 表示已经确认要直连
        self._proxy_usable: dict[str, bool] = {}

    @property
    def local_path(self) -> Optional[Path]:
        if _is_local(self.identifier):
            return Path(self.identifier)
        return None

    @property
    def accelerated(self) -> bool:
        """本地仓库与未配置加速源时都走直连。"""
        return bool(self.proxy) and self.local_path is None

    def _candidates(self, url: str) -> list[tuple[str, bool]]:
        """给出候选请求地址：加速源优先，直连兜底。第二项表示是否走了加速源。"""
        if not self.accelerated:
            return [(url, False)]
        host = urlparse(url).hostname or ""
        if self._proxy_usable.get(host) is False:
            return [(url, False)]
        return [(apply_proxy(self.proxy, url), True), (url, False)]

    def _record_route(self, url: str, via_proxy: bool, ok: bool) -> None:
        """记住某个主机上加速源是否可用，避免逐个文件重复回退。"""
        host = urlparse(url).hostname or ""
        self._proxy_usable[host] = ok if via_proxy else False

    def describe_routes(self) -> str:
        """本次同步里加速源与直连各自负责哪些 GitHub 主机，写进日志便于排错。"""
        if not self.accelerated:
            return "direct"
        accelerated = sorted(host for host, ok in self._proxy_usable.items() if ok)
        direct = sorted(host for host, ok in self._proxy_usable.items() if not ok)
        parts = []
        if accelerated:
            parts.append(f"proxy={','.join(accelerated)}")
        if direct:
            parts.append(f"direct={','.join(direct)}")
        return "; ".join(parts) if parts else f"proxy={self.proxy} (untested)"

    def _headers(self, accept: str = "application/vnd.github+json") -> dict[str, str]:
        headers = {"Accept": accept}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    def _client(self, timeout: float = 60.0) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            timeout=httpx.Timeout(timeout, connect=30.0),
            headers=self._headers(),
            follow_redirects=True,
            transport=self._transport,
        )

    # -- 列出文件（不下载内容）--------------------------------------------

    async def list_files(self) -> list[RepoFile]:
        """列出仓库中可同步的文件及其 sha，用于比对差异。"""
        if self._files_cache is not None:
            return self._files_cache

        if local := self.local_path:
            files = self._list_local_files(local)
        else:
            files = await self._list_tree_files()

        self._files_cache = files
        return files

    def _list_local_files(self, root: Path) -> list[RepoFile]:
        files = []
        for path in sorted(root.rglob("*")):
            if not path.is_file() or not _is_syncable(path.suffix.lower()):
                continue
            rel = path.relative_to(root).as_posix()
            if _is_ignored(rel):
                continue
            content = path.read_bytes()
            files.append(
                RepoFile(path=rel, sha=_stable_hash(content), size=len(content))
            )
        return files

    async def _list_tree_files(
        self, ref: Optional[str] = None, _retried: bool = False
    ) -> list[RepoFile]:
        ref = ref or self.ref
        url = f"https://api.github.com/repos/{self.identifier}/git/trees/{ref}?recursive=1"

        payload: Optional[dict[str, Any]] = None
        status = 0
        last_error: Optional[Exception] = None
        async with self._client(30) as client:
            for candidate, via_proxy in self._candidates(url):
                try:
                    resp = await client.get(candidate)
                except httpx.HTTPError as e:
                    last_error = e
                    self._record_route(url, via_proxy, False)
                    continue
                status = resp.status_code
                if status == 200:
                    data = _json_or_none(resp)
                    # 加速源可能返回 200 但正文不是 GitHub 接口数据，此时继续回退
                    if data is not None and ("tree" in data or data.get("truncated")):
                        self._record_route(url, via_proxy, True)
                        payload = data
                        break
                    last_error = ValueError("接口返回的内容不是有效的仓库数据")
                self._record_route(url, via_proxy, False)

        if payload is None:
            if status == 404 and not _retried and ref in ("main", "master"):
                # 分支名不对时在常用分支间回退一次
                fallback = "master" if ref == "main" else "main"
                self.ref = fallback
                return await self._list_tree_files(fallback, True)
            if status == 404:
                raise ValueError(f"仓库不存在或分支不可用：{self.identifier}@{ref}")
            if status == 403:
                raise ValueError(
                    "GitHub 接口访问受限（可能触发了速率限制），"
                    "可配置 GITHUB_TOKEN 后重试"
                )
            if last_error is not None:
                raise last_error
            raise ValueError(
                f"GitHub 接口请求失败（HTTP {status}）：{self.identifier}@{ref}"
            )

        if payload.get("truncated"):
            # 超大仓库的 tree 会被截断，退回用归档列举
            logger.warning(
                f"Tree for {self.identifier} was truncated, falling back to archive"
            )
            return await self._list_archive_files()

        files = []
        for item in payload.get("tree", []):
            if item.get("type") != "blob":
                continue
            path = item.get("path", "")
            if _is_ignored(path) or not _is_syncable(Path(path).suffix.lower()):
                continue
            files.append(
                RepoFile(
                    path=path,
                    sha=str(item.get("sha", "")),
                    size=int(item.get("size") or 0),
                )
            )
        return files

    async def _list_archive_files(self) -> list[RepoFile]:
        """兜底：下载归档来列举文件（内容不入库）。"""
        contents = await self.fetch_archive()
        return [
            RepoFile(path=path, sha=_stable_hash(content), size=len(content))
            for path, content in sorted(contents.items())
        ]

    # -- 读取内容 ---------------------------------------------------------

    async def read_file(self, file: RepoFile) -> bytes:
        """读取单个文件内容（用于增量更新）。"""
        if local := self.local_path:
            return (local / file.path).read_bytes()

        url = (
            f"https://api.github.com/repos/{self.identifier}"
            f"/contents/{file.path}?ref={self.ref}"
        )
        last_error: Optional[Exception] = None
        status = 0
        async with self._client(60) as client:
            for candidate, via_proxy in self._candidates(url):
                try:
                    resp = await client.get(
                        candidate, headers=self._headers("application/vnd.github.raw")
                    )
                except httpx.HTTPError as e:
                    last_error = e
                    self._record_route(url, via_proxy, False)
                    continue
                status = resp.status_code
                if status == 200 and not _proxy_error_page(resp.content, file.path):
                    self._record_route(url, via_proxy, True)
                    return resp.content
                last_error = None
                self._record_route(url, via_proxy, False)

        if last_error is not None:
            raise last_error
        raise httpx.HTTPError(
            f"文件下载失败（HTTP {status}）：{self.identifier}/{file.path}"
        )

    async def fetch_archive(self) -> dict[str, bytes]:
        """下载整个仓库归档并解压到内存。

        只在需要批量读取内容时使用；大仓库会有几百 MB，注意内存开销。
        落盘场景请用 :meth:`extract_archive`，它是流式的。
        """
        contents: dict[str, bytes] = {}

        def collect(rel: str, data: bytes) -> None:
            contents[rel] = data

        await self.extract_archive(collect)
        return contents

    async def extract_archive(self, on_file: Any, timeout: float = 900.0) -> None:
        """流式下载并解压归档，逐个回调 ``on_file(相对路径, 内容)``。

        归档不整体驻留内存：先落临时文件，再按成员读取，避免几百 MB 的仓库
        把内存吃满。本地仓库不走这里，直接复制文件。

        加速源不可用（连不上、返回错误页、返回的不是合法 tar.gz）时会自动
        退回直连；两个分支名都 404 才认定仓库不存在。
        """
        if local := self.local_path:
            for file in await self.list_files():
                on_file(file.path, (local / file.path).read_bytes())
            return

        # 分支名不对时在常用分支间回退一次
        refs = [self.ref]
        if self.ref in ("main", "master"):
            refs.append("master" if self.ref == "main" else "main")

        last_status = 0
        for ref in refs:
            url = (
                f"https://codeload.github.com/{self.identifier}/tar.gz/refs/heads/{ref}"
            )
            for candidate, via_proxy in self._candidates(url):
                status = await self._download_archive(candidate, on_file, timeout)
                if status == 200:
                    self._record_route(url, via_proxy, True)
                    self.ref = ref
                    return
                last_status = status
                self._record_route(url, via_proxy, False)
            if last_status != 404:
                # 报错不是因为分支不存在，换分支不会再成功
                break

        if last_status == 404:
            raise ValueError(f"仓库不存在或分支不可用：{self.identifier}@{refs[0]}")
        raise httpx.HTTPError(
            f"仓库归档下载失败（HTTP {last_status}）：{self.identifier}@{refs[0]}"
        )

    async def _download_archive(self, url: str, on_file: Any, timeout: float) -> int:
        """下载并解压一个归档地址，返回 HTTP 状态码（0 表示失败）。"""
        with tempfile.NamedTemporaryFile(suffix=".tar.gz", delete=False) as tmp:
            tmp_path = Path(tmp.name)

        try:
            async with self._client(timeout) as client:
                async with client.stream("GET", url) as resp:
                    if resp.status_code != 200:
                        await resp.aread()
                        return resp.status_code
                    with tmp_path.open("wb") as fh:
                        async for chunk in resp.aiter_bytes(1024 * 256):
                            fh.write(chunk)

            with tarfile.open(tmp_path, mode="r:gz") as tar:
                for member in tar.getmembers():
                    if not member.isfile():
                        continue
                    # 归档里第一层是 <repo>-<ref>/，需要剥掉
                    parts = member.name.split("/", 1)
                    if len(parts) < 2 or not parts[1]:
                        continue
                    rel = parts[1]
                    if _is_ignored(rel) or not _is_syncable(Path(rel).suffix.lower()):
                        continue
                    extracted = tar.extractfile(member)
                    if extracted is None:
                        continue
                    with extracted:
                        on_file(rel, extracted.read())
            return 200
        except (httpx.HTTPError, tarfile.TarError, OSError) as e:
            # 加速源返回 HTML 错误页时既不是合法 gzip，也不是合法 tar
            logger.warning(f"Failed to fetch archive {url}: {e}")
            return 0
        finally:
            tmp_path.unlink(missing_ok=True)


def _is_ignored(rel: str) -> bool:
    """内部与无关文件：.git、点文件、缓存、子模块 .gitmodules 等。"""
    parts = Path(rel).parts
    return (
        not parts
        or STATE_FILE_NAME in rel
        or "__pycache__" in parts
        or any(part.startswith(".") for part in parts)
    )


def _is_syncable(suffix: str) -> bool:
    return suffix in SYNC_SUFFIXES


@dataclass
class RepoState:
    """一个仓库的本地同步状态。"""

    identifier: str
    name: str = ""
    ref: str = DEFAULT_BRANCH
    url: str = ""
    enabled: bool = True
    meme_dir: str = ""
    # 该仓库专用的加速源前缀；留空表示跟随全局默认（[repo] github_proxy）
    proxy: str = ""
    installed_at: Optional[float] = None
    updated_at: Optional[float] = None
    files: dict[str, dict[str, Any]] = field(default_factory=dict)

    @property
    def display_name(self) -> str:
        return self.name or self.identifier

    @property
    def meme_keys(self) -> list[str]:
        keys = set()
        for path in self.files:
            key = RepoFile(path=path, sha="").meme_key(self.meme_dir)
            if key:
                keys.add(key)
        return sorted(keys)

    def to_dict(self) -> dict[str, Any]:
        return {
            "identifier": self.identifier,
            "name": self.name,
            "ref": self.ref,
            "url": self.url,
            "enabled": self.enabled,
            "meme_dir": self.meme_dir,
            "proxy": self.proxy,
            "installed_at": self.installed_at,
            "updated_at": self.updated_at,
            "files": self.files,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "RepoState":
        return cls(
            identifier=data["identifier"],
            name=data.get("name", ""),
            ref=data.get("ref", DEFAULT_BRANCH),
            url=data.get("url", ""),
            enabled=data.get("enabled", True),
            meme_dir=data.get("meme_dir", ""),
            proxy=data.get("proxy", ""),
            installed_at=data.get("installed_at"),
            updated_at=data.get("updated_at"),
            files=data.get("files", {}),
        )


class RepoManager:
    """外部仓库的注册、同步、更新检查与卸载。"""

    def __init__(self) -> None:
        self._states: Optional[dict[str, RepoState]] = None
        self._update_lock = asyncio.Lock()
        self._auto_update_running = False

    def repos_root(self) -> Path:
        root = get_data_dir() / REPOS_DIR_NAME
        root.mkdir(parents=True, exist_ok=True)
        return root

    def _load_states(self) -> dict[str, RepoState]:
        if self._states is not None:
            return self._states

        states: dict[str, RepoState] = {}
        root = self.repos_root()
        for repo_dir in sorted(root.iterdir()):
            state_file = repo_dir / STATE_FILE_NAME
            if not repo_dir.is_dir() or not state_file.is_file():
                continue
            try:
                states[repo_dir.name] = RepoState.from_dict(
                    json.loads(state_file.read_text(encoding="utf-8"))
                )
            except (OSError, ValueError, KeyError) as e:
                logger.warning(f"Failed to read repo state {state_file}: {e}")
        self._states = states
        return states

    def _save_state(self, state: RepoState) -> None:
        repo_dir = _repo_dir(state.identifier)
        repo_dir.mkdir(parents=True, exist_ok=True)
        _state_file(state.identifier).write_text(
            json.dumps(state.to_dict(), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        self._load_states()[repo_dir.name] = state

    def invalidate(self) -> None:
        self._states = None

    def save(self, state: RepoState) -> None:
        """持久化仓库状态，用于改名、改加速源这类元信息变更。"""
        self._save_state(state)

    def list_repos(self) -> list[RepoState]:
        return sorted(self._load_states().values(), key=lambda s: s.identifier)

    def get_repo(self, identifier: str) -> Optional[RepoState]:
        states = self._load_states()
        if identifier in states:
            return states[identifier]
        normalized = None
        try:
            normalized = normalize_repo_url(identifier)
        except ValueError:
            pass
        for state in states.values():
            if state.identifier == normalized or state.url == identifier:
                return state
        return None

    def work_dir(self, identifier: str) -> Path:
        return _repo_dir(identifier) / "src"

    # -- 加速源 ------------------------------------------------------------

    def default_proxy(self) -> str:
        """全局默认加速源，来自配置文件的 ``[repo] github_proxy``。"""
        try:
            return normalize_proxy(meme_config.repo.github_proxy)
        except (ValueError, AttributeError) as e:
            logger.warning(f"Invalid global github_proxy: {e}")
            return ""

    def effective_proxy(self, state: RepoState) -> str:
        """仓库实际使用的加速源：仓库自己的设置优先，其次全局默认。"""
        if _is_local(state.identifier):
            return ""
        if state.proxy:
            return state.proxy
        return self.default_proxy()

    def accelerated_url(self, state: RepoState) -> str:
        """仓库经过加速源后的完整地址，用于在管理面板里展示。"""
        if _is_local(state.identifier):
            return state.identifier
        base = f"https://github.com/{state.identifier}"
        proxy = self.effective_proxy(state)
        return apply_proxy(proxy, base) if proxy else base

    def set_proxy(self, identifier: str, proxy: str) -> RepoState:
        """给单个仓库设置加速源；传空字符串表示跟随全局默认。"""
        state = self.get_repo(identifier)
        if not state:
            raise ValueError(f"仓库不存在：{identifier}")
        state.proxy = normalize_proxy(proxy)
        self._save_state(state)
        return state

    def _client_for(
        self,
        state: RepoState,
        ref: Optional[str] = None,
        transport: Optional[httpx.AsyncBaseTransport] = None,
    ) -> RepositoryClient:
        return RepositoryClient(
            state.identifier,
            ref=ref or state.ref,
            proxy=self.effective_proxy(state),
            transport=transport,
        )

    # -- 预览可添加的仓库 --------------------------------------------------

    async def preview(self, url: str, ref: str = "", proxy: str = "") -> dict[str, Any]:
        """在真正添加前探测仓库：表情目录、表情数量与列表。"""
        identifier = normalize_repo_url(url)
        resolved_proxy = normalize_proxy(proxy)
        client = RepositoryClient(
            identifier,
            ref=ref or DEFAULT_BRANCH,
            proxy=resolved_proxy or self.default_proxy(),
        )
        files = await client.list_files()
        if not files:
            raise ValueError(f"仓库中没有找到可同步的文件：{identifier}")

        meme_dir = detect_meme_dir([f.path for f in files])
        keys = sorted({key for f in files if (key := f.meme_key(meme_dir))})
        return {
            "identifier": identifier,
            "name": Path(identifier).name
            if not _is_local(identifier)
            else Path(identifier).name,
            "ref": client.ref,
            "meme_dir": meme_dir,
            "proxy": resolved_proxy,
            "effective_proxy": client.proxy,
            "file_count": len(files),
            "meme_count": len(keys),
            "meme_keys": keys,
            "installed": self.get_repo(identifier) is not None,
        }

    # -- 安装与更新 -------------------------------------------------------

    async def install(
        self,
        url: str,
        ref: str = "",
        name: str = "",
        meme_dir: str = "",
        proxy: str = "",
    ) -> RepoState:
        """注册并下载一个外部仓库。"""
        identifier = normalize_repo_url(url)
        if self.get_repo(identifier):
            raise ValueError(f"仓库已存在：{identifier}")

        resolved_proxy = normalize_proxy(proxy)
        client = RepositoryClient(
            identifier,
            ref=ref or DEFAULT_BRANCH,
            proxy=resolved_proxy or self.default_proxy(),
        )
        files = await client.list_files()
        if not files:
            raise ValueError(f"仓库中没有找到可同步的文件：{identifier}")

        resolved_dir = meme_dir or detect_meme_dir([f.path for f in files])
        state = RepoState(
            identifier=identifier,
            name=name or Path(identifier).name,
            ref=client.ref,
            url=url,
            meme_dir=resolved_dir,
            proxy=resolved_proxy,
        )
        # 探测阶段已经确定了可用路由，直接用同一个客户端拉取归档
        await self._sync_files(client, state, files, full=True)
        state.installed_at = time.time()
        state.updated_at = state.installed_at
        self._save_state(state)
        self.load_repo_memes(state)
        logger.info(
            f"Installed repo {state.identifier} with {len(state.meme_keys)} meme(s) "
            f"({client.describe_routes()})"
        )
        return state

    async def update_all_repos(self) -> None:
        """自动同步已注册仓库；上一轮尚未结束时跳过，单仓库失败不影响其他仓库。"""
        if self._auto_update_running:
            return
        self._auto_update_running = True
        try:
            for state in self.list_repos():
                try:
                    await self.update(state.identifier)
                except Exception as e:  # noqa: BLE001 - 仓库异常隔离，取消仍向上传播
                    logger.opt(exception=e).warning(
                        f"Failed to automatically update repo {state.identifier}"
                    )
        finally:
            self._auto_update_running = False

    async def update(self, identifier: str) -> tuple[RepoState, dict[str, Any]]:
        """串行执行自动与手动更新，避免同时写入仓库与重新加载表情。"""
        async with self._update_lock:
            return await self._update(identifier)

    async def _update(self, identifier: str) -> tuple[RepoState, dict[str, Any]]:
        """重新拉取仓库内容，返回状态和变更摘要。"""
        state = self.get_repo(identifier)
        if not state:
            raise ValueError(f"仓库不存在：{identifier}")

        client = self._client_for(state)
        files = await client.list_files()
        changes = self.diff_with_files(state, files)

        if changes["added"] or changes["modified"] or changes["removed"]:
            await self._sync_files(client, state, files, full=False)
            # 下载完成后再卸载，网络失败或关闭取消时保留当前已加载的表情。
            unload_memes_by_source(repo_source_name(state.identifier))
            state.updated_at = time.time()
            self._save_state(state)
            self.load_repo_memes(state)
            logger.info(
                f"Updated repo {state.identifier}: "
                f"{len(changes['added'])} added, {len(changes['modified'])} modified, "
                f"{len(changes['removed'])} removed ({client.describe_routes()})"
            )

        return state, changes

    async def _sync_files(
        self,
        client: RepositoryClient,
        state: RepoState,
        files: list[RepoFile],
        full: bool,
    ) -> None:
        """把远端文件落到本地。

        ``full=True`` 走归档（一次请求），``full=False`` 只下载有变化的文件。
        """
        work_dir = self.work_dir(state.identifier)
        work_dir.mkdir(parents=True, exist_ok=True)

        wanted = {f.path: f for f in files if f.is_syncable}

        # 删除本地已不在仓库中的文件
        for path in list(state.files):
            if path not in wanted:
                target = work_dir / path
                if target.is_file():
                    target.unlink()

        if full:
            # 流式解压：归档不整体驻留内存，逐个文件写入
            def write_file(rel: str, content: bytes) -> None:
                remote = wanted.get(rel)
                if remote is None:
                    return
                target = work_dir / rel
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(content)
                if not remote.sha:
                    remote.sha = _stable_hash(content)
                remote.size = remote.size or len(content)

            await client.extract_archive(write_file)
        else:
            for path, remote in wanted.items():
                target = work_dir / path
                if (
                    remote.sha
                    and target.is_file()
                    and state.files.get(path, {}).get("sha") == remote.sha
                ):
                    continue
                try:
                    content = await client.read_file(remote)
                except (httpx.HTTPError, FileNotFoundError) as e:
                    logger.warning(
                        f"Failed to download {path} from {state.identifier}: {e}"
                    )
                    continue
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(content)
                if not remote.sha:
                    remote.sha = _stable_hash(content)
                remote.size = remote.size or len(content)

        state.files = {
            path: {"sha": remote.sha, "size": remote.size, "code": remote.is_code}
            for path, remote in sorted(wanted.items())
        }

    def diff_with_files(
        self, state: RepoState, remote_files: list[RepoFile]
    ) -> dict[str, Any]:
        """对比本地状态与远端文件列表。"""
        local = state.files
        remote = {f.path: f for f in remote_files if f.is_syncable}

        added, modified, removed = [], [], []
        for path, remote_file in remote.items():
            local_entry = local.get(path)
            if local_entry is None:
                added.append(path)
            elif remote_file.sha and local_entry.get("sha") != remote_file.sha:
                modified.append(path)
        for path in local:
            if path not in remote:
                removed.append(path)

        return {
            "added": sorted(added),
            "modified": sorted(modified),
            "removed": sorted(removed),
            # added_memes 只看真正新增的文件；被修改的表情归入 modified_memes
            "added_memes": sorted(self._meme_keys_of(added, state.meme_dir)),
            "modified_memes": sorted(self._meme_keys_of(modified, state.meme_dir)),
            "removed_memes": sorted(self._meme_keys_of(removed, state.meme_dir)),
        }

    @staticmethod
    def _meme_keys_of(paths: list[str], meme_dir: str = "") -> set[str]:
        keys = set()
        for path in paths:
            key = RepoFile(path=path, sha="").meme_key(meme_dir)
            if key:
                keys.add(key)
        return keys

    async def check_update(self, identifier: str) -> dict[str, Any]:
        """检查单个仓库是否有更新，并给出变更文件与内容。"""
        state = self.get_repo(identifier)
        if not state:
            raise ValueError(f"仓库不存在：{identifier}")

        client = self._client_for(state)
        files = await client.list_files()
        changes = self.diff_with_files(state, files)

        changed_paths = changes["added"] + changes["modified"]
        file_details = []
        for path in changed_paths:
            remote = next((f for f in files if f.path == path), None)
            if not remote:
                continue
            entry: dict[str, Any] = {
                "path": path,
                "status": "added" if path in changes["added"] else "modified",
                "meme_key": remote.meme_key(state.meme_dir),
                "kind": "code" if remote.is_code else "asset",
            }
            if remote.is_code and remote.size < 200_000:
                try:
                    content = await client.read_file(remote)
                    entry["content"] = content.decode("utf-8", errors="replace")
                    old_path = self.work_dir(state.identifier) / path
                    if old_path.is_file():
                        entry["previous_content"] = old_path.read_text(
                            encoding="utf-8", errors="replace"
                        )
                except (httpx.HTTPError, UnicodeDecodeError) as e:
                    entry["content_error"] = str(e)
            file_details.append(entry)

        return {
            "identifier": state.identifier,
            "name": state.display_name,
            "proxy": self.effective_proxy(state),
            "has_update": bool(changed_paths or changes["removed"]),
            "changes": changes,
            "files": file_details,
        }

    async def check_all_updates(self) -> list[dict[str, Any]]:
        results = []
        for state in self.list_repos():
            try:
                results.append(await self.check_update(state.identifier))
            except (httpx.HTTPError, ValueError) as e:
                results.append(
                    {
                        "identifier": state.identifier,
                        "name": state.display_name,
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
        return results

    def load_repo_memes(self, state: RepoState) -> list[str]:
        """把仓库目录里的表情加载进内存。"""
        work_dir = self.work_dir(state.identifier)
        if state.meme_dir:
            target = work_dir / state.meme_dir
        else:
            # 表情目录探测失败时退回仓库根目录，至少让内置约定（memes/）可用
            nested = work_dir / "memes"
            target = nested if nested.is_dir() else work_dir
        if not target.is_dir():
            return []

        source = repo_source_name(state.identifier)
        register_source_dir(source, work_dir)
        before = set(_memes_snapshot())
        load_memes(target, source=source)
        return sorted(set(_memes_snapshot()) - before)

    def uninstall(self, identifier: str) -> list[str]:
        """移除仓库并卸载它加载的表情。"""
        state = self.get_repo(identifier)
        if not state:
            raise ValueError(f"仓库不存在：{identifier}")

        removed = unload_memes_by_source(repo_source_name(state.identifier))
        repo_dir = _repo_dir(state.identifier)
        if repo_dir.is_dir():
            shutil.rmtree(repo_dir, ignore_errors=True)

        states = self._load_states()
        states.pop(repo_dir.name, None)
        self.invalidate()
        return removed


def _memes_snapshot() -> list[str]:
    from .manager import get_all_memes

    return [meme.key for meme in get_all_memes()]


def find_meme_dir(key: str) -> Optional[Path]:
    """定位某个表情的源码目录，内置与外部仓库都能找到。"""
    from .manager import get_meme_source, get_source_dir

    source = get_meme_source(key)
    if source == BUILTIN_SOURCE:
        candidate = Path(__file__).parent / "memes" / key
        return candidate if candidate.is_dir() else None

    # 外部来源的展示名是 repo:<identifier>，实际目录另行登记
    source_dir = get_source_dir(source)
    if not source_dir:
        return None

    work_dir = Path(source_dir)
    state = repo_manager.get_repo(source.removeprefix("repo:"))
    candidates = [
        work_dir / (state.meme_dir if state and state.meme_dir else "memes") / key,
        work_dir / "memes" / key,
        work_dir / "emoji" / key,
        work_dir / key,
    ]
    for candidate in candidates:
        if candidate.is_dir():
            return candidate
    return None


def list_meme_files(key: str) -> list[dict[str, Any]]:
    """列出表情目录下的文件（相对路径、大小、是否代码）。"""
    meme_dir = find_meme_dir(key)
    if not meme_dir:
        return []

    files = []
    for path in sorted(meme_dir.rglob("*")):
        if not path.is_file() or "__pycache__" in path.parts:
            continue
        suffix = path.suffix.lower()
        files.append(
            {
                "path": path.relative_to(meme_dir).as_posix(),
                "size": path.stat().st_size,
                "kind": "code" if suffix in CODE_SUFFIXES else "asset",
            }
        )
    return files


async def probe_proxy(
    proxy: str, identifier: str = "", ref: str = ""
) -> dict[str, Any]:
    """测试加速源的可用性：同时访问 GitHub 接口、raw 内容与归档，对比直连耗时。

    管理面板里点「测试加速源」时调用，返回逐条结果，方便判断是不是加速源本身的问题。
    不同加速源支持的端点不一样（有的只代理 raw，不代理 api 或归档），因此逐条列出；
    实际同步时也是按主机分别回退直连的。
    """
    resolved_proxy = normalize_proxy(proxy)
    target = (
        normalize_repo_url(identifier) if identifier.strip() else "octocat/Hello-World"
    )
    resolved_ref = ref or DEFAULT_BRANCH
    targets = [
        ("API 接口", f"https://api.github.com/repos/{target}", "GET"),
        (
            "raw 内容",
            f"https://raw.githubusercontent.com/{target}/{resolved_ref}/README.md",
            "GET",
        ),
        (
            "仓库归档",
            f"https://codeload.github.com/{target}/tar.gz/refs/heads/{resolved_ref}",
            "HEAD",
        ),
    ]

    async def measure(
        label: str, url: str, method: str, via_proxy: bool
    ) -> dict[str, Any]:
        started = time.perf_counter()
        try:
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(15.0, connect=10.0), follow_redirects=True
            ) as client:
                resp = await client.request(method, url)
            return {
                "label": label,
                "url": url,
                "via_proxy": via_proxy,
                "ok": resp.status_code < 400,
                "status": resp.status_code,
                "elapsed_ms": round((time.perf_counter() - started) * 1000, 1),
            }
        except httpx.HTTPError as e:
            return {
                "label": label,
                "url": url,
                "via_proxy": via_proxy,
                "ok": False,
                "status": 0,
                "elapsed_ms": round((time.perf_counter() - started) * 1000, 1),
                "error": str(e),
            }

    accelerated: list[dict[str, Any]] = []
    if resolved_proxy:
        for label, url, method in targets:
            accelerated.append(
                await measure(label, apply_proxy(resolved_proxy, url), method, True)
            )

    direct: list[dict[str, Any]] = []
    for label, url, method in targets:
        direct.append(await measure(label, url, method, False))

    return {
        "proxy": resolved_proxy,
        "identifier": target,
        "ref": resolved_ref,
        "accelerated": accelerated,
        "direct": direct,
        # 部分加速源只代理其中一部分端点，这两种情况分开报，界面提示更准
        "usable": bool(accelerated) and any(item["ok"] for item in accelerated),
        "all_ok": bool(accelerated) and all(item["ok"] for item in accelerated),
    }


repo_manager = RepoManager()
