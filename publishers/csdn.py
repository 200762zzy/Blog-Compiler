import json
from urllib.parse import urlparse

import httpx
import mistune

import http_client

from publishers.base import BasePublisher, PublishResult
from publishers.csdn_sign import ca_headers


_SAVE_URL = "https://bizapi.csdn.net/blog-console-api/v3/mdeditor/saveArticle"
_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)


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

        ca_key = self.settings.get("ca_key") or None
        ca_secret = self.settings.get("ca_secret") or None
        tags = kwargs.get("tags", "")
        categories = kwargs.get("categories", "")
        article_type = kwargs.get("article_type", "original")
        draft = kwargs.get("draft", False)
        article_id = str(kwargs.get("article_id", "") or "")

        parsed = urlparse(_SAVE_URL)
        path = parsed.path + ("?" + parsed.query if parsed.query else "")
        headers = ca_headers(
            path,
            method="POST",
            ca_key=ca_key,
            ca_secret=ca_secret,
            user_agent=_USER_AGENT,
        )

        image_warnings = []
        if content:
            from publishers.csdn_image import process_markdown_images
            content, image_warnings = process_markdown_images(content, self._cookies)

        try:
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
                "is_new": 0 if article_id else 1,
                "vote_id": 0,
                "pubStatus": "draft" if draft else "publish",
            }
            if article_id:
                try:
                    payload["id"] = int(article_id)
                except ValueError:
                    payload["id"] = article_id

            with http_client.client(cookies=self._cookies, timeout=30.0) as client:
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
            aid = str(data.get("data", {}).get("id", "") or "")
            return PublishResult(
                True, self.name, url=url, warnings=image_warnings, article_id=aid
            )

        except httpx.RequestError as e:
            return PublishResult(False, self.name, error=f"网络错误: {e}")
        except Exception as e:
            return PublishResult(False, self.name, error=str(e))
