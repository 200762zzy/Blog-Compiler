import base64

import pytest

import http_client
import image_base64
from image_base64 import embed_images, read_image_bytes, to_data_uri

PNG_BYTES = b"\x89PNG\r\n\x1a\n fake image body"


@pytest.fixture
def image(work_dir):
    path = work_dir / "shot.png"
    path.write_bytes(PNG_BYTES)
    return path


class FakeResponse:
    def __init__(self, content=b"", status_code=200):
        self.content = content
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class TestReadImageBytes:
    def test_reads_local_file(self, image):
        assert read_image_bytes(str(image)) == PNG_BYTES

    def test_missing_local_path_raises(self, work_dir):
        with pytest.raises(FileNotFoundError):
            read_image_bytes(str(work_dir / "nope.png"))

    def test_downloads_remote_image(self, monkeypatch):
        seen = {}
        monkeypatch.setattr(
            http_client,
            "get",
            lambda url=None, **kw: seen.update(url=url, kw=kw) or FakeResponse(b"remote"),
        )
        assert read_image_bytes("https://example.com/a.png") == b"remote"
        assert seen["url"] == "https://example.com/a.png"
        assert seen["kw"]["follow_redirects"] is True

    def test_remote_error_propagates(self, monkeypatch):
        monkeypatch.setattr(
            http_client, "get", lambda url=None, **kw: FakeResponse(status_code=404)
        )
        with pytest.raises(RuntimeError, match="404"):
            read_image_bytes("https://example.com/missing.png")


class TestToDataUri:
    def test_builds_png_data_uri(self, image):
        uri = to_data_uri(str(image))
        expected = base64.b64encode(PNG_BYTES).decode()
        assert uri == f"data:image/png;base64,{expected}"

    def test_uses_extension_for_mime(self, work_dir):
        path = work_dir / "photo.JPG"
        path.write_bytes(b"jpeg-bytes")
        assert to_data_uri(str(path)).startswith("data:image/jpeg;base64,")

    def test_unknown_extension_falls_back_to_png(self, work_dir):
        path = work_dir / "blob.heic"
        path.write_bytes(b"heic-bytes")
        assert to_data_uri(str(path)).startswith("data:image/png;base64,")

    def test_missing_file_raises(self, work_dir):
        with pytest.raises(FileNotFoundError):
            to_data_uri(str(work_dir / "gone.png"))


class TestEmbedImages:
    def test_local_image_is_inlined(self, image):
        out = embed_images(f"before\n\n![截图]({image})\n\nafter")
        assert out.startswith("before")
        assert out.endswith("after")
        assert "data:image/png;base64," in out
        assert str(image) not in out

    def test_alt_text_is_preserved(self, image):
        out = embed_images(f"![终端输出截图]({image})")
        assert out.startswith("![终端输出截图](data:image/png;base64,")

    def test_existing_data_uri_is_left_alone(self):
        content = "![a](data:image/png;base64,AAAA)"
        assert embed_images(content) == content

    def test_multiple_images_all_inlined(self, work_dir):
        first = work_dir / "a.png"
        second = work_dir / "b.png"
        first.write_bytes(b"aaa")
        second.write_bytes(b"bbb")

        out = embed_images(f"![a]({first})\n\n![b]({second})")
        assert out.count("data:image/png;base64,") == 2
        assert base64.b64encode(b"aaa").decode() in out
        assert base64.b64encode(b"bbb").decode() in out

    def test_missing_image_keeps_original_markup(self, work_dir):
        missing = work_dir / "gone.png"
        content = f"![a]({missing})"
        assert embed_images(content) == content

    def test_failure_of_one_image_does_not_block_others(self, work_dir):
        good = work_dir / "good.png"
        good.write_bytes(PNG_BYTES)
        missing = work_dir / "gone.png"

        out = embed_images(f"![good]({good})\n\n![bad]({missing})")
        assert "data:image/png;base64," in out
        assert f"![bad]({missing})" in out

    def test_content_without_images_is_unchanged(self):
        content = "# 标题\n\n没有图片的正文。"
        assert embed_images(content) == content

    def test_image_title_is_consumed(self, image):
        out = embed_images(f'![a]({image} "标题")')
        assert out.startswith("![a](data:image/png;base64,")
        assert out.endswith(")")
        assert '"标题"' not in out


def test_mainwindow_delegates_to_this_module():
    """The GUI keeps a thin wrapper; it must not grow a second implementation."""
    import inspect

    import app

    source = inspect.getsource(app.MainWindow._embed_images_base64)
    body = "\n".join(line for line in source.splitlines() if not line.strip().startswith("def "))
    assert "image_base64" in body
    assert "base64" not in body.replace("image_base64", "")
    assert "re.sub" not in body
