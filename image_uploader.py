import httpx
import os
import time
from pathlib import Path

import http_client


SCDN_API_URL = "https://img.scdn.io/api/v1.php"

CDN_CANDIDATES = [
    "img.scdn.io",
    "cloudflareimg.cdn.sn",
    "edgeoneimg.cdn.sn",
    "esaimg.cdn1.vip",
    "edgeoneimg.cdn1.vip",
]

_MIME_MAP = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".bmp": "image/bmp",
    ".tiff": "image/tiff",
}


def _guess_mime(path: Path) -> str:
    return _MIME_MAP.get(path.suffix.lower(), "image/png")


def upload_image(
    local_path: str,
    timeout: float = 60.0,
    cdn_domain: str | None = None,
    max_retries: int = 2,
) -> str:
    src = Path(local_path)
    if not src.exists():
        raise FileNotFoundError(f"图片不存在: {local_path}")

    from image_processor import optimize

    upload_path = optimize(local_path)
    temp_created = upload_path != local_path
    path = Path(upload_path)

    candidates = [cdn_domain] if cdn_domain else CDN_CANDIDATES
    failures = []
    try:
        for cdn in candidates:
            last_error = ""
            for attempt in range(1 + max_retries):
                try:
                    with open(upload_path, "rb") as f:
                        files = {"image": (path.name, f, _guess_mime(path))}
                        data = {"cdn_domain": cdn}
                        resp = http_client.post(SCDN_API_URL, files=files, data=data, timeout=timeout)

                    if resp.status_code != 200:
                        raise RuntimeError(
                            f"HTTP {resp.status_code}: {resp.text[:200]}"
                        )

                    result = resp.json()
                    if not result.get("success"):
                        raise RuntimeError(
                            f"{result.get('message', '未知错误')}"
                        )

                    return result["url"]

                except (httpx.TimeoutException, httpx.ConnectError, httpx.RemoteProtocolError) as e:
                    last_error = f"网络错误 ({type(e).__name__}): {e}"
                    if attempt < max_retries:
                        time.sleep(2 ** attempt)
                    continue
                except RuntimeError as e:
                    last_error = f"scdn.io: {e}"
                    break
                except Exception as e:
                    raise

            failures.append(f"{cdn}: {last_error or '未知错误'}")

        raise RuntimeError(f"图片上传失败 ({len(candidates)}个CDN均失败): " + " | ".join(failures))
    finally:
        if temp_created:
            try:
                os.remove(upload_path)
            except OSError:
                pass


def upload_images(local_paths: list[str]) -> dict[str, str]:
    mapping = {}
    for p in local_paths:
        url = upload_image(p)
        mapping[p] = url
    return mapping
