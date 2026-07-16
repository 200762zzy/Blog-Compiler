import json

import httpx

from publishers.base import BasePublisher, PublishResult


_DRAFT_URL = "https://api.juejin.cn/content_api/v1/article_draft/create"
_PUBLISH_URL = "https://api.juejin.cn/content_api/v1/article/publish"
_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

_DEFAULT_CATEGORY_ID = "6809637769959178254"
_DEFAULT_TAG_IDS = ["6809640408797167623"]

_HEADERS_BASE = {
    "content-type": "application/json",
    "origin": "https://juejin.cn",
    "referer": "https://juejin.cn/",
    "user-agent": _USER_AGENT,
}


def _build_cookie_header(cookies: dict) -> str:
    return "; ".join(f"{k}={v.get('value', v) if isinstance(v, dict) else v}" for k, v in cookies.items())


class JuejinPublisher(BasePublisher):
    name = "掘金"

    def __init__(self, settings):
        self.settings = settings
        self._cookies = None
        self._restore()

    def _restore(self):
        raw = self.settings.get("juejin_cookies")
        if raw:
            try:
                self._cookies = json.loads(raw)
            except (json.JSONDecodeError, TypeError):
                self._cookies = None

    def _save(self):
        self.settings.set("juejin_cookies", json.dumps(self._cookies) if self._cookies else "")

    def is_logged_in(self) -> bool:
        return bool(self._cookies)

    def login(self, parent=None) -> bool:
        from login_window import PlatformLoginWindow
        dlg = PlatformLoginWindow(
            parent,
            login_url="https://juejin.cn/login",
            domain_filter="juejin.cn",
            window_title="登录掘金",
        )
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
            return PublishResult(False, self.name, error="未登录掘金")

        category_id = kwargs.get("category_id", _DEFAULT_CATEGORY_ID)
        tag_ids = kwargs.get("tag_ids", _DEFAULT_TAG_IDS)

        brief = content[:100].strip()
        if len(brief) < 50:
            brief = (brief + "。" * 10)[:100]

        cookie_str = _build_cookie_header(self._cookies)
        headers = {**_HEADERS_BASE, "cookie": cookie_str}

        try:
            draft_payload = {
                "category_id": category_id,
                "tag_ids": tag_ids,
                "title": title,
                "brief_content": brief,
                "edit_type": 10,
                "mark_content": content,
                "cover_image": "",
                "html_content": "deprecated",
                "link_url": "",
                "theme_ids": [],
            }

            with httpx.Client(timeout=30.0) as client:
                draft_resp = client.post(_DRAFT_URL, headers=headers, json=draft_payload)

            if draft_resp.status_code != 200:
                return PublishResult(False, self.name, error=f"创建草稿失败 HTTP {draft_resp.status_code}")

            draft_data = draft_resp.json()
            if draft_data.get("err_no") != 0:
                msg = draft_data.get("err_msg", "未知错误")
                if "login" in msg.lower():
                    self.logout()
                return PublishResult(False, self.name, error=f"创建草稿失败: {msg}")

            draft_id = draft_data.get("data", {}).get("id")
            if not draft_id:
                return PublishResult(False, self.name, error="创建草稿失败: 未获取到 draft_id")

            publish_payload = {
                "draft_id": draft_id,
                "sync_to_org": False,
                "column_ids": [],
                "theme_ids": [],
            }

            with httpx.Client(timeout=30.0) as client:
                pub_resp = client.post(_PUBLISH_URL, headers=headers, json=publish_payload)

            if pub_resp.status_code != 200:
                return PublishResult(False, self.name, error=f"发布失败 HTTP {pub_resp.status_code}")

            pub_data = pub_resp.json()
            if pub_data.get("err_no") != 0:
                msg = pub_data.get("err_msg", "未知错误")
                return PublishResult(False, self.name, error=f"发布失败: {msg}")

            article_id = pub_data.get("data", {}).get("article_id", "")
            url = f"https://juejin.cn/post/{article_id}" if article_id else ""
            return PublishResult(True, self.name, url=url)

        except httpx.RequestError as e:
            return PublishResult(False, self.name, error=f"网络错误: {e}")
        except Exception as e:
            return PublishResult(False, self.name, error=str(e))
