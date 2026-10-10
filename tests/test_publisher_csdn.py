import json

import httpx
import pytest

import publishers.csdn as csdn_module
import publishers.csdn_image as csdn_image_module
from publishers.base import PublishResult
from publishers.csdn import CsdnPublisher

SAVE_URL = csdn_module._SAVE_URL


class Struct:
    """最小 settings 替身：只需 get/set。"""

    def __init__(self, **values):
        self.data = dict(values)
        self.writes = []

    def get(self, key, default=None):
        return self.data.get(key, default)

    def set(self, key, value):
        self.data[key] = value
        self.writes.append((key, value))


class FakeResponse:
    def __init__(self, payload=None, status_code=200, text=""):
        self.status_code = status_code
        self._payload = payload
        self.text = text

    def json(self):
        if self._payload is None:
            raise ValueError("no json")
        return self._payload


class ClientFactory:
    """替换 http_client.client()，记录每个客户端收到的请求。"""

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []
        self.kwargs = []

    def __call__(self, **kwargs):
        self.kwargs.append(kwargs)
        return self

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def post(self, url, headers=None, json=None, data=None, **kwargs):
        self.calls.append({"url": url, "headers": headers, "json": json, "data": data})
        return self.responses.pop(0)


@pytest.fixture
def cookies():
    return {"UserName": "someone", "UserToken": "tok"}


@pytest.fixture
def logged_in(cookies):
    return CsdnPublisher(Struct(csdn_cookies=json.dumps(cookies)))


@pytest.fixture
def blocked_images(monkeypatch):
    """默认不让发布流程真的去传图片。

    publish() 内部是 `from publishers.csdn_image import process_markdown_images`，
    所以要打在源模块上才拦得住。
    """
    monkeypatch.setattr(
        csdn_image_module,
        "process_markdown_images",
        lambda content, cookies: (content, []),
    )


class TestLoginState:
    def test_not_logged_in_without_cookies(self):
        assert CsdnPublisher(Struct()).is_logged_in() is False

    def test_logged_in_with_cookies(self, logged_in):
        assert logged_in.is_logged_in() is True

    def test_corrupt_cookie_json_is_treated_as_logged_out(self):
        publisher = CsdnPublisher(Struct(csdn_cookies="{ broken"))
        assert publisher.is_logged_in() is False

    def test_logout_clears_and_persists(self, logged_in):
        logged_in.logout()
        assert logged_in.is_logged_in() is False
        assert ("csdn_cookies", "") in logged_in.settings.writes


class TestPublishGuards:
    def test_publish_without_login_returns_failure(self):
        result = CsdnPublisher(Struct()).publish("标题", "正文")
        assert isinstance(result, PublishResult)
        assert result.success is False
        assert result.platform == "CSDN"
        assert "未登录" in result.error


