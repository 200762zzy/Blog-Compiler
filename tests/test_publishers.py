from exporter import Exporter
from publishers.base import PublishResult


def test_publish_result_defaults():
    r = PublishResult(True, "CSDN")
    assert r.success is True
    assert r.platform == "CSDN"
    assert r.url == ""
    assert r.error == ""
    assert r.warnings == []


def test_publish_result_warnings_are_independent():
    a = PublishResult(True, "CSDN")
    b = PublishResult(True, "掘金")
    a.warnings.append("x")
    assert b.warnings == []


def test_publish_result_article_id_default():
    assert PublishResult(True, "CSDN").article_id == ""


def test_publish_result_article_id_set():
    assert PublishResult(True, "CSDN", article_id="123").article_id == "123"


def test_adapt_for_csdn_adds_code_language():
    out = Exporter.adapt_for("CSDN", "```\ncode\n```")
    assert "```text" in out


def test_adapt_for_csdn_fixes_heading_spacing():
    out = Exporter.adapt_for("CSDN", "#标题")
    assert out.startswith("# 标题")


def test_adapt_for_juejin_strips_image_dimensions():
    out = Exporter.adapt_for("掘金", "![a](http://x/y.png =300x)")
    assert "=300x" not in out
    assert "http://x/y.png" in out


def test_adapt_for_unknown_platform_passthrough():
    assert Exporter.adapt_for("Unknown", "abc") == "abc"
