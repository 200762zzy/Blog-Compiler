import json
from pathlib import Path

import httpx
import pytest

import publishers.juejin as juejin_module
from publishers.base import PublishResult
from publishers.juejin import JuejinPublisher

DRAFT_URL = juejin_module._DRAFT_URL
PUBLISH_URL = juejin_module._PUBLISH_URL


class Struct:
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

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("boom", request=None, response=None)


class ClientFactory:
    """每次调用 http_client.client() 都得到一个新的记录器，对应一次 HTTP 请求。"""

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def __call__(self, **kwargs):
        return _Recorder(self)


class _Recorder:
    def __init__(self, factory):
        self.factory = factory

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def _handle(self, method, url, params=None, headers=None, json=None, content=None):
        self.factory.calls.append(
            {"method": method, "url": url, "params": params, "headers": headers,
             "json": json, "content": content}
        )
        return self.factory.responses.pop(0)

    def get(self, url, params=None, headers=None, **kwargs):
        return self._handle("GET", url, params=params, headers=headers)

    def post(self, url, params=None, headers=None, json=None, **kwargs):
        return self._handle("POST", url, params=params, headers=headers, json=json)

    def put(self, url, params=None, headers=None, content=None, **kwargs):
        return self._handle("PUT", url, params=params, headers=headers, content=content)


@pytest.fixture
def logged_in():
    return JuejinPublisher(Struct(juejin_cookies=json.dumps({"sessionid": "s"})))


@pytest.fixture
def no_local_images(monkeypatch):
    """默认让正文里没有本地图片，imagex 上传链不会触发。"""
    monkeypatch.setattr(juejin_module, "Path", lambda p: _MissingPath(p))


class _MissingPath:
    def __init__(self, value):
        self.value = value

    def exists(self):
        return False


def _draft_ok(draft_id="111"):
    return FakeResponse({"err_no": 0, "data": {"id": draft_id}})


def _publish_ok(article_id="222"):
    return FakeResponse({"err_no": 0, "data": {"article_id": article_id}})


class TestLoginState:
    def test_not_logged_in_without_cookies(self):
        assert JuejinPublisher(Struct()).is_logged_in() is False

    def test_logged_in_with_cookies(self, logged_in):
        assert logged_in.is_logged_in() is True

    def test_corrupt_json_is_treated_as_logged_out(self):
        assert JuejinPublisher(Struct(juejin_cookies="not json")).is_logged_in() is False

    def test_logout_clears_and_persists(self, logged_in):
        logged_in.logout()
        assert logged_in.is_logged_in() is False
        assert ("juejin_cookies", "") in logged_in.settings.writes


class TestPublishGuards:
    def test_publish_without_login_returns_failure(self):
        result = JuejinPublisher(Struct()).publish("标题", "正文")
        assert result.success is False
        assert result.platform == "掘金"
        assert "未登录" in result.error


class TestHappyPath:
    def test_creates_draft_then_publishes(self, logged_in, no_local_images, monkeypatch):
        factory = ClientFactory([_draft_ok(), _publish_ok("999")])
        monkeypatch.setattr(juejin_module.http_client, "client", factory)

        result = logged_in.publish("标题", "正文")

        assert result.success is True
        assert result.article_id == "999"
        assert result.url == "https://juejin.cn/post/999"
        assert [c["url"] for c in factory.calls] == [DRAFT_URL, PUBLISH_URL]

    def test_publish_payload_carries_the_draft_id(self, logged_in, no_local_images, monkeypatch):
        factory = ClientFactory([_draft_ok("777"), _publish_ok()])
        monkeypatch.setattr(juejin_module.http_client, "client", factory)

        logged_in.publish("标题", "正文")

        assert factory.calls[1]["json"]["draft_id"] == "777"

    def test_draft_payload_shape(self, logged_in, no_local_images, monkeypatch):
        factory = ClientFactory([_draft_ok(), _publish_ok()])
        monkeypatch.setattr(juejin_module.http_client, "client", factory)

        logged_in.publish("标题", "正文", category_id="c1", tag_ids=["t1", "t2"])

        payload = factory.calls[0]["json"]
        assert payload["title"] == "标题"
        assert payload["mark_content"] == "正文"
        assert payload["category_id"] == "c1"
        assert payload["tag_ids"] == ["t1", "t2"]
        assert payload["edit_type"] == 10

    def test_cookie_header_is_built_from_the_cookie_dict(
        self, logged_in, no_local_images, monkeypatch
    ):
        factory = ClientFactory([_draft_ok(), _publish_ok()])
        monkeypatch.setattr(juejin_module.http_client, "client", factory)

        logged_in.publish("标题", "正文")

        assert factory.calls[0]["headers"]["cookie"] == "sessionid=s"

    def test_zero_article_id_yields_no_url(self, logged_in, no_local_images, monkeypatch):
        factory = ClientFactory([_draft_ok(), _publish_ok("0")])
        monkeypatch.setattr(juejin_module.http_client, "client", factory)

        result = logged_in.publish("标题", "正文")

        assert result.success is True
        assert result.article_id == ""
        assert result.url == ""


