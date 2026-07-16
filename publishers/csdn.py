import uuid
import hmac
import hashlib
import json
from base64 import b64encode
from urllib.parse import urlparse

import httpx
import mistune

from publishers.base import BasePublisher, PublishResult


_SAVE_URL = "https://bizapi.csdn.net/blog-console-api/v3/mdeditor/saveArticle"
_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)
_CA_KEY = "203803574"
_CA_SECRET = "9znpamsyl2c7cdrr9sas0le9vbc3r6ba"


def _build_sign(method: str, path: str, nonce: str, ca_key: str, ca_secret: str) -> str:
    to_enc = (
        f"{method}\n*/*\n\napplication/json\n\n"
        f"x-ca-key:{ca_key}\n"
        f"x-ca-nonce:{nonce}\n"
        f"{path}"
    )
    raw = hmac.new(ca_secret.encode(), to_enc.encode(), hashlib.sha256).digest()
    return b64encode(raw).decode()


class CsdnPublisher(BasePublisher):
    name = "CSDN"

    def __init__(self, settings):
        self.settings = settings
        self._cookies = None
        self._restore()

    def _restore(self):
        raw = self.settings.get("csdn_cookies")
        if raw:
            try:
                self._cookies = json.loads(raw)
            except (json.JSONDecodeError, TypeError):
                self._cookies = None

    def _save(self):
        self.settings.set("csdn_cookies", json.dumps(self._cookies) if self._cookies else "")

    def is_logged_in(self) -> bool:
        return bool(self._cookies)

    def login(self, parent=None) -> bool:
        from login_window import CsdnLoginWindow
        dlg = CsdnLoginWindow(parent)
        result = False
        def on_success(cookies):
            nonlocal result
            self._cookies = cookies
            self._save()
            result = True
        dlg.login_successful.connect(on_success)
        dlg.exec()
        return result

    def logout(self):
        self._cookies = None
        self._save()

    def publish(self, title: str, content: str, **kwargs) -> PublishResult:
        if not self._cookies:
            return PublishResult(False, self.name, error="未登录 CSDN")

        ca_key = self.settings.get("ca_key") or _CA_KEY
        ca_secret = self.settings.get("ca_secret") or _CA_SECRET
        tags = kwargs.get("tags", "")
        categories = kwargs.get("categories", "")
        article_type = kwargs.get("article_type", "original")
        draft = kwargs.get("draft", False)

        nonce = str(uuid.uuid4())
        parsed = urlparse(_SAVE_URL)
        path = parsed.path + ("?" + parsed.query if parsed.query else "")
        sign = _build_sign("POST", path, nonce, ca_key, ca_secret)

        headers = {
            "x-ca-key": ca_key,
            "x-ca-nonce": nonce,
            "x-ca-signature": sign,
            "x-ca-signature-headers": "x-ca-key,x-ca-nonce",
            "content-type": "application/json",
            "origin": "https://editor.csdn.net",
            "referer": "https://editor.csdn.net/",
            "user-agent": _USER_AGENT,
        }

        html_content = mistune.html(content)
        payload = {
            "title": title,
            "markdowncontent": content,
            "content": html_content,
            "readType": "public",
            "tags": tags or " ",
            "status": 2 if draft else 0,
            "categories": categories,
            "type": article_type,
            "original_link": "",
            "authorized_status": False,
            "not_auto_saved": "1",
            "source": "pc_mdeditor",
            "cover_images": [],
            "cover_type": 0,
            "is_new": 1,
            "vote_id": 0,
            "pubStatus": "draft" if draft else "publish",
        }

        try:
            with httpx.Client(cookies=self._cookies, timeout=30.0) as client:
                resp = client.post(_SAVE_URL, headers=headers, json=payload)

            if resp.status_code != 200:
                detail = resp.text[:500]
                return PublishResult(False, self.name, error=f"HTTP {resp.status_code}: {detail}")

            data = resp.json()
            code = data.get("code", 0)
            if code not in (200, 0) and not data.get("status"):
                msg = data.get("msg") or data.get("message") or str(data)[:300]
                if "login" in str(msg).lower() or "未登录" in str(msg):
                    self.logout()
                    return PublishResult(False, self.name, error=f"登录过期: {msg}")
                return PublishResult(False, self.name, error=msg)

            url = data.get("data", {}).get("url", "")
            return PublishResult(True, self.name, url=url)

        except httpx.RequestError as e:
            return PublishResult(False, self.name, error=f"网络错误: {e}")
        except Exception as e:
            return PublishResult(False, self.name, error=str(e))
