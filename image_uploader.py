import httpx
from pathlib import Path


SCDN_API_URL = "https://img.scdn.io/api/v1.php"

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


def upload_image(local_path: str, timeout: float = 60.0) -> str:
    path = Path(local_path)
    if not path.exists():
        raise FileNotFoundError(f"图片不存在: {local_path}")

    with open(local_path, "rb") as f:
        files = {"image": (path.name, f, _guess_mime(path))}
        resp = httpx.post(SCDN_API_URL, files=files, timeout=timeout)

    if resp.status_code != 200:
        raise RuntimeError(
            f"scdn.io 上传失败 HTTP {resp.status_code}: {resp.text[:300]}"
        )

    result = resp.json()
    if not result.get("success"):
        raise RuntimeError(
            f"scdn.io 上传失败: {result.get('message', '未知错误')}"
        )

    return result["url"]


def upload_images(local_paths: list[str]) -> dict[str, str]:
    mapping = {}
    for p in local_paths:
        url = upload_image(p)
        mapping[p] = url
    return mapping
