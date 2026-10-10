import json

import pytest

import publishers
from publishers import get_publisher, get_publishers, init_publishers
from publishers.base import BasePublisher, PublishResult
from publishers.cnblogs import CnblogsPublisher
from publishers.csdn import CsdnPublisher
from publishers.juejin import JuejinPublisher


class Struct:
    def __init__(self, **values):
        self.data = dict(values)

    def get(self, key, default=None):
        return self.data.get(key, default)

    def set(self, key, value):
        self.data[key] = value


@pytest.fixture(autouse=True)
def clean_registry():
    """每个用例都从空注册表开始，避免互相污染。"""
    publishers._REGISTRY.clear()
    yield
    publishers._REGISTRY.clear()


class TestRegistry:
    def test_init_registers_the_three_platforms(self):
        init_publishers(Struct())
        assert {p.name for p in get_publishers()} == {"CSDN", "掘金", "博客园"}

    def test_registry_holds_the_expected_types(self):
        init_publishers(Struct())
        assert isinstance(get_publisher("CSDN"), CsdnPublisher)
        assert isinstance(get_publisher("掘金"), JuejinPublisher)
        assert isinstance(get_publisher("博客园"), CnblogsPublisher)

    def test_unknown_platform_returns_none(self):
        init_publishers(Struct())
        assert get_publisher("知乎") is None

    def test_empty_registry_returns_empty_list(self):
        assert get_publishers() == []

    def test_get_publishers_returns_a_copy(self):
        """调用方拿到列表后随手改动，不应影响注册表本身。"""
        init_publishers(Struct())
        snapshot = get_publishers()
        snapshot.clear()
        assert len(get_publishers()) == 3

    def test_reinit_replaces_previous_instances(self):
        init_publishers(Struct())
        first = get_publisher("CSDN")
        init_publishers(Struct())
        assert get_publisher("CSDN") is not first

    def test_reinit_does_not_leave_duplicates(self):
        init_publishers(Struct())
        init_publishers(Struct())
        assert len(get_publishers()) == 3


class TestAccountSwitchPropagates:
    """账号管理切换后会重新 init_publishers()，新凭据必须真正生效。"""

    def test_switched_cookies_are_picked_up(self):
        init_publishers(Struct(csdn_cookies=""))
        assert get_publisher("CSDN").is_logged_in() is False

        init_publishers(Struct(csdn_cookies=json.dumps({"UserName": "other"})))
        publisher = get_publisher("CSDN")
        assert publisher.is_logged_in() is True
        assert publisher._cookies == {"UserName": "other"}

    def test_switched_cnblogs_credentials_are_picked_up(self):
        init_publishers(Struct())
        assert get_publisher("博客园").is_logged_in() is False

        init_publishers(Struct(cnblogs_username="me", cnblogs_api_key="k"))
        assert get_publisher("博客园").is_logged_in() is True


class _DummyPublisher(BasePublisher):
    name = "测试平台"

    def is_logged_in(self) -> bool:
        return True

    def publish(self, title, content, **kwargs) -> PublishResult:
        return PublishResult(True, self.name)


class TestBasePublisher:
    def test_adapt_content_uses_the_exporter(self):
        """基类应把平台名交给 Exporter，未注册的适配器原样返回。"""
        publisher = _DummyPublisher()
        assert publisher.adapt_content("#标题") == "#标题"

    def test_display_name_defaults_to_name(self):
        assert _DummyPublisher().display_name == "测试平台"

    def test_login_and_logout_have_neutral_defaults(self):
        publisher = _DummyPublisher()
        assert publisher.login() is True
        assert publisher.logout() is None


def test_publish_result_is_shared_across_publishers():
    """三个发布器都返回同一种结果对象，界面才能统一渲染。"""
    init_publishers(Struct())
    for publisher in get_publishers():
        result = publisher.publish("标题", "正文")
        assert isinstance(result, PublishResult)
        assert result.platform == publisher.name
