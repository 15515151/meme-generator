"""内置表情与基础接口的冒烟测试。"""

from fastapi.testclient import TestClient

from meme_generator import get_meme, get_meme_keys
from meme_generator.app import create_app

from .helpers import assert_image, sample_png


def test_builtin_examples_are_registered():
    assert sorted(get_meme_keys()) == ["alike", "google"]


def test_text_meme_generates_image():
    result = get_meme("google")(texts=["Demo"])

    assert_image(result.getvalue())


def test_image_meme_generates_image():
    result = get_meme("alike")(images=[sample_png()])

    assert_image(result.getvalue())


def test_api_lists_builtin_memes():
    client = TestClient(create_app(), raise_server_exceptions=False)

    response = client.get("/memes/keys")

    assert response.status_code == 200
    assert response.json() == ["alike", "google"]


def test_api_generates_meme():
    client = TestClient(create_app(), raise_server_exceptions=False)

    response = client.post("/memes/google/", data={"texts": "API Demo"})

    assert response.status_code == 200
    assert_image(response.content)


def test_api_generates_image_meme():
    client = TestClient(create_app(), raise_server_exceptions=False)

    response = client.post(
        "/memes/alike/", files={"images": ("avatar.png", sample_png(), "image/png")}
    )

    assert response.status_code == 200
    assert_image(response.content)


def test_meme_info_and_preview():
    client = TestClient(create_app(), raise_server_exceptions=False)

    info = client.get("/memes/google/info")
    assert info.status_code == 200
    assert info.json()["params_type"]["max_texts"] == 1

    preview = client.get("/memes/google/preview")
    assert preview.status_code == 200
    assert_image(preview.content)


def test_public_api_lists_memes():
    client = TestClient(create_app(), raise_server_exceptions=False)

    response = client.get("/api/memes")

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 2
    assert {item["key"] for item in body["items"]} == {"alike", "google"}


def test_public_api_search():
    client = TestClient(create_app(), raise_server_exceptions=False)

    response = client.get("/api/memes", params={"q": "一样"})

    assert [item["key"] for item in response.json()["items"]] == ["alike"]
