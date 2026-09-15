"""CSDN native image hosting (img-blog.csdnimg.cn) via Huawei OBS direct upload.

CSDN re-host (转存) of external image URLs frequently fails, so before calling
saveArticle we upload every article image to CSDN's own CDN. The flow mirrors
the one used by CSDN's own editor (appName=direct_blog_markdown):

  1. signed POST to bizapi.csdn.net/resource-api/v1/image/direct/upload/signature
     (reuses the same x-ca HMAC as saveArticle, with the user's session cookies)
  2. anonymous multipart POST of the raw bytes to the returned Huawei OBS host,
     authorized by the returned policy/signature
  3. response data.imageUrl -> https://img-blog.csdnimg.cn/direct/...
"""

import hashlib
import hmac
import json
import re
import uuid
from base64 import b64encode
from pathlib import Path
from urllib.parse import urlparse

import httpx

import http_client

from image_handler import IMAGE_PATTERN

_BIZ = "https://bizapi.csdn.net"
_SIGN_PATH = "/resource-api/v1/image/direct/upload/signature"
_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)
_CA_KEY = "203803574"
_CA_SECRET = "9znpamsyl2c7cdrr9sas0le9vbc3r6ba"
_CSDN_HOSTS = ("csdnimg.cn", "csdn.net")

_MIME = {
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "png": "image/png",
    "gif": "image/gif",
    "webp": "image/webp",
}


def _cookie_dict(cookies) -> dict:
    return {
        k: v if isinstance(v, str) else v.get("value", str(v))
        for k, v in (cookies or {}).items()
    }


def _ca_headers(nonce: str, path: str) -> dict:
    to_enc = (
        f"POST\n*/*\n\napplication/json\n\n"
        f"x-ca-key:{_CA_KEY}\n"
        f"x-ca-nonce:{nonce}\n"
        f"{path}"
    )
    sig = b64encode(
        hmac.new(_CA_SECRET.encode(), to_enc.encode(), hashlib.sha256).digest()
    ).decode()
    return {
        "x-ca-key": _CA_KEY,
        "x-ca-nonce": nonce,
        "x-ca-signature": sig,
        "x-ca-signature-headers": "x-ca-key,x-ca-nonce",
        "Accept": "*/*",
        "content-type": "application/json",
        "Origin": "https://editor.csdn.net",
        "Referer": "https://editor.csdn.net/",
        "User-Agent": _USER_AGENT,
    }


def _guess_ext(target: str) -> str:
    path = urlparse(target).path
    ext = Path(path).suffix.lstrip(".").lower()
    return ext if ext in _MIME else "png"


def _fetch_signature(client: httpx.Client, ext: str) -> dict:
    resp = client.post(
        _BIZ + _SIGN_PATH,
        headers=_ca_headers(str(uuid.uuid4()), _SIGN_PATH),
        json={"imageTemplate": "", "appName": "direct_blog_markdown", "imageSuffix": ext},
        timeout=30.0,
    )
    try:
        data = resp.json()
    except json.JSONDecodeError:
        raise RuntimeError(f"CSDN 签名接口返回非JSON HTTP {resp.status_code}: {resp.text[:200]}")
    if resp.status_code != 200 or data.get("code") != 200 or not data.get("data"):
        msg = data.get("message") or data.get("msg") or str(data)[:200]
        if resp.status_code in (401, 403):
            raise RuntimeError("CSDN 登录已过期，请重新扫码登录")
        raise RuntimeError(f"CSDN 获取上传签名失败: {msg}")
    return data["data"]


def upload_image_bytes(cookies: dict, image_data: bytes, ext: str, retries: int = 1) -> str:
    """Upload raw bytes to CSDN CDN and return the img-blog.csdnimg.cn URL."""
    client = http_client.client(cookies=_cookie_dict(cookies), timeout=60.0, follow_redirects=True)
    last_error = ""
    try:
        for attempt in range(1 + retries):
            info = _fetch_signature(client, ext)
            cp = info.get("customParam") or {}
            form = {
                "key": info["filePath"],
                "policy": info["policy"],
                "signature": info["signature"],
                "callbackBody": info.get("callbackBody", ""),
                "callbackBodyType": info.get("callbackBodyType", ""),
                "callbackUrl": info.get("callbackUrl", ""),
                "AccessKeyId": info.get("accessId", ""),
                "x:rtype": cp.get("rtype", ""),
                "x:filePath": cp.get("filePath", ""),
                "x:isAudit": str(cp.get("isAudit", 0)),
                "x:x-image-app": cp.get("x-image-app", ""),
                "x:type": cp.get("type", ""),
                "x:x-image-suffix": cp.get("x-image-suffix", ""),
                "x:username": cp.get("username", ""),
            }
            files = {"file": (f"image.{ext}", image_data, _MIME.get(ext, "image/png"))}

            with http_client.client(timeout=60.0) as obs:
                resp = obs.post(
                    info["host"],
                    data=form,
                    files=files,
                    headers={"User-Agent": _USER_AGENT, "Referer": "https://editor.csdn.net/"},
                )

            text = resp.text
            if "AccessDenied" in text:
                last_error = f"签名已过期 HTTP {resp.status_code}"
                continue
            if not text and resp.status_code == 200:
                last_error = "图片被CSDN审核拦截（可能是图片过小或内容异常）"
                continue
            try:
                result = resp.json()
            except json.JSONDecodeError:
                last_error = f"OBS 响应非JSON HTTP {resp.status_code}: {text[:200]}"
                continue
            if result.get("code") == 200:
                url = result.get("data", {}).get("imageUrl")
                if url:
                    return url
            last_error = f"OBS 解析失败: {text[:200]}"
    finally:
        client.close()
    raise RuntimeError(f"CSDN 图片上传失败: {last_error}")


def _is_csdn_url(target: str) -> bool:
    host = (urlparse(target).hostname or "").lower()
    return any(host == h or host.endswith("." + h) for h in _CSDN_HOSTS)


def process_markdown_images(content: str, cookies: dict):
    """Replace local paths / external image URLs with CSDN-hosted URLs.

    Returns (new_content, warnings); failures keep the original URL and are
    listed in warnings so the caller can decide whether to abort.
    """
    warnings = []

    def replacer(match):
        alt = match.group(1)
        target = match.group(2).strip()
        if not target or target.startswith("data:") or _is_csdn_url(target):
            return match.group(0)

        try:
            ext = _guess_ext(target)
            path = Path(target)
            if path.exists():
                with open(target, "rb") as f:
                    image_data = f.read()
            elif target.startswith(("http://", "https://")):
                with http_client.client(timeout=60.0, follow_redirects=True) as dl:
                    resp = dl.get(
                        target,
                        headers={"User-Agent": _USER_AGENT, "Referer": "https://img.scdn.io/"},
                    )
                if resp.status_code != 200:
                    raise RuntimeError(f"下载外链图片失败 HTTP {resp.status_code}")
                image_data = resp.content
            else:
                return match.group(0)

            url = upload_image_bytes(cookies, image_data, ext)
            return f"![{alt}]({url})"
        except Exception as e:
            warnings.append(f"{target}: {e}")
            return match.group(0)

    new_content = re.sub(IMAGE_PATTERN, replacer, content)
    return new_content, warnings