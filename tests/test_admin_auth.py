"""管理面板认证接口测试。"""

from fastapi.testclient import TestClient

from meme_generator.app import create_app


def test_status_reports_uninitialized(tmp_root):
    client = TestClient(create_app(), raise_server_exceptions=False)

    response = client.get("/api/admin/status")

    assert response.status_code == 200
    body = response.json()
    assert body["initialized"] is False
    assert body["authenticated"] is False
    assert body["min_password_length"] == 8


def test_setup_then_login_and_use_token(tmp_root):
    client = TestClient(create_app(), raise_server_exceptions=False)

    setup = client.post("/api/admin/setup", json={"password": "first-password"})
    assert setup.status_code == 200
    token = setup.json()["token"]

    # 初始化后状态应变为已登录
    status = client.get(
        "/api/admin/status", headers={"Authorization": f"Bearer {token}"}
    )
    assert status.json() == {
        "initialized": True,
        "authenticated": True,
        "min_password_length": 8,
    }

    # 已初始化后不能重复 setup
    again = client.post("/api/admin/setup", json={"password": "another-password"})
    assert again.status_code == 409
    assert again.json()["error"]["code"] == "ADMIN_ALREADY_INITIALIZED"

    # 正确密码可以登录，错误密码不行
    login = client.post("/api/admin/login", json={"password": "first-password"})
    assert login.status_code == 200
    assert login.json()["token"]

    wrong = client.post("/api/admin/login", json={"password": "wrong-password"})
    assert wrong.status_code == 401
    assert wrong.json()["error"]["code"] == "ADMIN_PASSWORD_INCORRECT"


def test_short_password_is_rejected(tmp_root):
    client = TestClient(create_app(), raise_server_exceptions=False)

    response = client.post("/api/admin/setup", json={"password": "short"})

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "ADMIN_PASSWORD_TOO_WEAK"


def test_admin_routes_require_token(tmp_root):
    client = TestClient(create_app(), raise_server_exceptions=False)

    response = client.get("/api/admin/memes")

    # 尚未初始化时应提示先初始化
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "ADMIN_NOT_INITIALIZED"


def test_invalid_token_is_rejected(tmp_root):
    client = TestClient(create_app(), raise_server_exceptions=False)
    client.post("/api/admin/setup", json={"password": "first-password"})

    response = client.get(
        "/api/admin/memes", headers={"Authorization": "Bearer not-a-token"}
    )

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "TOKEN_INVALID"


def test_token_query_parameter_is_accepted(tmp_root):
    """预览图片走 <img>，无法带请求头，因此支持查询参数传令牌。"""
    client = TestClient(create_app(), raise_server_exceptions=False)
    token = client.post("/api/admin/setup", json={"password": "first-password"}).json()[
        "token"
    ]

    response = client.get(f"/api/admin/memes/google/preview?token={token}")

    assert response.status_code == 200


def test_change_password_invalidates_old_token(tmp_root):
    client = TestClient(create_app(), raise_server_exceptions=False)
    token = client.post("/api/admin/setup", json={"password": "first-password"}).json()[
        "token"
    ]
    headers = {"Authorization": f"Bearer {token}"}

    changed = client.post(
        "/api/admin/password",
        json={"old_password": "first-password", "new_password": "second-password"},
        headers=headers,
    )
    assert changed.status_code == 200
    new_token = changed.json()["token"]

    # 旧令牌应失效
    stale = client.get("/api/admin/memes", headers=headers)
    assert stale.status_code == 401

    # 新令牌可用，且新密码能登录
    assert (
        client.get(
            "/api/admin/memes", headers={"Authorization": f"Bearer {new_token}"}
        ).status_code
        == 200
    )
    assert (
        client.post(
            "/api/admin/login", json={"password": "second-password"}
        ).status_code
        == 200
    )
