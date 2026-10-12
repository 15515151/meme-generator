"""外部仓库与更新检查接口测试。

用本地目录当仓库，既能覆盖下载/安装/更新逻辑，又不依赖网络。
"""

from pathlib import Path

from fastapi.testclient import TestClient

from meme_generator.app import create_app

from .helpers import admin_headers

HELLO_MEME = """
from datetime import datetime

from pil_utils import BuildImage

from meme_generator import add_meme


def hello(images, texts: list[str], args):
    frame = BuildImage.new("RGB", (300, 120), "white")
    frame.draw_text((10, 10, 290, 110), texts[0] if texts else "hello", max_fontsize=50)
    return frame.save_jpg()


add_meme(
    "hello",
    hello,
    min_texts=1,
    max_texts=1,
    default_texts=["hello"],
    keywords=["打招呼"],
    date_created=datetime(2026, 1, 1),
)
"""

BYE_MEME = """
from datetime import datetime

from pil_utils import BuildImage

from meme_generator import add_meme


def bye(images, texts: list[str], args):
    frame = BuildImage.new("RGB", (300, 120), "black")
    frame.draw_text((10, 10, 290, 110), texts[0] if texts else "bye", max_fontsize=50, fill="white")
    return frame.save_jpg()


add_meme(
    "bye",
    bye,
    min_texts=1,
    max_texts=1,
    default_texts=["bye"],
    keywords=["再见"],
    date_created=datetime(2026, 2, 1),
)
"""


def make_repo(root: Path, files: dict[str, str]) -> str:
    """在临时目录里搭一个假仓库。"""
    for rel, content in files.items():
        target = root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    return str(root)


def make_client() -> tuple[TestClient, dict[str, str]]:
    client = TestClient(create_app(), raise_server_exceptions=False)
    return client, admin_headers(client)


def test_add_local_repo_loads_memes(tmp_path):
    client, headers = make_client()
    repo = make_repo(tmp_path / "repo", {"memes/hello/__init__.py": HELLO_MEME})

    response = client.post("/api/admin/repos", json={"url": repo}, headers=headers)

    assert response.status_code == 201
    body = response.json()
    assert body["meme_keys"] == ["hello"]
    assert body["meme_count"] == 1

    # 新表情立刻可用，无需重启
    assert "hello" in client.get("/memes/keys").json()
    assert client.get("/memes/hello/info").status_code == 200
    assert client.post("/memes/hello/", data={"texts": "你好"}).status_code == 200


def test_added_meme_is_attributed_to_repo(tmp_path):
    client, headers = make_client()
    repo = make_repo(tmp_path / "repo", {"memes/hello/__init__.py": HELLO_MEME})
    client.post("/api/admin/repos", json={"url": repo}, headers=headers)

    listing = client.get("/api/admin/memes", headers=headers).json()

    hello = next(item for item in listing["items"] if item["key"] == "hello")
    assert hello["source"].startswith("repo:")
    assert "builtin" in listing["sources"]


def test_duplicate_repo_is_rejected(tmp_path):
    client, headers = make_client()
    repo = make_repo(tmp_path / "repo", {"memes/hello/__init__.py": HELLO_MEME})
    client.post("/api/admin/repos", json={"url": repo}, headers=headers)

    response = client.post("/api/admin/repos", json={"url": repo}, headers=headers)

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "REPO_ALREADY_EXISTS"


def test_missing_repo_is_reported(tmp_path):
    client, headers = make_client()

    response = client.post(
        "/api/admin/repos",
        json={"url": str(tmp_path / "does-not-exist")},
        headers=headers,
    )

    assert response.status_code in (400, 502)


def test_update_detects_new_and_modified_files(tmp_path):
    client, headers = make_client()
    root = tmp_path / "repo"
    repo = make_repo(root, {"memes/hello/__init__.py": HELLO_MEME})
    installed = client.post(
        "/api/admin/repos", json={"url": repo}, headers=headers
    ).json()
    identifier = installed["identifier"]

    # 新增一个表情，并修改已有表情
    make_repo(root, {"memes/bye/__init__.py": BYE_MEME})
    (root / "memes/hello/__init__.py").write_text(
        HELLO_MEME + "\n# changed\n", encoding="utf-8"
    )

    response = client.get(
        "/api/admin/updates/check", params={"identifier": identifier}, headers=headers
    )

    assert response.status_code == 200
    body = response.json()
    assert body["has_update"] is True
    assert body["changes"]["added"] == ["memes/bye/__init__.py"]
    assert body["changes"]["modified"] == ["memes/hello/__init__.py"]
    assert body["changes"]["added_memes"] == ["bye"]
    assert body["changes"]["modified_memes"] == ["hello"]

    # 变更文件按表情归类，并带上代码内容供下游取用
    added_file = next(f for f in body["files"] if f["status"] == "added")
    assert added_file["meme_key"] == "bye"
    assert added_file["kind"] == "code"
    assert "add_meme" in added_file["content"]


