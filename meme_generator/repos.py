"""外部表情仓库管理。

把「拉取额外表情仓库并更新」这件事收进主项目：注册仓库后，可以同步下载它的
表情目录到本地数据目录，再由服务加载。同步状态记录在仓库目录里的
``.meme_repo.json``，据此计算新增/更新/删除，供更新检查 API 使用。

仓库来源支持两种：

* GitHub 仓库（``https://github.com/owner/repo`` 或 ``owner/repo``）——
  通过 GitHub REST API 递归取文件树，逐个下载需要的文件；
* 本地目录（绝对路径）——直接从文件系统复制，方便本地开发与测试。
"""

import hashlib
import io
import json
import os
import shutil
import tarfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urlparse

import httpx

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


def repo_source_name(identifier: str) -> str:
    """表情来源的展示名，形如 ``repo:owner/name``。"""
    return f"repo:{identifier}"


# 打包进 wheel 时表情目录只保留代码，图片由资源接口单独下载，
# 因此仓库同步同样只取这些文本/代码类文件。
CODE_SUFFIXES = {".py", ".json", ".toml", ".txt", ".md", ".yaml", ".yml"}
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"}


@dataclass
class RepoFile:
    """仓库里的一个文件。"""

    path: str
    sha: str
    size: int = 0
    download_url: Optional[str] = None
    content: Optional[str] = None

    @property
    def suffix(self) -> str:
        return Path(self.path).suffix.lower()

    @property
    def meme_key(self) -> Optional[str]:
        """返回文件所属的表情 key（memes/<key>/... 或 <key>/...）。"""
        parts = Path(self.path).parts
        if not parts:
            return None
        if parts[0] == "memes" and len(parts) > 2:
            return parts[1]
        if len(parts) > 1:
            return parts[0]
        return None

    @property
    def is_code(self) -> bool:
        return self.suffix in CODE_SUFFIXES

    @property
    def is_binary(self) -> bool:
        return self.suffix in IMAGE_SUFFIXES


def _stable_hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


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


class RepositoryClient:
    """读取远端（GitHub）或本地仓库的内容。

    远端仓库走 GitHub 的归档接口一次拿全量文件，而不是逐个下载：像
    meme-generator-contrib 这样的仓库有两百多个文件，逐文件请求既慢又容易因
    为单个请求失败而中断。归档会缓存在内存里，一次同步只下载一次。
    """

    def __init__(self, identifier: str, ref: str = "main", token: Optional[str] = None):
        self.identifier = identifier
        self.ref = ref
        self.token = token or os.getenv("GITHUB_TOKEN") or os.getenv("GH_TOKEN") or ""
        self._files_cache: Optional[list[RepoFile]] = None
        self._contents: dict[str, bytes] = {}

    @property
    def local_path(self) -> Optional[Path]:
        if _is_local(self.identifier):
            return Path(self.identifier)
        return None

    def _headers(self) -> dict[str, str]:
        headers = {"Accept": "application/vnd.github+json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    def _archive_url(self) -> str:
        return (
            f"https://codeload.github.com/{self.identifier}"
            f"/tar.gz/refs/heads/{self.ref}"
        )

    async def _fetch_archive(self) -> None:
        """下载并解压仓库归档到内存。"""
        if self._contents:
            return
        url = self._archive_url()
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(180.0, connect=30.0),
            headers=self._headers(),
            follow_redirects=True,
        ) as client:
            resp = await client.get(url)
            if resp.status_code == 404 and self.ref == "main":
                # 老仓库可能还在用 master
                self.ref = "master"
                return await self._fetch_archive()
            resp.raise_for_status()
            archive = resp.content

        with tarfile.open(fileobj=io.BytesIO(archive), mode="r:gz") as tar:
            for member in tar.getmembers():
                if not member.isfile():
                    continue
                # 归档里第一层是 <repo>-<ref>/，需要剥掉
                parts = member.name.split("/", 1)
                if len(parts) < 2 or not parts[1]:
                    continue
                rel = parts[1]
                if rel.startswith(".") or "/." in rel:
                    continue
                extracted = tar.extractfile(member)
                if extracted is None:
                    continue
                self._contents[rel] = extracted.read()

    async def list_files(self) -> list[RepoFile]:
        """列出仓库中需要同步的文件（代码与资源）。"""
        if self._files_cache is not None:
            return self._files_cache

        if local := self.local_path:
            files = []
            for path in sorted(local.rglob("*")):
                if not path.is_file():
                    continue
                rel = path.relative_to(local).as_posix()
                if (
                    STATE_FILE_NAME in rel
                    or rel.startswith(".git")
                    or "/.git" in rel
                    or "__pycache__" in rel
                ):
                    continue
                content = path.read_bytes()
                files.append(
                    RepoFile(
                        path=rel,
                        # 本地仓库没有远端 sha，用内容哈希代替，否则无法检测改动
                        sha=_stable_hash(content),
                        size=len(content),
                    )
                )
        else:
            await self._fetch_archive()
            files = [
                RepoFile(path=path, sha=_stable_hash(content), size=len(content))
                for path, content in sorted(self._contents.items())
            ]

        self._files_cache = files
        return files

    async def read_file(self, file: RepoFile) -> bytes:
        """读取单个文件内容。"""
        if local := self.local_path:
            return (local / file.path).read_bytes()
        await self._fetch_archive()
        try:
            return self._contents[file.path]
        except KeyError:
            raise FileNotFoundError(f"仓库中不存在文件：{file.path}") from None


