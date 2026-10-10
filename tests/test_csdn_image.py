import json

import pytest

import http_client
import publishers.csdn_image as csdn_image
from publishers.csdn_image import (
    _guess_ext,
    _is_csdn_url,
    _read_image_bytes,
    _upload_form,
    process_markdown_images,
)


class FakeResponse:
    def __init__(self, status_code=200, text="", payload=None, content=b""):
        self.status_code = status_code
        self.text = text
        self.content = content
        self._payload = payload

    def json(self):
        if self._payload is None:
            raise json.JSONDecodeError("bad", "", 0)
        return self._payload


class TestGuessExt:
    @pytest.mark.parametrize(
        "target,expected",
        [
            ("a.png", "png"),
            ("a.JPG", "jpg"),
            ("a.jpeg", "jpeg"),
            ("a.gif", "gif"),
            ("a.webp", "webp"),
            ("https://x/y/z.PNG?sign=1", "png"),
            ("a.bmp", "png"),
            ("noext", "png"),
        ],
    )
    def test_extensions(self, target, expected):
        assert _guess_ext(target) == expected


class TestIsCsdnUrl:
    @pytest.mark.parametrize(
        "target,expected",
        [
            ("https://img-blog.csdnimg.cn/direct/a.png", True),
            ("https://i-blog.csdnimg.cn/x.png", True),
            ("https://blog.csdn.net/x.png", True),
            ("https://evil-csdnimg.cn/x.png", False),
            ("https://csdnimg.cn.evil.com/x.png", False),
            ("/local/path.png", False),
        ],
    )
    def test_host_matching(self, target, expected):
        assert _is_csdn_url(target) is expected


def test_upload_form_maps_signature_fields():
    info = {
        "filePath": "direct/a.png",
        "policy": "POLICY",
        "signature": "SIG",
        "accessId": "AK",
        "callbackBody": "CB",
        "callbackBodyType": "CBT",
        "callbackUrl": "CU",
        "customParam": {
            "rtype": "1",
            "filePath": "direct/a.png",
            "isAudit": 0,
            "x-image-app": "blog",
            "type": "png",
            "x-image-suffix": "png",
            "username": "someone",
        },
    }
    form = _upload_form(info)

    assert form["key"] == "direct/a.png"
    assert form["policy"] == "POLICY"
    assert form["signature"] == "SIG"
    assert form["AccessKeyId"] == "AK"
    assert form["x:rtype"] == "1"
    assert form["x:isAudit"] == "0"
    assert form["x:x-image-app"] == "blog"
    assert form["x:username"] == "someone"


def test_upload_form_tolerates_missing_custom_param():
    form = _upload_form({"filePath": "k", "policy": "p", "signature": "s"})
    assert form["key"] == "k"
    assert form["AccessKeyId"] == ""
    assert form["x:isAudit"] == "0"


class TestReadImageBytes:
    def test_reads_local_file(self, work_dir):
        path = work_dir / "a.png"
        path.write_bytes(b"local-bytes")
        assert _read_image_bytes(str(path)) == b"local-bytes"

    def test_missing_local_path_raises(self, work_dir):
        with pytest.raises(FileNotFoundError):
            _read_image_bytes(str(work_dir / "nope.png"))

    def test_downloads_remote_urlthrough_shared_client(self, monkeypatch):
        seen = {}

        class Downloader:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def get(self, url, headers=None):
                seen["url"] = url
                seen["headers"] = headers
                return FakeResponse(content=b"remote-bytes")

        monkeypatch.setattr(http_client, "client", lambda **kw: Downloader())
        assert _read_image_bytes("https://x/y.png") == b"remote-bytes"
        assert seen["url"] == "https://x/y.png"

    def test_remote_http_error_raises(self, monkeypatch):
        class Downloader:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def get(self, url, headers=None):
                return FakeResponse(status_code=404)

        monkeypatch.setattr(http_client, "client", lambda **kw: Downloader())
        with pytest.raises(RuntimeError, match="404"):
            _read_image_bytes("https://x/missing.png")


class TestProcessMarkdownImages:
    def test_local_image_is_replaced(self, work_dir, monkeypatch):
        source = work_dir / "pic.png"
        source.write_bytes(b"png-bytes")
        monkeypatch.setattr(
            csdn_image, "_upload_image_bytes", lambda c, d, e, **k: "https://img-blog.csdnimg.cn/direct/new.png"
        )
        content, warnings = process_markdown_images(f"![alt]({source})", {})
        assert content == "![alt](https://img-blog.csdnimg.cn/direct/new.png)"
        assert warnings == []

    def test_relative_path_that_is_not_a_file_keeps_original(self):
        content = "![alt](pic.png)"
        new_content, warnings = process_markdown_images(content, {})
        assert new_content == content
        assert len(warnings) == 1

    def test_data_uri_is_left_alone(self, monkeypatch):
        called = []
        monkeypatch.setattr(
            csdn_image, "_upload_image_bytes", lambda *a, **k: called.append(1)
        )
        content = "![a](data:image/png;base64,AAAA)"
        assert process_markdown_images(content, {})[0] == content
        assert called == []

    def test_already_hosted_csdn_image_is_left_alone(self, monkeypatch):
        called = []
        monkeypatch.setattr(
            csdn_image, "_upload_image_bytes", lambda *a, **k: called.append(1)
        )
        content = "![a](https://img-blog.csdnimg.cn/direct/x.png)"
        assert process_markdown_images(content, {})[0] == content
        assert called == []

    def test_missing_local_file_keeps_original_and_warns(self, work_dir):
        content = f"![a]({work_dir / 'gone.png'})"
        new_content, warnings = process_markdown_images(content, {})
        assert new_content == content
        assert len(warnings) == 1
        assert "gone.png" in warnings[0]

    def test_upload_failure_keeps_other_images_working(self, work_dir, monkeypatch):
        good = work_dir / "good.png"
        good.write_bytes(b"g")

        def fake_upload(cookies, data, ext, **kwargs):
            if data == b"g":
                return "https://img-blog.csdnimg.cn/direct/good.png"
            raise RuntimeError("boom")

        monkeypatch.setattr(csdn_image, "_upload_image_bytes", fake_upload)
        content = f"![a]({good})\n\n![b]({work_dir / 'gone.png'})"

        new_content, warnings = process_markdown_images(content, {})
        assert "https://img-blog.csdnimg.cn/direct/good.png" in new_content
        assert str(work_dir / "gone.png") in new_content
        assert len(warnings) == 1

    def test_no_images_returns_content_unchanged(self):
        content = "# 标题\n\n没有图片。"
        assert process_markdown_images(content, {}) == (content, [])
