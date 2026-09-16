from login_window import parse_cookie_text


def test_parse_cookie_semicolon():
    assert parse_cookie_text("a=1; b=2") == {"a": "1", "b": "2"}


def test_parse_cookie_newlines():
    assert parse_cookie_text("a=1\nb=2") == {"a": "1", "b": "2"}


def test_parse_cookie_json():
    assert parse_cookie_text('{"a": "1", "b": {"value": "2"}}') == {"a": "1", "b": "2"}


def test_parse_cookie_empty():
    assert parse_cookie_text("") == {}
    assert parse_cookie_text("   ") == {}


def test_parse_cookie_ignores_garbage():
    assert parse_cookie_text("; ; invalid ; a=1") == {"a": "1"}
