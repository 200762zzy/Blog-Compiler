import xmlrpc.client

from publishers.base import BasePublisher, PublishResult


class CnblogsPublisher(BasePublisher):
    name = "博客园"

    def __init__(self, settings):
        self.settings = settings
        self._username = ""
        self._api_key = ""
        self._blog_id = ""
        self._restore()

    def _restore(self):
        self._username = self.settings.get("cnblogs_username", "")
        self._api_key = self.settings.get("cnblogs_api_key", "")
        self._blog_id = self.settings.get("cnblogs_blog_id", "")

    def _save(self):
        self.settings.set("cnblogs_username", self._username)
        self.settings.set("cnblogs_api_key", self._api_key)
        self.settings.set("cnblogs_blog_id", self._blog_id)

    def _get_endpoint(self) -> str:
        blog_id = self._blog_id or self._username
        return f"https://rpc.cnblogs.com/metaweblog/{blog_id}"

    def is_logged_in(self) -> bool:
        return bool(self._username and self._api_key)

    def login(self, parent=None) -> bool:
        from PySide6.QtWidgets import QInputDialog, QLineEdit, QMessageBox

        username, ok1 = QInputDialog.getText(parent, "博客园设置", "用户名:", QLineEdit.Normal, self._username)
        if not ok1 or not username.strip():
            return False

        api_key, ok2 = QInputDialog.getText(
            parent, "博客园设置",
            "MetaWeblog API Key\n(博客园后台 → 设置 → MetaWeblog 生成):",
            QLineEdit.Password, self._api_key,
        )
        if not ok2 or not api_key.strip():
            return False

        blog_id, ok3 = QInputDialog.getText(
            parent, "博客园设置",
            "博客名 (可选，默认从用户名推断)\n例如 https://www.cnblogs.com/xxx/ 中的 xxx:",
            QLineEdit.Normal, self._blog_id or username.strip(),
        )

        self._username = username.strip()
        self._api_key = api_key.strip()
        self._blog_id = blog_id.strip() if ok3 and blog_id.strip() else self._username

        try:
            proxy = xmlrpc.client.ServerProxy(self._get_endpoint())
            proxy.blogger.getUsersBlogs("", self._username, self._api_key)
            self._save()
            return True
        except Exception as e:
            QMessageBox.warning(parent, "验证失败", f"无法连接博客园:\n{e}")
            self._username = ""
            self._api_key = ""
            self._blog_id = ""
            return False

    def logout(self):
        self._username = ""
        self._api_key = ""
        self._blog_id = ""
        self._save()

    def publish(self, title: str, content: str, **kwargs) -> PublishResult:
        if not self.is_logged_in():
            return PublishResult(False, self.name, error="未配置博客园账号")

        tags = kwargs.get("tags", "")
        categories = kwargs.get("categories", "")

        post_categories = ["[Markdown]"]
        if categories:
            post_categories.extend([c.strip() for c in categories.split(",") if c.strip()])

        post = {
            "title": title,
            "description": content,
            "categories": post_categories,
            "mt_keywords": tags,
        }

        try:
            proxy = xmlrpc.client.ServerProxy(self._get_endpoint(), verbose=False)
            post_id = proxy.metaWeblog.newPost("", self._username, self._api_key, post, True)
            url = f"https://www.cnblogs.com/{self._blog_id}/p/{post_id}"
            return PublishResult(True, self.name, url=url)
        except Exception as e:
            error_msg = str(e)
            if "401" in error_msg or "权限" in error_msg:
                self.logout()
            return PublishResult(False, self.name, error=f"发布失败: {error_msg}")