class TestSuccessfulPublish:
    def test_returns_url_and_article_id(self, logged_in, blocked_images, monkeypatch):
        factory = ClientFactory(
            [FakeResponse({"code": 200, "data": {"url": "https://blog.csdn.net/x/1", "id": 42}})]
        )
        monkeypatch.setattr(csdn_module.http_client, "client", factory)

        result = logged_in.publish("标题", "正文", tags="python", categories="后端")

        assert result.success is True
        assert result.url == "https://blog.csdn.net/x/1"
        assert result.article_id == "42"
        assert result.error == ""

    def test_sends_signed_headers(self, logged_in, blocked_images, monkeypatch):
        factory = ClientFactory([FakeResponse({"code": 200, "data": {}})])
        monkeypatch.setattr(csdn_module.http_client, "client", factory)

        logged_in.publish("标题", "正文")

        headers = factory.calls[0]["headers"]
        assert headers["x-ca-key"]
        assert headers["x-ca-nonce"]
        assert headers["x-ca-signature"]
        assert headers["x-ca-signature-headers"] == "x-ca-key,x-ca-nonce"
        assert headers["User-Agent"]

    def test_sends_both_markdown_and_html(self, logged_in, blocked_images, monkeypatch):
        factory = ClientFactory([FakeResponse({"code": 200, "data": {}})])
        monkeypatch.setattr(csdn_module.http_client, "client", factory)

        logged_in.publish("标题", "# 大标题\n\n正文")

        payload = factory.calls[0]["json"]
        assert payload["title"] == "标题"
        assert "# 大标题" in payload["markdowncontent"]
        assert "<h1" in payload["content"]

    def test_tags_and_categories_reach_the_payload(self, logged_in, blocked_images, monkeypatch):
        factory = ClientFactory([FakeResponse({"code": 200, "data": {}})])
        monkeypatch.setattr(csdn_module.http_client, "client", factory)

        logged_in.publish("标题", "正文", tags="a,b", categories="后端")

        payload = factory.calls[0]["json"]
        assert payload["tags"] == "a,b"
        assert payload["categories"] == "后端"

    def test_blank_tags_fall_back_to_a_space(self, logged_in, blocked_images, monkeypatch):
        """CSDN 不接受空 tags，代码用单个空格兜底。"""
        factory = ClientFactory([FakeResponse({"code": 200, "data": {}})])
        monkeypatch.setattr(csdn_module.http_client, "client", factory)

        logged_in.publish("标题", "正文", tags="")

        assert factory.calls[0]["json"]["tags"] == " "

    def test_cookies_are_attached_to_the_client(self, logged_in, blocked_images, monkeypatch):
        factory = ClientFactory([FakeResponse({"code": 200, "data": {}})])
        monkeypatch.setattr(csdn_module.http_client, "client", factory)

        logged_in.publish("标题", "正文")

        assert factory.kwargs[0]["cookies"] == logged_in._cookies

    def test_request_goes_to_the_save_endpoint(self, logged_in, blocked_images, monkeypatch):
        factory = ClientFactory([FakeResponse({"code": 200, "data": {}})])
        monkeypatch.setattr(csdn_module.http_client, "client", factory)

        logged_in.publish("标题", "正文")

        assert factory.calls[0]["url"] == SAVE_URL


class TestDraftAndNewArticleFlags:
    def test_new_article_by_default(self, logged_in, blocked_images, monkeypatch):
        factory = ClientFactory([FakeResponse({"code": 200, "data": {}})])
        monkeypatch.setattr(csdn_module.http_client, "client", factory)

        logged_in.publish("标题", "正文")

        payload = factory.calls[0]["json"]
        assert payload["is_new"] == 1
        assert payload["status"] == 0
        assert payload["pubStatus"] == "publish"
        assert "id" not in payload

    def test_draft_flag_changes_status(self, logged_in, blocked_images, monkeypatch):
        factory = ClientFactory([FakeResponse({"code": 200, "data": {}})])
        monkeypatch.setattr(csdn_module.http_client, "client", factory)

        logged_in.publish("标题", "正文", draft=True)

        payload = factory.calls[0]["json"]
        assert payload["status"] == 2
        assert payload["pubStatus"] == "draft"

    def test_existing_article_id_updates_instead_of_creating(
        self, logged_in, blocked_images, monkeypatch
    ):
        factory = ClientFactory([FakeResponse({"code": 200, "data": {}})])
        monkeypatch.setattr(csdn_module.http_client, "client", factory)

        logged_in.publish("标题", "正文", article_id="12345")

        payload = factory.calls[0]["json"]
        assert payload["id"] == 12345
        assert payload["is_new"] == 0

    def test_non_numeric_article_id_is_passed_through(
        self, logged_in, blocked_images, monkeypatch
    ):
        factory = ClientFactory([FakeResponse({"code": 200, "data": {}})])
        monkeypatch.setattr(csdn_module.http_client, "client", factory)

        logged_in.publish("标题", "正文", article_id="abc")

        assert factory.calls[0]["json"]["id"] == "abc"


