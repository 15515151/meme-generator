"""仓库加速源的测试。

加速源是纯前缀：``https://mirror.example.com/`` 会把
``https://github.com/owner/repo`` 变成
``https://mirror.example.com/https://github.com/owner/repo``。

这里用 httpx.MockTransport 模拟 GitHub 的 tree / contents / codeload 三个端点，
既能验证加速地址的拼接，也能验证加速源失效时自动退回直连。
"""

import asyncio
import io
import tarfile
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from meme_generator.app import create_app
from meme_generator.config import meme_config
from meme_generator.repos import (
    RepoManager,
    RepositoryClient,
    RepoState,
    apply_proxy,
    normalize_proxy,
    split_accelerated_url,
)

from .helpers import admin_headers
from .test_admin_repos import HELLO_MEME, make_repo

PROXY = "https://mirror.example.com/"
REPO = "MemeCrafters/meme-generator-contrib"
MEME_CODE = b"from meme_generator import add_meme\n"
TREE_PAYLOAD = {
    "tree": [
        {
            "type": "blob",
            "path": "memes/hello/__init__.py",
            "sha": "0" * 40,
            "size": len(MEME_CODE),
        }
    ]
}


def build_archive(ref: str = "main") -> bytes:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as tar:
        info = tarfile.TarInfo(f"meme-generator-contrib-{ref}/memes/hello/__init__.py")
        info.size = len(MEME_CODE)
        tar.addfile(info, io.BytesIO(MEME_CODE))
    return buffer.getvalue()


def make_transport(
    calls: list[str], *, proxy_broken: bool = False, proxy_html: bool = False
) -> httpx.MockTransport:
    """模拟 GitHub 接口；``proxy_broken``/``proxy_html`` 让加速源返回坏响应。"""

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        calls.append(url)
        via_proxy = url.startswith(PROXY)
        if via_proxy and proxy_broken:
            return httpx.Response(502, text="bad gateway", request=request)
        if via_proxy and proxy_html:
            return httpx.Response(200, text="<html>proxy error</html>", request=request)
        if "/git/trees/" in url:
            return httpx.Response(200, json=TREE_PAYLOAD, request=request)
        if "/contents/" in url:
            return httpx.Response(200, content=MEME_CODE, request=request)
        if "codeload.github.com" in url:
            return httpx.Response(200, content=build_archive(), request=request)
        return httpx.Response(404, request=request)

    return httpx.MockTransport(handler)


def make_client() -> tuple[TestClient, dict[str, str]]:
    client = TestClient(create_app(), raise_server_exceptions=False)
    return client, admin_headers(client)


@pytest.fixture(autouse=True)
def restore_global_proxy():
    """全局加速源是模块级单例，测试改完要还原。"""
    original = meme_config.repo.github_proxy
    yield
    meme_config.repo.github_proxy = original


# -- 地址处理 -------------------------------------------------------------


def test_normalize_proxy_fills_scheme_and_strips_slash():
    assert normalize_proxy("mirror.example.com/") == "https://mirror.example.com"
    assert normalize_proxy(" https://ghfast.top// ") == "https://ghfast.top"
    assert normalize_proxy("  ") == ""


def test_normalize_proxy_rejects_bad_address():
    with pytest.raises(ValueError, match="加速源"):
        normalize_proxy("https://")


def test_apply_proxy_prefix_and_placeholder():
    original = f"https://github.com/{REPO}"

    assert apply_proxy(PROXY, original) == f"{PROXY}{original}"
    assert apply_proxy("", original) == original
    assert (
        apply_proxy("https://example.com/fetch/{url}", "https://api.github.com/x")
        == "https://example.com/fetch/https://api.github.com/x"
    )


def test_split_accelerated_url_recognizes_pasted_proxy():
    original = f"https://github.com/{REPO}"

    # 用户把「加速后的地址」整串粘进来
    assert split_accelerated_url(f"{PROXY}{original}") == (
        original,
        PROXY.rstrip("/"),
    )
    # 普通地址与 owner/repo 不受影响
    assert split_accelerated_url(original) == (original, "")
    assert split_accelerated_url(REPO) == (REPO, "")


# -- 客户端请求路径 -------------------------------------------------------


def test_list_files_uses_proxy_first():
    async def scenario():
        calls: list[str] = []
        client = RepositoryClient(REPO, proxy=PROXY, transport=make_transport(calls))

        files = await client.list_files()

        assert [f.path for f in files] == ["memes/hello/__init__.py"]
        assert calls == [
            f"{PROXY}https://api.github.com/repos/{REPO}/git/trees/main?recursive=1"
        ]

    asyncio.run(scenario())


def test_read_file_uses_proxy():
    async def scenario():
        calls: list[str] = []
        client = RepositoryClient(REPO, proxy=PROXY, transport=make_transport(calls))
        files = await client.list_files()

        content = await client.read_file(files[0])

        assert content == MEME_CODE
        assert calls[-1] == (
            f"{PROXY}https://api.github.com/repos/{REPO}"
            "/contents/memes/hello/__init__.py?ref=main"
        )

    asyncio.run(scenario())


def test_list_files_falls_back_to_direct_when_proxy_unavailable():
    async def scenario():
        calls: list[str] = []
        client = RepositoryClient(
            REPO, proxy=PROXY, transport=make_transport(calls, proxy_broken=True)
        )

        files = await client.list_files()

        assert [f.path for f in files] == ["memes/hello/__init__.py"]
        assert len(calls) == 2
        assert calls[1].startswith("https://api.github.com/repos/")

    asyncio.run(scenario())


