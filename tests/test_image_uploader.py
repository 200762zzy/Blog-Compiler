from pathlib import Path

import httpx
import pytest

import image_uploader
from image_uploader import _guess_mime, upload_image, upload_images


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    monkeypatch.setattr(image_uploader.time, "sleep", lambda _s: None)


def _write_image(work_dir, name="pic.png"):
    path = work_dir / name
    path.write_bytes(b"\x89PNG\r\n\x1a\n fake")
    return path


class FakeResponse:
    def __init__(self, status_code=200, payload=None, text=""):
        self.status_code = status_code
        self._payload = payload
        self.text = text

    def json(self):
        if self._payload is None:
            raise ValueError("no json")
        return self._payload


class TestGuessMime:
    def test_known_extensions(self):
        assert _guess_mime(Path("a.png")) == "image/png"
        assert _guess_mime(Path("a.JPG")) == "image/jpeg"
        assert _guess_mime(Path("a.webp")) == "image/webp"
        assert _guess_mime(Path("a.gif")) == "image/gif"

    def test_unknown_extension_falls_back_to_png(self):
        assert _guess_mime(Path("a.heic")) == "image/png"


def test_missing_file_raises():
    with pytest.raises(FileNotFoundError):
        upload_image("definitely/not/here.png")


def test_successful_upload_returns_url(work_dir, monkeypatch):
    src = _write_image(work_dir)
    calls = []

    def fake_post(url, files=None, data=None, timeout=None):
        calls.append((url, data))
        return FakeResponse(payload={"success": True, "url": "https://cdn/x.png"})

    monkeypatch.setattr(image_uploader.http_client, "post", fake_post)
    assert upload_image(str(src)) == "https://cdn/x.png"
    assert calls[0][0] == image_uploader.SCDN_API_URL
    assert calls[0][1] == {"cdn_domain": image_uploader.CDN_CANDIDATES[0]}


def test_uploads_sent_as_multipart_image_field(work_dir, monkeypatch):
    src = _write_image(work_dir)
    seen = {}

    def fake_post(url, files=None, data=None, timeout=None):
        seen["files"] = files
        return FakeResponse(payload={"success": True, "url": "https://cdn/x.png"})

    monkeypatch.setattr(image_uploader.http_client, "post", fake_post)
    upload_image(str(src))

    field, (filename, fh, mime) = next(iter(seen["files"].items()))
    assert field == "image"
    assert filename == "pic.png"
    assert mime == "image/png"
    fh.close()


def test_http_error_falls_through_to_next_cdn(work_dir, monkeypatch):
    src = _write_image(work_dir)
    seen_domains = []

    def fake_post(url, files=None, data=None, timeout=None):
        seen_domains.append(data["cdn_domain"])
        if len(seen_domains) == 1:
            return FakeResponse(status_code=502, text="bad gateway")
        return FakeResponse(payload={"success": True, "url": "https://cdn/ok.png"})

    monkeypatch.setattr(image_uploader.http_client, "post", fake_post)
    assert upload_image(str(src)) == "https://cdn/ok.png"
    assert seen_domains == image_uploader.CDN_CANDIDATES[:2]


def test_unsuccessful_payload_moves_to_next_cdn(work_dir, monkeypatch):
    src = _write_image(work_dir)
    count = {"n": 0}

    def fake_post(url, files=None, data=None, timeout=None):
        count["n"] += 1
        if count["n"] == 1:
            return FakeResponse(payload={"success": False, "message": "额度不足"})
        return FakeResponse(payload={"success": True, "url": "https://cdn/ok.png"})

    monkeypatch.setattr(image_uploader.http_client, "post", fake_post)
    assert upload_image(str(src)) == "https://cdn/ok.png"


def test_all_cdns_failing_raises_with_each_reason(work_dir, monkeypatch):
    src = _write_image(work_dir)

    def fake_post(url, files=None, data=None, timeout=None):
        return FakeResponse(status_code=500, text="boom")

    monkeypatch.setattr(image_uploader.http_client, "post", fake_post)
    with pytest.raises(RuntimeError) as excinfo:
        upload_image(str(src), max_retries=0)

    message = str(excinfo.value)
    assert f"{len(image_uploader.CDN_CANDIDATES)}个CDN均失败" in message
    for domain in image_uploader.CDN_CANDIDATES:
        assert domain in message


def test_network_error_is_retried_then_succeeds(work_dir, monkeypatch):
    src = _write_image(work_dir)
    attempts = {"n": 0}

    def fake_post(url, files=None, data=None, timeout=None):
        attempts["n"] += 1
        if attempts["n"] == 1:
            raise httpx.ConnectError("no route")
        return FakeResponse(payload={"success": True, "url": "https://cdn/ok.png"})

    monkeypatch.setattr(image_uploader.http_client, "post", fake_post)
    assert upload_image(str(src), max_retries=1) == "https://cdn/ok.png"
    assert attempts["n"] == 2


def test_explicit_cdn_domain_is_the_only_candidate(work_dir, monkeypatch):
    src = _write_image(work_dir)
    seen_domains = []

    def fake_post(url, files=None, data=None, timeout=None):
        seen_domains.append(data["cdn_domain"])
        return FakeResponse(status_code=500, text="boom")

    monkeypatch.setattr(image_uploader.http_client, "post", fake_post)
    with pytest.raises(RuntimeError):
        upload_image(str(src), cdn_domain="only.example.com", max_retries=0)
    assert seen_domains == ["only.example.com"]


def test_temp_optimised_file_is_removed(work_dir, monkeypatch):
    src = _write_image(work_dir)
    temp = work_dir / "optimised.webp"
    temp.write_bytes(b"webp")
    removed = []

    import image_processor
    monkeypatch.setattr(image_processor, "optimize", lambda _p: str(temp))
    monkeypatch.setattr(image_uploader.os, "remove", lambda p: removed.append(p))
    monkeypatch.setattr(
        image_uploader.http_client,
        "post",
        lambda *a, **k: FakeResponse(payload={"success": True, "url": "https://cdn/x.webp"}),
    )

    assert upload_image(str(src)) == "https://cdn/x.webp"
    assert removed == [str(temp)]


def test_original_file_is_not_deleted_when_no_temp_created(work_dir, monkeypatch):
    src = _write_image(work_dir)
    removed = []

    import image_processor
    monkeypatch.setattr(image_processor, "optimize", lambda p: str(p))
    monkeypatch.setattr(image_uploader.os, "remove", lambda p: removed.append(p))
    monkeypatch.setattr(
        image_uploader.http_client,
        "post",
        lambda *a, **k: FakeResponse(payload={"success": True, "url": "https://cdn/x.png"}),
    )

    upload_image(str(src))
    assert removed == []


def test_upload_images_builds_mapping(work_dir, monkeypatch):
    first = _write_image(work_dir, "a.png")
    second = _write_image(work_dir, "b.png")
    urls = iter(["https://cdn/a.png", "https://cdn/b.png"])

    monkeypatch.setattr(
        image_uploader,
        "upload_image",
        lambda p, **k: next(urls),
    )

    mapping = upload_images([str(first), str(second)])
    assert mapping == {str(first): "https://cdn/a.png", str(second): "https://cdn/b.png"}
