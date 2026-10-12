"""错误响应格式测试。

所有错误都应返回统一结构，方便调用方按 code 分支处理。
"""

from fastapi.testclient import TestClient

from meme_generator.app import create_app

from .helpers import admin_headers


def assert_error_shape(body: dict, code: str | None = None) -> None:
    """校验 {error: {code, message, status_code}, detail} 结构。"""
    assert "error" in body
    error = body["error"]
    assert isinstance(error["code"], str)
    assert error["code"]
    assert isinstance(error["message"], str)
    assert error["message"]
    assert isinstance(error["status_code"], int)
    # detail 与历史响应保持一致
    assert body["detail"] == error["message"]
    if code is not None:
        assert error["code"] == code


def test_unknown_meme_error():
    client = TestClient(create_app(), raise_server_exceptions=False)

    response = client.get("/memes/not-a-meme/info")

    assert response.status_code == 531
    assert_error_shape(response.json(), "NO_SUCH_MEME")
    assert response.json()["error"]["context"]["meme_key"] == "not-a-meme"


def test_unknown_route_error():
    client = TestClient(create_app(), raise_server_exceptions=False)

    response = client.get("/memes/not-a-meme/not-a-route")

    assert response.status_code == 404
    assert_error_shape(response.json(), "NOT_FOUND")


def test_meme_generation_param_errors():
    client = TestClient(create_app(), raise_server_exceptions=False)

    # alike 需要 1 张图片，不传应报数量不符
    response = client.post("/memes/alike/", data={"texts": "x"})

    assert response.status_code == 541
    assert_error_shape(response.json(), "IMAGE_NUMBER_MISMATCH")
    assert response.json()["error"]["context"]["min_images"] == 1


def test_too_many_texts_error():
    client = TestClient(create_app(), raise_server_exceptions=False)

    response = client.post("/memes/google/", data={"texts": ["a", "b"]})

    assert response.status_code == 542
    assert_error_shape(response.json(), "TEXT_NUMBER_MISMATCH")


def test_invalid_image_data_error():
    client = TestClient(create_app(), raise_server_exceptions=False)

    response = client.post(
        "/memes/alike/", files={"images": ("bad.png", b"not-an-image", "image/png")}
    )

    assert response.status_code == 533
    assert_error_shape(response.json(), "OPEN_IMAGE_FAILED")


def test_validation_error_shape():
    client = TestClient(create_app(), raise_server_exceptions=False)

    # render_list 的 meme_list 元素结构不合法
    response = client.post("/memes/render_list", json={"meme_list": [{"nope": 1}]})

    assert response.status_code == 422
    body = response.json()
    assert_error_shape(body, "VALIDATION_ERROR")
    assert "errors" in body["error"]["context"]


def test_admin_auth_errors_are_shaped():
    client = TestClient(create_app(), raise_server_exceptions=False)

    # 未初始化
    assert_error_shape(client.get("/api/admin/memes").json(), "ADMIN_NOT_INITIALIZED")

    headers = admin_headers(client, password="shaped-error-password")

    # 缺失令牌
    assert_error_shape(
        client.get("/api/admin/memes", headers={"Authorization": "Bearer"}).json(),
        "UNAUTHORIZED",
    )

    # 无效令牌
    assert_error_shape(
        client.get("/api/admin/memes", headers={"Authorization": "Bearer junk"}).json(),
        "TOKEN_INVALID",
    )

    # 不存在的表情
    assert_error_shape(
        client.post(
            "/api/admin/memes/missing/toggle", json={"disabled": True}, headers=headers
        ).json(),
        "NO_SUCH_MEME",
    )