def test_read_file_ignores_proxy_html_error_page():
    async def scenario():
        calls: list[str] = []
        client = RepositoryClient(
            REPO, proxy=PROXY, transport=make_transport(calls, proxy_html=True)
        )
        files = await client.list_files()

        content = await client.read_file(files[0])

        assert content == MEME_CODE
        assert calls[-1].startswith("https://api.github.com/repos/")

    asyncio.run(scenario())


def test_archive_falls_back_when_proxy_returns_html():
    async def scenario():
        calls: list[str] = []
        client = RepositoryClient(
            REPO, proxy=PROXY, transport=make_transport(calls, proxy_html=True)
        )
        collected: dict[str, bytes] = {}

        await client.extract_archive(
            lambda path, content: collected.__setitem__(path, content)
        )

        assert collected == {"memes/hello/__init__.py": MEME_CODE}
        assert calls[0].startswith(PROXY)
        assert calls[1].startswith("https://codeload.github.com/")

    asyncio.run(scenario())


# -- 加速源的生效规则 -----------------------------------------------------


def test_effective_proxy_prefers_repo_setting_over_global():
    manager = RepoManager()
    meme_config.repo.github_proxy = "https://ghfast.top/"
    state = RepoState(identifier="owner/repo")

    assert manager.effective_proxy(state) == "https://ghfast.top"
    assert (
        manager.accelerated_url(state)
        == "https://ghfast.top/https://github.com/owner/repo"
    )

    state.proxy = "https://mirror.example.com"

    assert manager.effective_proxy(state) == "https://mirror.example.com"
    assert (
        manager.accelerated_url(state)
        == "https://mirror.example.com/https://github.com/owner/repo"
    )


def test_local_repo_never_uses_proxy():
    manager = RepoManager()
    meme_config.repo.github_proxy = "https://ghfast.top/"
    state = RepoState(identifier="/tmp/local-repo", proxy="https://mirror.example.com")

    assert manager.effective_proxy(state) == ""
    assert manager.accelerated_url(state) == "/tmp/local-repo"


# -- 管理接口 -------------------------------------------------------------


def test_global_proxy_can_be_set_and_cleared(config_file):
    client, headers = make_client()

    response = client.patch(
        "/api/admin/settings",
        json={"github_proxy": "mirror.example.com/"},
        headers=headers,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["repo"]["github_proxy"] == "https://mirror.example.com"
    assert body["repo"]["effective_proxy"] == "https://mirror.example.com"
    assert "mirror.example.com" in config_file.read_text(encoding="utf-8")

    cleared = client.patch(
        "/api/admin/settings", json={"github_proxy": ""}, headers=headers
    )
    assert cleared.status_code == 200
    assert cleared.json()["repo"]["effective_proxy"] == ""


def test_invalid_global_proxy_is_rejected():
    client, headers = make_client()

    response = client.patch(
        "/api/admin/settings", json={"github_proxy": "https://"}, headers=headers
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_proxy_presets_are_listed():
    client, headers = make_client()

    body = client.get("/api/admin/repos/proxies", headers=headers).json()

    assert body["default"] == ""
    assert "https://ghfast.top" in body["items"]


def test_proxy_test_rejects_invalid_proxy():
    client, headers = make_client()

    response = client.post(
        "/api/admin/repos/proxy-test", json={"proxy": "https://"}, headers=headers
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_repo_proxy_can_be_set_and_persisted(tmp_path):
    client, headers = make_client()
    repo = make_repo(tmp_path / "repo", {"memes/hello/__init__.py": HELLO_MEME})
    created = client.post(
        "/api/admin/repos", json={"url": repo}, headers=headers
    ).json()
    identifier = created["identifier"]
    # 本地仓库不套加速源
    assert created["proxy"] == ""
    assert created["effective_proxy"] == ""

    response = client.patch(
        f"/api/admin/repos/{identifier}",
        json={"proxy": "mirror.example.com/", "name": "带加速源的仓库"},
        headers=headers,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["proxy"] == "https://mirror.example.com"
    assert body["display_name"] == "带加速源的仓库"
    assert body["effective_proxy"] == ""

    listed = client.get("/api/admin/repos", headers=headers).json()["items"][0]
    assert listed["proxy"] == "https://mirror.example.com"

    # 清空后跟随全局默认
    client.patch("/api/admin/settings", json={"github_proxy": ""}, headers=headers)
    cleared = client.patch(
        f"/api/admin/repos/{identifier}", json={"proxy": ""}, headers=headers
    ).json()
    assert cleared["proxy"] == ""


def test_repo_proxy_setting_validates_address(tmp_path):
    client, headers = make_client()
    repo = make_repo(tmp_path / "repo", {"memes/hello/__init__.py": HELLO_MEME})
    identifier = client.post(
        "/api/admin/repos", json={"url": repo}, headers=headers
    ).json()["identifier"]

    response = client.patch(
        f"/api/admin/repos/{identifier}", json={"proxy": "https://"}, headers=headers
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_repo_state_keeps_proxy_across_reload(tmp_path):
    client, headers = make_client()
    repo = make_repo(tmp_path / "repo", {"memes/hello/__init__.py": HELLO_MEME})
    identifier = client.post(
        "/api/admin/repos", json={"url": repo}, headers=headers
    ).json()["identifier"]
    client.patch(
        f"/api/admin/repos/{identifier}",
        json={"proxy": "https://mirror.example.com/"},
        headers=headers,
    )

    from meme_generator.repos import repo_manager

    # 丢掉内存缓存后重新读盘，加速源仍然在
    repo_manager.invalidate()
    state = repo_manager.get_repo(identifier)

    assert state is not None
    assert state.proxy == "https://mirror.example.com"
    assert Path(repo_manager.work_dir(identifier)).is_dir()
