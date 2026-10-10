import httpx

import http_client


class FakeClient:
    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.calls = []
        self.closed = False

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.closed = True
        return False

    def _record(self, method, url, kwargs):
        self.calls.append((method, url, kwargs))
        return "response"

    def get(self, url, **kwargs):
        return self._record("GET", url, kwargs)

    def post(self, url, **kwargs):
        return self._record("POST", url, kwargs)

    def put(self, url, **kwargs):
        return self._record("PUT", url, kwargs)

    def close(self):
        self.closed = True


def test_proxy_is_none_by_default():
    http_client.set_proxy(None)
    assert http_client.get_proxy() is None


def test_blank_proxy_is_treated_as_unset():
    http_client.set_proxy("   ")
    assert http_client.get_proxy() is None
    http_client.set_proxy(None)


def test_set_proxy_strips_whitespace():
    http_client.set_proxy("  http://127.0.0.1:7890  ")
    assert http_client.get_proxy() == "http://127.0.0.1:7890"
    http_client.set_proxy(None)


def test_client_injects_configured_proxy(monkeypatch):
    monkeypatch.setattr(httpx, "Client", lambda **kw: FakeClient(**kw))
    http_client.set_proxy("http://proxy:8080")
    try:
        instance = http_client.client(timeout=5.0)
        assert instance.kwargs == {"timeout": 5.0, "proxy": "http://proxy:8080"}
    finally:
        http_client.set_proxy(None)


def test_client_keeps_explicit_proxy(monkeypatch):
    monkeypatch.setattr(httpx, "Client", lambda **kw: FakeClient(**kw))
    http_client.set_proxy("http://global:1")
    try:
        instance = http_client.client(proxy="http://explicit:2")
        assert instance.kwargs["proxy"] == "http://explicit:2"
    finally:
        http_client.set_proxy(None)


def test_client_adds_no_proxy_when_unset(monkeypatch):
    monkeypatch.setattr(httpx, "Client", lambda **kw: FakeClient(**kw))
    http_client.set_proxy(None)
    assert "proxy" not in http_client.client().kwargs


def test_get_forwards_kwargs_and_closes(monkeypatch):
    created = []

    def factory(**kw):
        instance = FakeClient(**kw)
        created.append(instance)
        return instance

    monkeypatch.setattr(httpx, "Client", factory)
    http_client.set_proxy(None)

    assert http_client.get("https://x/y", timeout=3.0, follow_redirects=True) == "response"
    assert created[0].calls == [
        ("GET", "https://x/y", {"timeout": 3.0, "follow_redirects": True})
    ]
    assert created[0].closed is True


def test_post_forwards_body_kwargs_and_closes(monkeypatch):
    created = []
    monkeypatch.setattr(
        httpx, "Client", lambda **kw: created.append(FakeClient(**kw)) or created[-1]
    )
    http_client.set_proxy(None)

    files = {"image": ("a.png", b"data", "image/png")}
    http_client.post("https://x/upload", files=files, data={"cdn_domain": "d"}, timeout=60.0)

    assert created[0].calls == [
        (
            "POST",
            "https://x/upload",
            {"files": files, "data": {"cdn_domain": "d"}, "timeout": 60.0},
        )
    ]
    assert created[0].closed is True


def test_put_forwards_kwargs_and_closes(monkeypatch):
    created = []
    monkeypatch.setattr(
        httpx, "Client", lambda **kw: created.append(FakeClient(**kw)) or created[-1]
    )
    http_client.set_proxy(None)

    http_client.put("https://x/y", content=b"bytes", headers={"a": "b"})
    assert created[0].calls == [
        ("PUT", "https://x/y", {"content": b"bytes", "headers": {"a": "b"}})
    ]
    assert created[0].closed is True
