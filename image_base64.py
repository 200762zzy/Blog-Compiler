"""把 Markdown 里的图片转成 data URI，用于发布时「base64 内嵌」。

路径写死在正文里（本地路径或外链）时，平台可能拉不到图；内嵌成 data URI
后图片跟着正文一起提交，代价是文章体积变大。

本地文件直接读；http(s) 链接经 http_client 下载，因此受代理设置影响。
任何单张失败都保留原样，不影响其余图片。
"""

import base64
import re
from pathlib import Path

import http_client

from image_handler import IMAGE_PATTERN
from image_uploader import _guess_mime

_IMAGE_RE = re.compile(IMAGE_PATTERN)


def read_image_bytes(target: str) -> bytes:
    """Return the raw bytes of a local path or an http(s) URL."""
    path = Path(target)
    if path.exists():
        return path.read_bytes()
    if target.startswith(("http://", "https://")):
        resp = http_client.get(url=target, timeout=30.0, follow_redirects=True)
        resp.raise_for_status()
        return resp.content
    raise FileNotFoundError(f"图片不存在: {target}")


def to_data_uri(target: str) -> str:
    """Return `data:<mime>;base64,<payload>` for the given image."""
    payload = base64.b64encode(read_image_bytes(target)).decode()
    return f"data:{_guess_mime(Path(target))};base64,{payload}"


def embed_images(markdown: str) -> str:
    """Replace every image reference with an inline data URI."""
    def _replace(match):
        target = match.group(2)
        if target.startswith("data:"):
            return match.group(0)
        try:
            return f"![{match.group(1)}]({to_data_uri(target)})"
        except Exception:
            return match.group(0)

    return _IMAGE_RE.sub(_replace, markdown)
