import os
import tempfile
from io import BytesIO
from pathlib import Path

os.environ["MEME_GENERATOR_CONFIG_FILE"] = str(
    Path(tempfile.gettempdir()) / "meme-generator-test-config.toml"
)
Path(os.environ["MEME_GENERATOR_CONFIG_FILE"]).write_text("", encoding="utf-8")

from fastapi.testclient import TestClient
from PIL import Image

from meme_generator import get_meme, get_meme_keys
from meme_generator.app import create_app


def sample_png() -> bytes:
    output = BytesIO()
    Image.new("RGB", (96, 96), "orange").save(output, format="PNG")
    return output.getvalue()


def assert_image(content: bytes) -> None:
    image = Image.open(BytesIO(content))
    image.verify()


def test_builtin_examples_are_registered():
    assert sorted(get_meme_keys()) == ["alike", "google"]


def test_text_meme_generates_image():
    result = get_meme("google")(texts=["Demo"])

    assert_image(result.getvalue())


def test_image_meme_generates_image():
    result = get_meme("alike")(images=[sample_png()])

    assert_image(result.getvalue())


def test_api_lists_builtin_memes():
    client = TestClient(create_app())

    response = client.get("/memes/keys")

    assert response.status_code == 200
    assert response.json() == ["alike", "google"]
