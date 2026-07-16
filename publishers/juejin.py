import json
import mimetypes
from pathlib import Path

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

    def _upload_image(self, local_path: str) -> str:
        cookie_str = _build_cookie_header(self._cookies)
        headers = {
            "user-agent": _USER_AGENT,
            "referer": "https://juejin.cn/",
            "origin": "https://juejin.cn",
            "cookie": cookie_str,
        }

        with httpx.Client(timeout=15.0) as client:
            resp = client.get(
                "https://api.juejin.cn/imagex/gen_token",
                params={"client": "web"},
                headers=headers,
            )
            resp.raise_for_status()
            data = resp.json()
            token = data.get("data") or data.get("token", "")
        if not token:
            raise Exception("获取上传 token 失败")

        with httpx.Client(timeout=15.0) as client:
            apply_resp = client.get(
                "https://imagex.bytedanceapi.com/",
                params={
                    "Action": "ApplyImageUpload",
                    "Version": "2018-08-01",
                    "ServiceId": "k3u1fbpfcp",
                    "s": token,
                },
                headers={"user-agent": _USER_AGENT},
            )
            apply_resp.raise_for_status()
            apply_data = apply_resp.json()

        upload_addr = apply_data.get("Result", {}).get("UploadAddress", {})
        store_uri = upload_addr.get("StoreUri", "")
        upload_hosts = upload_addr.get("UploadHosts", [])
        session_key = upload_addr.get("SessionKey", "")
        if not store_uri or not upload_hosts:
            raise Exception("获取上传地址失败")

        upload_host = upload_hosts[0]
        file_bytes = Path(local_path).read_bytes()
        mime = mimetypes.guess_type(local_path)[0] or "application/octet-stream"

        with httpx.Client(timeout=60.0) as client:
            put_resp = client.put(
                f"https://{upload_host}/{store_uri}",
                content=file_bytes,
                headers={"Content-Type": mime},
            )
            put_resp.raise_for_status()

        with httpx.Client(timeout=15.0) as client:
            commit_resp = client.post(
                f"https://{upload_host}/",
                params={
                    "Action": "CommitImageUpload",
                    "Version": "2018-08-01",
                    "ServiceId": "k3u1fbpfcp",
                },
                json={"SessionKey": session_key},
                headers={"Content-Type": "application/json"},
            )
            commit_resp.raise_for_status()
            commit_data = commit_resp.json()

        results = commit_data.get("Result", {}).get("Results", [])
        if not results:
            raise Exception("提交上传后未返回结果")

        return results[0].get("ImageUrl", "") or ""

    def _handle_images(self, content: str) -> str:
        from image_handler import ImageHandler
        images = ImageHandler.extract_images(content)
        local_images = [p for p in images if Path(p).exists()]
        if not local_images:
            return content

        mapping = {}
        for path in local_images:
            try:
                url = self._upload_image(path)
                mapping[path] = url
            except Exception as e:
                continue

        for local_path, remote_url in mapping.items():
            content = content.replace(f"({local_path})", f"({remote_url})")
            content = content.replace(f'"{local_path}"', f'"{remote_url}"')
        return content

    def publish(self, title: str, content: str, **kwargs) -> PublishResult:
        if not self._cookies:
            return PublishResult(False, self.name, error="未登录掘金")

        content = self._handle_images(content)

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
