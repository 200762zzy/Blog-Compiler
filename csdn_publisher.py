import uuid
import hmac
import hashlib
from base64 import b64encode
from urllib.parse import urlparse

import httpx
import mistune


CA_KEY = "203803574"
CA_SECRET = "9znpamsyl2c7cdrr9sas0le9vbc3r6ba"
SAVE_URL = "https://bizapi.csdn.net/blog-console-api/v3/mdeditor/saveArticle"

_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)


def _uuid() -> str:
    return str(uuid.uuid4())


def _build_sign(method: str, path: str, nonce: str) -> str:
    to_enc = (
        f"{method}\n*/*\n\napplication/json\n\n"
        f"x-ca-key:{CA_KEY}\n"
        f"x-ca-nonce:{nonce}\n"
        f"{path}"
    )
    raw = hmac.new(CA_SECRET.encode(), to_enc.encode(), hashlib.sha256).digest()
    return b64encode(raw).decode()


def publish(
    title: str,
    markdown_content: str,
    cookies: dict,
    is_new: bool = True,
    tags: str = "",
    categories: str = "",
    read_type: str = "public",
    article_type: str = "original",
) -> dict:
    nonce = _uuid()
    parsed = urlparse(SAVE_URL)
    path = parsed.path + ("?" + parsed.query if parsed.query else "")

    sign = _build_sign("POST", path, nonce)

    headers = {
        "x-ca-key": CA_KEY,
        "x-ca-nonce": nonce,
        "x-ca-signature": sign,
        "x-ca-signature-headers": "x-ca-key,x-ca-nonce",
        "content-type": "application/json",
        "origin": "https://editor.csdn.net",
        "referer": "https://editor.csdn.net/",
        "user-agent": _USER_AGENT,
    }

    html_content = mistune.html(markdown_content)

    payload = {
        "title": title,
        "markdowncontent": markdown_content,
        "content": html_content,
        "readType": read_type,
        "tags": tags or " ",
        "status": 0,
        "categories": categories,
        "type": article_type,
        "original_link": "",
        "authorized_status": False,
        "not_auto_saved": "1",
        "source": "pc_mdeditor",
        "cover_images": [],
        "cover_type": 0,
        "is_new": 1 if is_new else 0,
        "vote_id": 0,
        "pubStatus": "publish",
    }

    with httpx.Client(cookies=cookies, timeout=30.0) as client:
        resp = client.post(SAVE_URL, headers=headers, json=payload)

    if resp.status_code != 200:
        detail = resp.text[:500]
        raise RuntimeError(f"发布失败 HTTP {resp.status_code}: {detail}")

    data = resp.json()
    code = data.get("code", 0)
    if code not in (200, 0) and not data.get("status"):
        msg = data.get("msg") or data.get("message") or str(data)[:300]
        if "login" in str(msg).lower() or "未登录" in str(msg):
            raise PermissionError(f"登录已过期，请重新登录: {msg}")
        raise RuntimeError(f"发布失败: {msg}")

    return data
