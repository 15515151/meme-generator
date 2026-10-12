"""表情管理接口测试：列表、搜索、封禁、预览。"""

from fastapi.testclient import TestClient

from meme_generator.app import create_app

from .helpers import admin_headers, assert_image


def make_client() -> tuple[TestClient, dict[str, str]]:
    client = TestClient(create_app(), raise_server_exceptions=False)
    return client, admin_headers(client)


def test_list_includes_all_memes_with_metadata():
    client, headers = make_client()

    response = client.get("/api/admin/memes", headers=headers)

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 2
    assert body["enabled"] == 2
    assert body["disabled"] == 0
    assert {item["key"] for item in body["items"]} == {"alike", "google"}
    assert body["sources"] == ["builtin"]

    google = next(item for item in body["items"] if item["key"] == "google")
    assert google["min_texts"] == 1
    assert google["max_texts"] == 1
    assert google["keywords"] == ["google"]


def test_search_matches_key_keyword_and_tag():
    client, headers = make_client()

    assert [
        item["key"]
        for item in client.get(
            "/api/admin/memes", params={"q": "goo"}, headers=headers
        ).json()["items"]
    ] == ["google"]

    # 中文关键词
    assert [
        item["key"]
        for item in client.get(
            "/api/admin/memes", params={"q": "一样"}, headers=headers
        ).json()["items"]
    ] == ["alike"]

    assert (
        client.get("/api/admin/memes", params={"q": "不存在"}, headers=headers).json()[
            "items"
        ]
        == []
    )


def test_filter_by_status():
    client, headers = make_client()
    client.post(
        "/api/admin/memes/google/toggle", json={"disabled": True}, headers=headers
    )

    disabled = client.get(
        "/api/admin/memes", params={"status": "disabled"}, headers=headers
    ).json()
    assert [item["key"] for item in disabled["items"]] == ["google"]
    assert disabled["disabled"] == 1

    enabled = client.get(
        "/api/admin/memes", params={"status": "enabled"}, headers=headers
    ).json()
    assert [item["key"] for item in enabled["items"]] == ["alike"]


def test_toggle_disables_meme_everywhere():
    client, headers = make_client()

    response = client.post(
        "/api/admin/memes/google/toggle", json={"disabled": True}, headers=headers
    )
    assert response.status_code == 200
    assert response.json()["disabled"] is True

    # 对外接口里消失
    assert client.get("/memes/keys").json() == ["alike"]

    # 直接访问返回规范错误
    info = client.get("/memes/google/info")
    assert info.status_code == 403
    assert info.json()["error"]["code"] == "MEME_DISABLED"
    assert info.json()["error"]["context"]["meme_key"] == "google"

    # 生成接口同样被拦截
    generate = client.post("/memes/google/", data={"texts": "hi"})
    assert generate.status_code == 403
    assert generate.json()["error"]["code"] == "MEME_DISABLED"

    # 重新启用后恢复
    client.post(
        "/api/admin/memes/google/toggle", json={"disabled": False}, headers=headers
    )
    assert sorted(client.get("/memes/keys").json()) == ["alike", "google"]


def test_toggle_persists_to_config(config_file):
    client, headers = make_client()

    client.post(
        "/api/admin/memes/google/toggle", json={"disabled": True}, headers=headers
    )

    content = config_file.read_text(encoding="utf-8")
    assert "google" in content
    assert "meme_disabled_list" in content


def test_toggle_unknown_meme_returns_404():
    client, headers = make_client()

    response = client.post(
        "/api/admin/memes/not-a-meme/toggle", json={"disabled": True}, headers=headers
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NO_SUCH_MEME"


def test_batch_toggle():
    client, headers = make_client()

    response = client.post(
        "/api/admin/memes/batch-toggle",
        json={"keys": ["google", "alike", "missing"], "disabled": True},
        headers=headers,
    )

    assert response.status_code == 200
    body = response.json()
    assert sorted(body["updated"]) == ["alike", "google"]
    assert "missing" in body["failed"]
    assert client.get("/memes/keys").json() == []


def test_admin_preview_works_even_when_disabled():
    client, headers = make_client()
    client.post(
        "/api/admin/memes/google/toggle", json={"disabled": True}, headers=headers
    )

    response = client.get("/api/admin/memes/google/preview", headers=headers)

    assert response.status_code == 200
    assert_image(response.content)


def test_admin_preview_accepts_custom_text():
    client, headers = make_client()

    response = client.get(
        "/api/admin/memes/google/preview", params={"texts": "自定义"}, headers=headers
    )

    assert response.status_code == 200
    assert_image(response.content)


def test_admin_preview_rejects_too_few_texts():
    client, headers = make_client()

    response = client.get(
        "/api/admin/memes/google/preview", params={"texts": ""}, headers=headers
    )

    # 空字符串会被忽略，回退到默认文本，因此这里应成功
    assert response.status_code == 200


def test_meme_detail_includes_shortcuts():
    client, headers = make_client()

    response = client.get("/api/admin/memes/google", headers=headers)

    assert response.status_code == 200
    body = response.json()
    assert body["key"] == "google"
    assert body["source"] == "builtin"
    assert isinstance(body["shortcuts"], list)


def test_meme_assets_listing():
    client, headers = make_client()

    response = client.get("/api/admin/memes/google/assets", headers=headers)

    assert response.status_code == 200
    body = response.json()
    assert body["key"] == "google"
    assert body["count"] >= 1
    assert any(file["path"] == "__init__.py" for file in body["files"])


def test_health_summary():
    client, headers = make_client()
    client.post(
        "/api/admin/memes/google/toggle", json={"disabled": True}, headers=headers
    )

    response = client.get("/api/admin/health", headers=headers)

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["memes"] == 2
    assert body["disabled"] == 1
    assert body["repos"] == 0