class TestBriefContent:
    """掘金对 brief_content 有硬性长度要求：少于 50 个字符接口直接报错。"""

    def test_long_content_is_truncated_to_the_limit(self, logged_in, no_local_images, monkeypatch):
        factory = ClientFactory([_draft_ok(), _publish_ok()])
        monkeypatch.setattr(juejin_module.http_client, "client", factory)

        logged_in.publish("标题", "字" * 300)

        brief = factory.calls[0]["json"]["brief_content"]
        assert len(brief) == juejin_module._BRIEF_MAX

    def test_short_content_reaches_the_minimum(self, logged_in, no_local_images, monkeypatch):
        factory = ClientFactory([_draft_ok(), _publish_ok()])
        monkeypatch.setattr(juejin_module.http_client, "client", factory)

        logged_in.publish("标题", "很短")

        brief = factory.calls[0]["json"]["brief_content"]
        assert len(brief) >= juejin_module._BRIEF_MIN
        assert brief.startswith("很短")

    def test_padding_stays_within_the_upper_bound(self, logged_in, no_local_images, monkeypatch):
        factory = ClientFactory([_draft_ok(), _publish_ok()])
        monkeypatch.setattr(juejin_module.http_client, "client", factory)

        logged_in.publish("标题", "短")

        brief = factory.calls[0]["json"]["brief_content"]
        assert juejin_module._BRIEF_MIN <= len(brief) <= juejin_module._BRIEF_MAX

    def test_every_published_brief_respects_the_bounds(self, logged_in, no_local_images, monkeypatch):
        """不论正文多长多短，摘要长度都必须落在掘金接受的区间里。"""
        for content in ["", "短", "中等长度的一段正文内容用来测试", "很长" * 200]:
            factory = ClientFactory([_draft_ok(), _publish_ok()])
            monkeypatch.setattr(juejin_module.http_client, "client", factory)

            logged_in.publish("标题", content)

            brief = factory.calls[0]["json"]["brief_content"]
            if content:
                assert juejin_module._BRIEF_MIN <= len(brief) <= juejin_module._BRIEF_MAX, content
            else:
                assert brief == ""

    def test_summary_skips_the_heading(self, logged_in, no_local_images, monkeypatch):
        """只截正文开头的话，摘要很可能就是那行标题。"""
        factory = ClientFactory([_draft_ok(), _publish_ok()])
        monkeypatch.setattr(juejin_module.http_client, "client", factory)

        logged_in.publish("标题", "# 我的标题\n\n这是正文的第一段内容。")

        brief = factory.calls[0]["json"]["brief_content"]
        assert brief.startswith("这是正文的第一段内容。")

    def test_summary_falls_back_to_the_heading(self, logged_in, no_local_images, monkeypatch):
        factory = ClientFactory([_draft_ok(), _publish_ok()])
        monkeypatch.setattr(juejin_module.http_client, "client", factory)

        logged_in.publish("标题", "# 只有一个标题")

        brief = factory.calls[0]["json"]["brief_content"]
        assert brief.startswith("只有一个标题")

    def test_summary_strips_markdown_noise(self, logged_in, no_local_images, monkeypatch):
        """摘要显示在信息流里，不该带图片和链接语法。"""
        factory = ClientFactory([_draft_ok(), _publish_ok()])
        monkeypatch.setattr(juejin_module.http_client, "client", factory)

        content = "![截图](a.png) 参考 [官方文档](https://example.com) 的说明。"
        logged_in.publish("标题", content)

        brief = factory.calls[0]["json"]["brief_content"]
        assert "![" not in brief
        assert "a.png" not in brief
        assert "https://example.com" not in brief
        assert "官方文档" in brief

    def test_summary_skips_code_blocks(self, logged_in, no_local_images, monkeypatch):
        factory = ClientFactory([_draft_ok(), _publish_ok()])
        monkeypatch.setattr(juejin_module.http_client, "client", factory)

        content = "```python\nprint('这不是摘要')\n```\n\n这段才是真正的正文说明。"
        logged_in.publish("标题", content)

        brief = factory.calls[0]["json"]["brief_content"]
        assert "这段才是真正的正文说明。" in brief
        assert "print" not in brief


