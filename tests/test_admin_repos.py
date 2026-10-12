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


# -- 表情目录探测 ---------------------------------------------------------


def test_detect_meme_dir_prefers_common_names():
    from meme_generator.repos import detect_meme_dir

    # memes/ 约定
    assert (
        detect_meme_dir(
            ["memes/alpha/__init__.py", "memes/beta/__init__.py", "README.md"]
        )
        == "memes"
    )

    # emoji/ 约定（如 anyliew/meme_emoji）
    assert (
        detect_meme_dir(
            ["emoji/alpha/__init__.py", "emoji/beta/__init__.py", "docs/a.png"]
        )
        == "emoji"
    )

    # 根目录直接放表情
    assert detect_meme_dir(["alpha/__init__.py", "beta/__init__.py"]) == ""

    # 有干扰目录时，取表情数量最多的那个
    assert (
        detect_meme_dir(
            [
                "memes/a/__init__.py",
                "memes/b/__init__.py",
                "memes/c/__init__.py",
                "docs/d/__init__.py",
            ]
        )
        == "memes"
    )

    assert detect_meme_dir([]) == ""


def test_install_repo_under_emoji_dir(tmp_path):
    """表情放在 emoji/ 下的仓库也要能正确加载。"""
    client, headers = make_client()
    root = tmp_path / "repo"
    repo = make_repo(root, {"emoji/hello/__init__.py": HELLO_MEME})

    response = client.post("/api/admin/repos", json={"url": repo}, headers=headers)

    assert response.status_code == 201
    body = response.json()
    assert body["meme_dir"] == "emoji"
    assert body["meme_keys"] == ["hello"]
    # 不应把 emoji 目录本身当成表情 key
    assert "emoji" not in body["meme_keys"]
    assert "hello" in client.get("/memes/keys").json()


def test_preview_detects_layout(tmp_path):
    client, headers = make_client()
    repo = make_repo(
        tmp_path / "repo",
        {"emoji/alpha/__init__.py": HELLO_MEME, "emoji/beta/__init__.py": HELLO_MEME},
    )

    response = client.post(
        "/api/admin/repos/preview", json={"url": repo}, headers=headers
    )

    assert response.status_code == 200
    body = response.json()
    assert body["meme_dir"] == "emoji"
    assert body["meme_count"] == 2
    assert sorted(body["meme_keys"]) == ["alpha", "beta"]
    assert body["installed"] is False


def test_presets_endpoint():
    client, headers = make_client()

    response = client.get("/api/admin/repos/presets", headers=headers)

    assert response.status_code == 200
    items = response.json()["items"]
    assert len(items) >= 4
    identifiers = {item["identifier"] for item in items}
    assert "MemeCrafters/meme-generator-contrib" in identifiers
    assert "anyliew/meme_emoji" in identifiers
    # 都没装过
    assert all(item["installed"] is False for item in items)

    # 仓库命名与分支来自配置
    jj = next(
        item for item in items if item["identifier"] == "jinjiao007/meme-generator-jj"
    )
    assert jj["branch"] == "master"
    assert jj["name"] == "jinjiao007的仓库"


def test_preset_install_reports_remaining(tmp_path):
    client, headers = make_client()
    repo = make_repo(tmp_path / "repo", {"memes/hello/__init__.py": HELLO_MEME})
    client.post("/api/admin/repos", json={"url": repo}, headers=headers)

    items = client.get("/api/admin/repos/presets", headers=headers).json()["items"]

    # 自定义仓库不影响内置预设的状态
    assert all(item["installed"] is False for item in items)


def test_repo_name_can_be_customized(tmp_path):
    client, headers = make_client()
    repo = make_repo(tmp_path / "repo", {"memes/hello/__init__.py": HELLO_MEME})

    response = client.post(
        "/api/admin/repos",
        json={"url": repo, "name": "我的表情仓库", "ref": "main"},
        headers=headers,
    )

    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "我的表情仓库"
    assert body["display_name"] == "我的表情仓库"


def test_sync_ignores_non_meme_files(tmp_path):
    """只同步代码与图片，忽略点文件、缓存等无关内容。"""
    client, headers = make_client()
    root = tmp_path / "repo"
    repo = make_repo(
        root,
        {
            "memes/hello/__init__.py": HELLO_MEME,
            ".github/workflows/ci.yml": "name: ci\n",
            "memes/hello/__pycache__/x.pyc": "junk",
            "notes.txt": "notes",
        },
    )

    response = client.post("/api/admin/repos", json={"url": repo}, headers=headers)

    assert response.status_code == 201
    files = response.json()
    recorded = client.get("/api/admin/repos", headers=headers).json()["items"][0]
    assert recorded["file_count"] < 4
    assert files["meme_count"] == 1
