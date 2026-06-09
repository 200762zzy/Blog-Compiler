import mimetypes
import uuid
from pathlib import Path

import httpx


CSDN_UPLOAD_URL = "https://blog.csdn.net/phoenix/upload"
SMMS_UPLOAD_URL = "https://sm.ms/api/v2/upload"
SMMS_TOKEN = ""  # 可选，留空用匿名上传


class CSDNUploader:
    def __init__(self, cookies: dict | None = None):
        self.cookies = cookies or {}
        self._client = None
        self.last_error = ""

    @property
    def client(self) -> httpx.Client:
        if self._client is None:
            cookie_dict = {
                k: v if isinstance(v, str) else v.get("value", str(v))
                for k, v in self.cookies.items()
            }
            self._client = httpx.Client(
                cookies=cookie_dict,
                timeout=60.0,
                follow_redirects=True
            )
        return self._client

    def login(self, cookies: dict):
        self.cookies = cookies
        self._client = None

    def upload_image(self, local_path: str) -> str:
        self.last_error = ""
        try:
            return self._upload_csdn(local_path)
        except Exception as e:
            self.last_error = str(e)
            raise

    def upload_with_fallback(self, local_path: str) -> str:
        path = Path(local_path)
        if not path.exists():
            raise FileNotFoundError(f"图片不存在: {local_path}")

        try:
            return self._upload_csdn(local_path)
        except Exception as e1:
            err1 = str(e1)
            try:
                return self._upload_smms(local_path)
            except Exception as e2:
                raise RuntimeError(
                    f"CSDN 上传失败: {err1}\nSM.MS 上传失败: {e2}"
                )

    def _upload_csdn(self, local_path: str) -> str:
        path = Path(local_path)
        mime_type, _ = mimetypes.guess_type(local_path)
        if mime_type is None:
            mime_type = "image/png"

        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            "Referer": "https://blog.csdn.net/",
            "Origin": "https://blog.csdn.net",
        }

        with open(local_path, "rb") as f:
            files = {"file": (path.name, f, mime_type)}
            resp = self.client.post(
                CSDN_UPLOAD_URL, files=files, headers=headers
            )

        if resp.status_code != 200:
            raise RuntimeError(
                f"CSDN 上传返回 HTTP {resp.status_code}: {resp.text[:500]}"
            )

        data = resp.json()
        for key in ("url", "data"):
            val = data.get(key)
            if isinstance(val, dict) and "url" in val:
                return val["url"]
            if isinstance(val, str) and val.startswith("http"):
                return val

        raise RuntimeError(f"CSDN 无法解析响应: {resp.text[:500]}")

    def _upload_smms(self, local_path: str) -> str:
        path = Path(local_path)
        mime_type, _ = mimetypes.guess_type(local_path)
        if mime_type is None:
            mime_type = "image/png"

        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
        }
        if SMMS_TOKEN:
            headers["Authorization"] = f"Basic {SMMS_TOKEN}"

        with open(local_path, "rb") as f:
            files = {"smfile": (path.name, f, mime_type)}
            resp = httpx.post(
                SMMS_UPLOAD_URL, files=files, headers=headers, timeout=60.0
            )

        if resp.status_code != 200:
            raise RuntimeError(
                f"SM.MS 返回 HTTP {resp.status_code}: {resp.text[:300]}"
            )

        data = resp.json()
        if data.get("success") and "data" in data:
            url = data["data"].get("url")
            if url:
                return url

        raise RuntimeError(f"SM.MS 解析失败: {resp.text[:300]}")

    def verify_login(self) -> bool:
        try:
            resp = self.client.get(
                "https://blog.csdn.net/",
                timeout=10.0,
                headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124.0.0.0"},
            )
            return resp.status_code == 200 and "passport" not in str(resp.url)
        except Exception:
            return False