@dataclass
class RepoState:
    """一个仓库的本地同步状态。"""

    identifier: str
    ref: str = "main"
    url: str = ""
    enabled: bool = True
    installed_at: Optional[float] = None
    updated_at: Optional[float] = None
    files: dict[str, dict[str, Any]] = field(default_factory=dict)

    @property
    def meme_keys(self) -> list[str]:
        keys = set()
        for path in self.files:
            parts = Path(path).parts
            if parts and parts[0] == "memes" and len(parts) > 2:
                keys.add(parts[1])
            elif len(parts) > 1:
                keys.add(parts[0])
        return sorted(keys)

    def to_dict(self) -> dict[str, Any]:
        return {
            "identifier": self.identifier,
            "ref": self.ref,
            "url": self.url,
            "enabled": self.enabled,
            "installed_at": self.installed_at,
            "updated_at": self.updated_at,
            "files": self.files,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "RepoState":
        return cls(
            identifier=data["identifier"],
            ref=data.get("ref", "main"),
            url=data.get("url", ""),
            enabled=data.get("enabled", True),
            installed_at=data.get("installed_at"),
            updated_at=data.get("updated_at"),
            files=data.get("files", {}),
        )


class RepoManager:
    """外部仓库的注册、同步、更新检查与卸载。"""

    def __init__(self) -> None:
        self._states: Optional[dict[str, RepoState]] = None

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

    # -- 安装与更新 ---------------------------------------------------------

    async def install(self, url: str, ref: str = "main") -> RepoState:
        """注册并下载一个外部仓库。已存在则执行更新。"""
        identifier = normalize_repo_url(url)
        existing = self.get_repo(identifier)
        if existing and existing.identifier == identifier:
            raise ValueError(f"仓库已存在：{identifier}")

        client = RepositoryClient(identifier, ref=ref)
        files = await client.list_files()
        if not files:
            raise ValueError(f"仓库中没有找到任何文件：{identifier}")

        state = RepoState(identifier=identifier, ref=client.ref, url=url)
        await self._sync_files(client, state, files)
        state.installed_at = time.time()
        state.updated_at = state.installed_at
        self._save_state(state)
        self.load_repo_memes(state)
        return state

    async def update(self, identifier: str) -> tuple[RepoState, dict[str, Any]]:
        """重新拉取仓库内容，返回状态和变更摘要。"""
        state = self.get_repo(identifier)
        if not state:
            raise ValueError(f"仓库不存在：{identifier}")

        client = RepositoryClient(state.identifier, ref=state.ref)
        files = await client.list_files()
        changes = self.diff_with_files(state, files)

        if changes["added"] or changes["modified"] or changes["removed"]:
            # 先卸载旧表情，避免新版本用同一个 key 注册时被当成重复而跳过
            unload_memes_by_source(repo_source_name(state.identifier))
            await self._sync_files(client, state, files)
            state.updated_at = time.time()
            self._save_state(state)
            self.load_repo_memes(state)

        return state, changes

    async def _sync_files(
        self, client: RepositoryClient, state: RepoState, files: list[RepoFile]
    ) -> None:
        work_dir = self.work_dir(state.identifier)
        work_dir.mkdir(parents=True, exist_ok=True)

        wanted = {f.path: f for f in files if f.is_code or f.is_binary}

        # 删除已不在仓库中的文件
        for path in list(state.files):
            if path not in wanted:
                target = work_dir / path
                if target.is_file():
                    target.unlink()

        for path, remote in wanted.items():
            target = work_dir / path
            if (
                target.is_file()
                and state.files.get(path, {}).get("sha") == remote.sha
                and remote.sha
            ):
                continue
            try:
                content = await client.read_file(remote)
            except httpx.HTTPError as e:
                logger.warning(
                    f"Failed to download {path} from {state.identifier}: {e}"
                )
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)
            remote.sha = remote.sha or _stable_hash(content)

        state.files = {
            path: {"sha": remote.sha, "size": remote.size, "code": remote.is_code}
            for path, remote in sorted(wanted.items())
        }

    def diff_with_files(
        self, state: RepoState, remote_files: list[RepoFile]
    ) -> dict[str, Any]:
        """对比本地状态与远端文件列表。"""
        local = state.files
        remote = {f.path: f for f in remote_files if f.is_code or f.is_binary}

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
            "added_memes": sorted(self._meme_keys_of(added)),
            "modified_memes": sorted(self._meme_keys_of(modified)),
            "removed_memes": sorted(self._meme_keys_of(removed)),
        }

    @staticmethod
    def _meme_keys_of(paths: list[str]) -> set[str]:
        keys = set()
        for path in paths:
            parts = Path(path).parts
            if parts and parts[0] == "memes" and len(parts) > 2:
                keys.add(parts[1])
            elif len(parts) > 1:
                keys.add(parts[0])
            elif parts:
                keys.add(parts[0])
        return keys

    async def check_update(self, identifier: str) -> dict[str, Any]:
        """检查单个仓库是否有更新，并给出变更文件与内容。"""
        state = self.get_repo(identifier)
        if not state:
            raise ValueError(f"仓库不存在：{identifier}")

        client = RepositoryClient(state.identifier, ref=state.ref)
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
                "meme_key": remote.meme_key,
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
        memes_dir = work_dir / "memes"
        target = memes_dir if memes_dir.is_dir() else work_dir
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
    for candidate in (work_dir / "memes" / key, work_dir / key):
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


repo_manager = RepoManager()
