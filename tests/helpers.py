"""测试共用工具。"""

from io import BytesIO

from PIL import Image


def sample_png(size: tuple[int, int] = (96, 96), color: str = "orange") -> bytes:
    output = BytesIO()
    Image.new("RGB", size, color).save(output, format="PNG")
    return output.getvalue()


def assert_image(content: bytes) -> None:
    Image.open(BytesIO(content)).verify()


def admin_headers(client, password: str = "test-password-123") -> dict[str, str]:
    """首次调用时初始化管理员并返回带令牌的请求头。"""
    response = client.post("/api/admin/setup", json={"password": password})
    if response.status_code != 200:
        response = client.post("/api/admin/login", json={"password": password})
    token = response.json()["token"]
    return {"Authorization": f"Bearer {token}"}
