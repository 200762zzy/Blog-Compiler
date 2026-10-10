import pytest

import publishers.cnblogs as cnblogs_module
from publishers.base import PublishResult
from publishers.cnblogs import CnblogsPublisher


class Struct:
    def __init__(self, **values):
        self.data = dict(values)
        self.writes = []

    def get(self, key, default=None):
        return self.data.get(key, default)

    def set(self, key, value):
        self.data[key] = value
        self.writes.append((key, value))


class FakeProxy:
    """记录 metaWeblog 调用并返回预设结果的替身。"""

    def __init__(self, result=None, raises=None, bloggers_result=None):
        self.result = result
        self.raises = raises
        self.bloggers_result = bloggers_result
        self.calls = []
        self.metaWeblog = self
        self.blogger = self

    def newPost(self, *args):
        self.calls.append(("newPost", args))
        if self.raises:
            raise self.raises
        return self.result

    def getUsersBlogs(self, *args):
        self.calls.append(("getUsersBlogs", args))
        if self.raises:
            raise self.raises
        return self.bloggers_result


@pytest.fixture
def configured():
    return CnblogsPublisher(
        Struct(cnblogs_username="me", cnblogs_api_key="key", cnblogs_blog_id="myblog")
    )


@pytest.fixture
def proxy(monkeypatch):
    """把 xmlrpc 客户端替换成可检查的替身。"""
    def install(fake):
        monkeypatch.setattr(
            cnblogs_module.xmlrpc.client, "ServerProxy", lambda *a, **k: fake
        )
        return fake
    return install


class TestLoginState:
    def test_needs_both_username_and_key(self):
        assert CnblogsPublisher(Struct()).is_logged_in() is False
        assert CnblogsPublisher(Struct(cnblogs_username="me")).is_logged_in() is False
        assert (
            CnblogsPublisher(Struct(cnblogs_username="me", cnblogs_api_key="k")).is_logged_in()
            is True
        )

    def test_logout_clears_everything(self, configured):
        configured.logout()
        assert configured.is_logged_in() is False
        written = {k for k, _ in configured.settings.writes}
        assert written == {"cnblogs_username", "cnblogs_api_key", "cnblogs_blog_id"}


class TestEndpoint:
    def test_uses_explicit_blog_id(self, configured):
        assert configured._get_endpoint() == "https://rpc.cnblogs.com/metaweblog/myblog"

    def test_falls_back_to_username(self):
        publisher = CnblogsPublisher(Struct(cnblogs_username="me", cnblogs_api_key="k"))
        assert publisher._get_endpoint() == "https://rpc.cnblogs.com/metaweblog/me"


class TestPublishGuards:
    def test_publish_without_config_returns_failure(self):
        result = CnblogsPublisher(Struct()).publish("标题", "正文")
        assert isinstance(result, PublishResult)
        assert result.success is False
        assert result.platform == "博客园"
        assert "未配置" in result.error


class TestSuccessfulPublish:
    def test_returns_article_url_from_post_id(self, configured, proxy):
        proxy(FakeProxy(result="1234"))

        result = configured.publish("标题", "正文")

        assert result.success is True
        assert result.url == "https://www.cnblogs.com/myblog/p/1234"

    def test_sends_markdown_category_and_keywords(self, configured, proxy):
        fake = proxy(FakeProxy(result="1"))

        configured.publish("标题", "正文", tags="a,b", categories="后端, Python")

        _, args = fake.calls[0]
        _, username, api_key, post, publish_flag = args
        assert username == "me"
        assert api_key == "key"
        assert publish_flag is True
        assert post["title"] == "标题"
        assert post["description"] == "正文"
        assert post["mt_keywords"] == "a,b"

    def test_markdown_category_is_always_present(self, configured, proxy):
        """博客园靠这个分类决定按 Markdown 渲染，丢了正文就会显示成纯文本。"""
        fake = proxy(FakeProxy(result="1"))

        configured.publish("标题", "正文")

        _, args = fake.calls[0]
        assert "[Markdown]" in args[3]["categories"]

    def test_extra_categories_are_appended_and_trimmed(self, configured, proxy):
        fake = proxy(FakeProxy(result="1"))

        configured.publish("标题", "正文", categories=" 后端 , , Python ")

        _, args = fake.calls[0]
        assert args[3]["categories"] == ["[Markdown]", "后端", "Python"]

    def test_no_extra_categories_leaves_only_markdown(self, configured, proxy):
        fake = proxy(FakeProxy(result="1"))

        configured.publish("标题", "正文", categories="")

        _, args = fake.calls[0]
        assert args[3]["categories"] == ["[Markdown]"]


class TestFailureHandling:
    def test_generic_failure_is_reported(self, configured, proxy):
        proxy(FakeProxy(raises=Exception("服务器开小差了")))

        result = configured.publish("标题", "正文")

        assert result.success is False
        assert "发布失败" in result.error
        assert "服务器开小差了" in result.error

    def test_401_clears_the_credentials(self, configured, proxy):
        proxy(FakeProxy(raises=Exception("HTTP 401 Unauthorized")))

        result = configured.publish("标题", "正文")

        assert result.success is False
        assert configured.is_logged_in() is False

    def test_chinese_permission_error_clears_the_credentials(self, configured, proxy):
        proxy(FakeProxy(raises=Exception("没有权限")))

        result = configured.publish("标题", "正文")

        assert result.success is False
        assert configured.is_logged_in() is False

    def test_english_permission_error_does_not_clear_credentials(self, configured, proxy):
        """记录现状：只匹配 401 和中文「权限」，英文 permission 不会被识别为登录失效。

        这不会造成错误结果（仍是失败），只是凭据不会被清掉。
        """
        proxy(FakeProxy(raises=Exception("Permission denied")))

        result = configured.publish("标题", "正文")

        assert result.success is False
        assert configured.is_logged_in() is True
