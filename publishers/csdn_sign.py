"""CSDN 网关 (x-ca) HMAC 签名 —— 单一实现来源。

CSDN 的 bizapi 网关要求每个请求携带 x-ca-key / x-ca-nonce / x-ca-signature。
被签名的字符串是固定的 7 行结构：

    {METHOD}
    */*
    <空行>
    application/json
    <空行>
    x-ca-key:{key}
    x-ca-nonce:{nonce}
    {请求路径}

注意其中第 2、4 行是**常量**：Accept 头固定按 ``*/*`` 参与签名，
Content-Type 固定按 ``application/json`` 参与签名，都与请求实际发送的
头无关。改动这个模板会导致签名失效（网关返回 401/403）。

x-ca-signature-headers 只列出 x-ca-key 与 x-ca-nonce，但请求里仍会再发送
Accept / content-type，且大小写与该常量的顺序保持原样，避免触发网关校验。
"""

import hashlib
import hmac
import uuid
from base64 import b64encode

DEFAULT_CA_KEY = "203803574"
DEFAULT_CA_SECRET = "9znpamsyl2c7cdrr9sas0le9vbc3r6ba"


def build_signature(
    method: str,
    path: str,
    nonce: str,
    ca_secret: str,
    ca_key: str = DEFAULT_CA_KEY,
) -> str:
    """Return the base64 x-ca-signature for one request."""
    to_enc = (
        f"{method}\n*/*\n\napplication/json\n\n"
        f"x-ca-key:{ca_key}\n"
        f"x-ca-nonce:{nonce}\n"
        f"{path}"
    )
    raw = hmac.new(ca_secret.encode(), to_enc.encode(), hashlib.sha256).digest()
    return b64encode(raw).decode()


def ca_headers(
    path: str,
    method: str = "POST",
    nonce: str | None = None,
    ca_key: str | None = None,
    ca_secret: str | None = None,
    user_agent: str | None = None,
) -> dict:
    """Build the signed headers for one CSDN bizapi request.

    ca_key/ca_secret fall back to the published CSDN editor credentials; pass a
    user's own values when settings override them.
    """
    ca_key = ca_key or DEFAULT_CA_KEY
    ca_secret = ca_secret or DEFAULT_CA_SECRET
    nonce = nonce or str(uuid.uuid4())

    headers = {
        "x-ca-key": ca_key,
        "x-ca-nonce": nonce,
        "x-ca-signature": build_signature(method, path, nonce, ca_secret, ca_key),
        "x-ca-signature-headers": "x-ca-key,x-ca-nonce",
        "Accept": "*/*",
        "content-type": "application/json",
        "Origin": "https://editor.csdn.net",
        "Referer": "https://editor.csdn.net/",
    }
    if user_agent:
        headers["User-Agent"] = user_agent
    return headers
