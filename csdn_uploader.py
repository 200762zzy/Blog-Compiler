import mimetypes
from pathlib import Path

import httpx


UPLOAD_URL = "https://blog.csdn.net/phoenix/upload"


class CSDNUploader:
    def __init__(self, cookies: dict | None = None):
        self.cookies = cookies or {}
        self._client = None

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
        path = Path(local_path)
        if not path.exists():
            raise FileNotFoundError(f"图片不存在: {local_path}")

        mime_type, _ = mimetypes.guess_type(local_path)
        if mime_type is None:
            mime_type = "image/png"

        with open(local_path, "rb") as f:
            files = {"file": (path.name, f, mime_type)}
            resp = self.client.post(UPLOAD_URL, files=files)

        resp.raise_for_status()
        data = resp.json()

        if "url" in data:
            return data["url"]
        elif "data" in data and isinstance(data["data"], dict) and "url" in data["data"]:
            return data["data"]["url"]
        elif "url" in data.get("data", {}):
            return data["data"]["url"]
        else:
            raise ValueError(f"无法解析上传响应: {data}")

    def verify_login(self) -> bool:
        try:
            resp = self.client.get(
                "https://blog.csdn.net/",
                timeout=10.0
            )
            return resp.status_code == 200 and "passport" not in str(resp.url)
        except Exception:
            return False