class TestConfiguredCredentials:
    def test_settings_credentials_override_defaults(
        self, blocked_images, monkeypatch
    ):
        publisher = CsdnPublisher(
            Struct(
                csdn_cookies=json.dumps({"UserName": "me"}),
                ca_key="my-key",
                ca_secret="my-secret",
            )
        )
        factory = ClientFactory([FakeResponse({"code": 200, "data": {}})])
        monkeypatch.setattr(csdn_module.http_client, "client", factory)

        publisher.publish("标题", "正文")

        assert factory.calls[0]["headers"]["x-ca-key"] == "my-key"


class TestFailureHandling:
    def test_http_error_is_reported(self, logged_in, blocked_images, monkeypatch):
        factory = ClientFactory([FakeResponse(status_code=500, text="server exploded")])
        monkeypatch.setattr(csdn_module.http_client, "client", factory)

        result = logged_in.publish("标题", "正文")

        assert result.success is False
        assert "HTTP 500" in result.error

    def test_business_error_message_is_reported(self, logged_in, blocked_images, monkeypatch):
        factory = ClientFactory([FakeResponse({"code": 40001, "msg": "标题不能为空"})])
        monkeypatch.setattr(csdn_module.http_client, "client", factory)

        result = logged_in.publish("", "正文")

        assert result.success is False
        assert result.error == "标题不能为空"

    def test_expired_login_is_detected_and_cleared(
        self, logged_in, blocked_images, monkeypatch
    ):
        factory = ClientFactory([FakeResponse({"code": 401, "msg": "用户未登录"})])
        monkeypatch.setattr(csdn_module.http_client, "client", factory)

        result = logged_in.publish("标题", "正文")

        assert result.success is False
        assert "登录过期" in result.error
        assert logged_in.is_logged_in() is False

    def test_network_error_is_reported(self, logged_in, blocked_images, monkeypatch):
        class Boom:
            def __call__(self, **kwargs):
                return self

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def post(self, *args, **kwargs):
                raise httpx.ConnectError("no route to host")

        monkeypatch.setattr(csdn_module.http_client, "client", Boom())

        result = logged_in.publish("标题", "正文")

        assert result.success is False
        assert "网络错误" in result.error

    def test_unexpected_exception_is_reported(self, logged_in, blocked_images, monkeypatch):
        monkeypatch.setattr(
            csdn_module.mistune, "html", lambda content: (_ for _ in ()).throw(ValueError("boom"))
        )
        factory = ClientFactory([])
        monkeypatch.setattr(csdn_module.http_client, "client", factory)

        result = logged_in.publish("标题", "正文")

        assert result.success is False
        assert "boom" in result.error


class TestImageWarnings:
    def test_warnings_are_carried_into_the_result(self, logged_in, monkeypatch):
        monkeypatch.setattr(
            csdn_image_module,
            "process_markdown_images",
            lambda content, cookies: (content, ["a.png: 上传失败"]),
        )
        factory = ClientFactory([FakeResponse({"code": 200, "data": {}})])
        monkeypatch.setattr(csdn_module.http_client, "client", factory)

        result = logged_in.publish("标题", "![a](a.png)")

        assert result.success is True
        assert result.warnings == ["a.png: 上传失败"]

    def test_empty_content_skips_image_processing(self, logged_in, monkeypatch):
        called = []
        monkeypatch.setattr(
            csdn_image_module,
            "process_markdown_images",
            lambda content, cookies: called.append(1) or (content, []),
        )
        factory = ClientFactory([FakeResponse({"code": 200, "data": {}})])
        monkeypatch.setattr(csdn_module.http_client, "client", factory)

        logged_in.publish("标题", "")

        assert called == []

    def test_converted_content_is_what_gets_sent(self, logged_in, monkeypatch):
        monkeypatch.setattr(
            csdn_image_module,
            "process_markdown_images",
            lambda content, cookies: ("![a](https://img-blog.csdnimg.cn/direct/x.png)", []),
        )
        factory = ClientFactory([FakeResponse({"code": 200, "data": {}})])
        monkeypatch.setattr(csdn_module.http_client, "client", factory)

        logged_in.publish("标题", "![a](local.png)")

        payload = factory.calls[0]["json"]
        assert "img-blog.csdnimg.cn" in payload["markdowncontent"]
        assert "local.png" not in payload["markdowncontent"]