class TestBuildBriefContent:
    """build_brief_content 是纯函数，直接测比透过发布流程更清楚。"""

    def test_empty_content_gives_empty_brief(self):
        from publishers.juejin import build_brief_content

        assert build_brief_content("") == ""

    def test_never_exceeds_upper_bound(self):
        from publishers.juejin import build_brief_content

        for length in (0, 1, 10, 49, 50, 99, 100, 101, 500):
            brief = build_brief_content("字" * length)
            assert len(brief) <= juejin_module._BRIEF_MAX or length == 0

    def test_short_input_meets_the_minimum(self):
        from publishers.juejin import build_brief_content

        assert len(build_brief_content("短")) >= juejin_module._BRIEF_MIN

    def test_is_idempotent_for_compliant_input(self):
        from publishers.juejin import build_brief_content

        once = build_brief_content("正好六十个字的正文内容用来验证补齐逻辑是否稳定可靠不重复处理" * 2)
        assert build_brief_content(once) == once


class TestLocalImageUpload:
    def _setup_local_image(self, monkeypatch, work_dir):
        image = work_dir / "shot.png"
        image.write_bytes(b"png-bytes")
        return image

    def test_local_image_is_uploaded_and_path_replaced(self, logged_in, monkeypatch, work_dir):
        image = self._setup_local_image(monkeypatch, work_dir)

        factory = ClientFactory(
            [
                FakeResponse({"data": "token-abc"}),                      # gen_token
                FakeResponse({"Result": {"UploadAddress": {                # ApplyImageUpload
                    "StoreUri": "store/uri",
                    "UploadHosts": ["upload.example.com"],
                    "SessionKey": "session-key",
                }}}),
                FakeResponse({}),                                          # PUT 上传字节
                FakeResponse({"Result": {"Results": [                      # CommitImageUpload
                    {"ImageUrl": "https://byteimg.com/x.png"}
                ]}}),
                _draft_ok(),                                               # 创建草稿
                _publish_ok(),                                             # 发布
            ]
        )
        monkeypatch.setattr(juejin_module.http_client, "client", factory)

        result = logged_in.publish("标题", f"![截图]({image})")

        assert result.success is True
        assert "byteimg.com/x.png" in factory.calls[4]["json"]["mark_content"]
        assert str(image) not in factory.calls[4]["json"]["mark_content"]

    def test_one_path_being_a_prefix_of_another_does_not_corrupt_content(
        self, logged_in, monkeypatch, work_dir
    ):
        """回归：换图用的是裸字符串替换，短路径会污染长路径。

        短图先上传时 `replace("(a.png)", "(URL)")` 会把 `(a.png.bak)` 变成
        `(URL.bak)`，长图自己的 URL 就贴错了。
        """
        short = work_dir / "a.png"
        long = work_dir / "a.png.bak"
        short.write_bytes(b"short")
        long.write_bytes(b"long")

        uploaded = {
            str(short): "https://byteimg.com/short.png",
            str(long): "https://byteimg.com/long.png",
        }
        monkeypatch.setattr(logged_in, "_upload_image", lambda p: uploaded[p])

        content = f"![短]({short})\n\n![长]({long})"
        result = logged_in._handle_images(content)

        assert "https://byteimg.com/short.png" in result
        assert "https://byteimg.com/long.png" in result
        assert str(short) not in result
        assert str(long) not in result

    def test_image_title_is_preserved_when_replacing(self, logged_in, monkeypatch, work_dir):
        image = self._setup_local_image(monkeypatch, work_dir)
        monkeypatch.setattr(
            logged_in, "_upload_image", lambda p: "https://byteimg.com/x.png"
        )

        result = logged_in._handle_images(f'![截图]({image} "标题")')

        assert "https://byteimg.com/x.png" in result
        assert str(image) not in result

    def test_alt_text_is_preserved(self, logged_in, monkeypatch, work_dir):
        image = self._setup_local_image(monkeypatch, work_dir)
        monkeypatch.setattr(
            logged_in, "_upload_image", lambda p: "https://byteimg.com/x.png"
        )

        result = logged_in._handle_images(f"![终端截图]({image})")

        assert result == "![终端截图](https://byteimg.com/x.png)"

    def test_only_local_images_are_uploaded(self, logged_in, monkeypatch, work_dir):
        image = self._setup_local_image(monkeypatch, work_dir)
        seen = []
        monkeypatch.setattr(
            logged_in, "_upload_image", lambda p: seen.append(p) or "https://byteimg.com/x.png"
        )

        logged_in._handle_images(f"![a]({image})\n\n![b](https://example.com/remote.png)")

        assert seen == [str(image)]

    def test_upload_failure_keeps_the_original_path(self, logged_in, monkeypatch, work_dir):
        image = self._setup_local_image(monkeypatch, work_dir)

        factory = ClientFactory(
            [
                FakeResponse({"data": ""}),   # gen_token 拿不到 token -> 抛异常
                _draft_ok(),
                _publish_ok(),
            ]
        )
        monkeypatch.setattr(juejin_module.http_client, "client", factory)

        result = logged_in.publish("标题", f"![截图]({image})")

        assert result.success is True
        assert str(image) in factory.calls[1]["json"]["mark_content"]

    def test_no_local_images_makes_no_upload_calls(self, logged_in, no_local_images, monkeypatch):
        factory = ClientFactory([_draft_ok(), _publish_ok()])
        monkeypatch.setattr(juejin_module.http_client, "client", factory)

        logged_in.publish("标题", "![a](https://example.com/a.png)")

        assert len(factory.calls) == 2


