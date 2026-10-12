"""设置接口与预览回退的测试。"""

from fastapi.testclient import TestClient

from meme_generator import get_meme
from meme_generator.app import create_app
from meme_generator.utils import random_image

from .helpers import admin_headers, assert_image


def make_client() -> tuple[TestClient, dict[str, str]]:
    client = TestClient(create_app(), raise_server_exceptions=False)
    return client, admin_headers(client)


# -- 设置接口 -------------------------------------------------------------


def test_settings_default_api_domain_is_empty():
    client, headers = make_client()

    response = client.get("/api/admin/settings", headers=headers)

    assert response.status_code == 200
    body = response.json()
    assert body["server"]["api_domain"] == ""
    assert body["server"]["port"] == 2233
    assert body["config_file"]


def test_api_domain_can_be_set_and_persists(config_file):
    client, headers = make_client()

    response = client.patch(
        "/api/admin/settings",
        json={"api_domain": "https://meme.example.com/"},
        headers=headers,
    )

    assert response.status_code == 200
    # 末尾斜杠会被去掉
    assert response.json()["server"]["api_domain"] == "https://meme.example.com"
    assert "meme.example.com" in config_file.read_text(encoding="utf-8")

    # 重新读取仍然是配置后的值
    assert (
        client.get("/api/admin/settings", headers=headers).json()["server"][
            "api_domain"
        ]
        == "https://meme.example.com"
    )


def test_api_domain_can_be_cleared():
    client, headers = make_client()
    client.patch(
        "/api/admin/settings",
        json={"api_domain": "https://a.example.com"},
        headers=headers,
    )

    response = client.patch(
        "/api/admin/settings", json={"api_domain": ""}, headers=headers
    )

    assert response.status_code == 200
    assert response.json()["server"]["api_domain"] == ""


def test_api_domain_requires_scheme():
    client, headers = make_client()

    response = client.patch(
        "/api/admin/settings", json={"api_domain": "meme.example.com"}, headers=headers
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_settings_requires_admin():
    client = TestClient(create_app(), raise_server_exceptions=False)

    assert client.get("/api/admin/settings").status_code == 403


# -- 预览回退 -------------------------------------------------------------


def test_generate_preview_succeeds_for_every_builtin_meme():
    """内置表情都应能生成预览，不应有永久失败的。"""
    from meme_generator import get_meme_keys

    for key in get_meme_keys():
        result = get_meme(key).generate_preview()
        assert_image(result.getvalue())


def test_preview_truncates_over_long_default_text():
    """默认文本超限的表情应截断后出图，而不是抛 TextOverLength。"""
    from datetime import datetime

    from pil_utils import BuildImage

    from meme_generator import add_meme
    from meme_generator.exception import TextOverLength

    def picky(images, texts: list[str], args):
        # 模仿第三方仓库里限制渲染高度的写法
        if len(texts[0]) > 4:
            raise TextOverLength(texts[0])
        frame = BuildImage.new("RGB", (200, 100), "white")
        frame.draw_text((10, 10, 190, 90), texts[0], max_fontsize=28)
        return frame.save_jpg()

    add_meme(
        "picky_preview_test",
        picky,
        min_texts=1,
        max_texts=1,
        default_texts=["这是一段很长的默认文本"],
        keywords=["picky-preview-test"],
        date_created=datetime(2026, 1, 1),
    )

    try:
        # 直接用超长文本调用会失败，说明限制确实生效
        try:
            get_meme("picky_preview_test")(images=[], texts=["这是一段很长的默认文本"])
            raise AssertionError("expected TextOverLength")
        except TextOverLength:
            pass

        # 但预览应通过截断成功出图
        result = get_meme("picky_preview_test").generate_preview()
        assert_image(result.getvalue())
    finally:
        from meme_generator.manager import _meme_sources, _memes

        _memes.pop("picky_preview_test", None)
        _meme_sources.pop("picky_preview_test", None)


def test_preview_falls_back_when_truncation_is_not_enough():
    """连单字都放不下时应退回 ASCII 占位，保证预览一定能出图。"""
    from datetime import datetime

    from pil_utils import BuildImage

    from meme_generator import add_meme
    from meme_generator.exception import TextOverLength

    def cjk_only(images, texts: list[str], args):
        # 只接受 ASCII，模拟文本区域过窄的表情
        if not texts[0].isascii():
            raise TextOverLength(texts[0])
        frame = BuildImage.new("RGB", (160, 80), "white")
        frame.draw_text((8, 8, 152, 72), texts[0], max_fontsize=24)
        return frame.save_jpg()

    add_meme(
        "ascii_only_preview_test",
        cjk_only,
        min_texts=1,
        max_texts=1,
        default_texts=["纯中文"],
        keywords=["ascii-only-preview-test"],
        date_created=datetime(2026, 1, 1),
    )

    try:
        result = get_meme("ascii_only_preview_test").generate_preview()
        assert_image(result.getvalue())
    finally:
        from meme_generator.manager import _meme_sources, _memes

        _memes.pop("ascii_only_preview_test", None)
        _meme_sources.pop("ascii_only_preview_test", None)


def test_admin_preview_reports_failure_only_when_unrecoverable():
    """正常表情的管理端预览不应返回错误。"""
    client, headers = make_client()

    response = client.get("/api/admin/memes/google/preview", headers=headers)

    assert response.status_code == 200
    assert_image(response.content)


def test_preview_uses_random_image_for_image_memes():
    """需要图片的表情用随机图生成预览，不应因为缺图而失败。"""
    meme = get_meme("alike")

    result = meme.generate_preview()

    assert_image(result.getvalue())
    # 随机图来自 utils，确认参数确实提供了图片
    assert meme.params_type.min_images == 1
    assert len(random_image()) > 0
