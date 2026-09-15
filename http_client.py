"""Shared httpx factory so every network call honours the configured proxy.

A single module-level proxy is configured once at startup from settings, then
all HTTP calls in the app (AI, image hosting, publishers) go through `client()`
so a user behind a proxy / GFW-unstable network can reach them reliably.
"""

import httpx

_proxy: str | None = None


def set_proxy(url: str | None):
    global _proxy
    _proxy = (url or "").strip() or None


def get_proxy() -> str | None:
    return _proxy


def client(**kwargs) -> httpx.Client:
    if _proxy and "proxy" not in kwargs and "proxies" not in kwargs:
        kwargs["proxy"] = _proxy
    return httpx.Client(**kwargs)


def get(url, **kwargs):
    with client(**kwargs) as c:
        return c.get(url)


def post(url, **kwargs):
    with client(**kwargs) as c:
        return c.post(url)


def put(url, **kwargs):
    with client(**kwargs) as c:
        return c.put(url)