def test_update_applies_changes(tmp_path):
    client, headers = make_client()
    root = tmp_path / "repo"
    repo = make_repo(root, {"memes/hello/__init__.py": HELLO_MEME})
    identifier = client.post(
        "/api/admin/repos", json={"url": repo}, headers=headers
    ).json()["identifier"]

    make_repo(root, {"memes/bye/__init__.py": BYE_MEME})

    response = client.post(
        f"/api/admin/repos/{identifier}/update", json={"apply": True}, headers=headers
    )

    assert response.status_code == 200
    assert response.json()["applied"] is True
    assert response.json()["changes"]["added_memes"] == ["bye"]
    assert "bye" in client.get("/memes/keys").json()


def test_update_without_changes(tmp_path):
    client, headers = make_client()
    repo = make_repo(tmp_path / "repo", {"memes/hello/__init__.py": HELLO_MEME})
    identifier = client.post(
        "/api/admin/repos", json={"url": repo}, headers=headers
    ).json()["identifier"]

    response = client.post(
        f"/api/admin/repos/{identifier}/update", json={"apply": True}, headers=headers
    )

    assert response.status_code == 200
    assert response.json()["has_update"] is False


def test_uninstall_removes_memes(tmp_path):
    client, headers = make_client()
    repo = make_repo(tmp_path / "repo", {"memes/hello/__init__.py": HELLO_MEME})
    identifier = client.post(
        "/api/admin/repos", json={"url": repo}, headers=headers
    ).json()["identifier"]
    assert "hello" in client.get("/memes/keys").json()

    response = client.delete(f"/api/admin/repos/{identifier}", headers=headers)

    assert response.status_code == 200
    assert response.json()["removed_memes"] == ["hello"]
    assert "hello" not in client.get("/memes/keys").json()
    assert client.get("/api/admin/repos", headers=headers).json()["total"] == 0


def test_public_repo_and_update_endpoints(tmp_path):
    client, headers = make_client()
    root = tmp_path / "repo"
    repo = make_repo(root, {"memes/hello/__init__.py": HELLO_MEME})
    client.post("/api/admin/repos", json={"url": repo}, headers=headers)

    repos = client.get("/api/repos")
    assert repos.status_code == 200
    assert repos.json()["total"] == 1
    assert repos.json()["items"][0]["meme_keys"] == ["hello"]

    # 无更新时
    updates = client.get("/api/updates")
    assert updates.status_code == 200
    assert updates.json()["updated"] == 0

    # 有更新时，公开接口也应反馈
    make_repo(root, {"memes/bye/__init__.py": BYE_MEME})
    updates = client.get("/api/updates", params={"include_content": True})
    body = updates.json()
    assert body["updated"] == 1
    files = body["results"][0]["files"]
    assert any(f["path"] == "memes/bye/__init__.py" for f in files)
    assert all("content" in f for f in files)

    # 不请求内容时不应返回 content，减小响应体积
    lean = client.get("/api/updates").json()
    assert all("content" not in f for f in lean["results"][0]["files"])

    # 单表情更新详情
    detail = client.get("/api/updates/bye")
    assert detail.status_code == 200
    assert detail.json()["meme_key"] == "bye"
    assert detail.json()["has_update"] is True
    assert detail.json()["installed"] is False


def test_meme_updates_grouped_by_meme(tmp_path):
    client, headers = make_client()
    root = tmp_path / "repo"
    repo = make_repo(root, {"memes/hello/__init__.py": HELLO_MEME})
    client.post("/api/admin/repos", json={"url": repo}, headers=headers)

    make_repo(root, {"memes/bye/__init__.py": BYE_MEME})

    response = client.get("/api/admin/updates/memes", headers=headers)

    assert response.status_code == 200
    body = response.json()
    bye = next(item for item in body["items"] if item["meme_key"] == "bye")
    assert bye["status"] == "new"
    assert bye["installed"] is False
    assert bye["code_files"] == 1


def test_check_all_updates(tmp_path):
    client, headers = make_client()
    repo = make_repo(tmp_path / "repo", {"memes/hello/__init__.py": HELLO_MEME})
    client.post("/api/admin/repos", json={"url": repo}, headers=headers)

    response = client.get("/api/admin/updates/check-all", headers=headers)

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["updated"] == 0


def test_unknown_repo_returns_404():
    client, headers = make_client()

    assert (
        client.delete("/api/admin/repos/not-a-repo", headers=headers).status_code == 404
    )
    assert (
        client.get(
            "/api/admin/updates/check",
            params={"identifier": "not-a-repo"},
            headers=headers,
        ).status_code
        == 404
    )


def test_repo_url_normalization():
    from meme_generator.repos import normalize_repo_url

    assert normalize_repo_url("https://github.com/owner/repo") == "owner/repo"
    assert normalize_repo_url("https://github.com/owner/repo/") == "owner/repo"
    assert normalize_repo_url("https://github.com/owner/repo.git") == "owner/repo"
    assert normalize_repo_url("owner/repo") == "owner/repo"
    assert normalize_repo_url("git@github.com:owner/repo.git") == "owner/repo"