class TestFailureHandling:
    def test_draft_http_error(self, logged_in, no_local_images, monkeypatch):
        factory = ClientFactory([FakeResponse(status_code=500, text="boom")])
        monkeypatch.setattr(juejin_module.http_client, "client", factory)

        result = logged_in.publish("标题", "正文")

        assert result.success is False
        assert "创建草稿失败" in result.error
        assert "500" in result.error

    def test_draft_business_error(self, logged_in, no_local_images, monkeypatch):
        factory = ClientFactory([FakeResponse({"err_no": 403, "err_msg": "标题重复"})])
        monkeypatch.setattr(juejin_module.http_client, "client", factory)

        result = logged_in.publish("标题", "正文")

        assert result.success is False
        assert "标题重复" in result.error

    def test_missing_draft_id(self, logged_in, no_local_images, monkeypatch):
        factory = ClientFactory([FakeResponse({"err_no": 0, "data": {}})])
        monkeypatch.setattr(juejin_module.http_client, "client", factory)

        result = logged_in.publish("标题", "正文")

        assert result.success is False
        assert "draft_id" in result.error

    def test_publish_step_http_error(self, logged_in, no_local_images, monkeypatch):
        factory = ClientFactory([_draft_ok(), FakeResponse(status_code=502, text="bad")])
        monkeypatch.setattr(juejin_module.http_client, "client", factory)

        result = logged_in.publish("标题", "正文")

        assert result.success is False
        assert "发布失败" in result.error

    def test_publish_step_business_error(self, logged_in, no_local_images, monkeypatch):
        factory = ClientFactory([_draft_ok(), FakeResponse({"err_no": 1, "err_msg": "内容违规"})])
        monkeypatch.setattr(juejin_module.http_client, "client", factory)

        result = logged_in.publish("标题", "正文")

        assert result.success is False
        assert "内容违规" in result.error

    def test_login_error_clears_cookies(self, logged_in, no_local_images, monkeypatch):
        factory = ClientFactory([FakeResponse({"err_no": 1, "err_msg": "login required"})])
        monkeypatch.setattr(juejin_module.http_client, "client", factory)

        result = logged_in.publish("标题", "正文")

        assert result.success is False
        assert logged_in.is_logged_in() is False

    def test_network_error_is_reported(self, logged_in, no_local_images, monkeypatch):
        class Boom:
            def __call__(self, **kwargs):
                return self

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def post(self, *args, **kwargs):
                raise httpx.ConnectError("no route")

        monkeypatch.setattr(juejin_module.http_client, "client", Boom())

        result = logged_in.publish("标题", "正文")

        assert result.success is False
        assert "网络错误" in result.error
