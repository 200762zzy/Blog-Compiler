import hashlib
import hmac
from base64 import b64encode

import pytest

from publishers.csdn_sign import (
    DEFAULT_CA_KEY,
    DEFAULT_CA_SECRET,
    build_signature,
    ca_headers,
)

_PATH = "/blog-console-api/v3/mdeditor/saveArticle"


def _expected(method, path, nonce, key, secret):
    to_enc = (
        f"{method}\n*/*\n\napplication/json\n\n"
        f"x-ca-key:{key}\n"
        f"x-ca-nonce:{nonce}\n"
        f"{path}"
    )
    return b64encode(
        hmac.new(secret.encode(), to_enc.encode(), hashlib.sha256).digest()
    ).decode()


def test_signature_matches_documented_template():
    sig = build_signature("POST", _PATH, "nonce-1", "secret-1", "key-1")
    assert sig == _expected("POST", _PATH, "nonce-1", "key-1", "secret-1")


def test_signature_is_deterministic_for_same_inputs():
    a = build_signature("POST", _PATH, "n", "s", "k")
    b = build_signature("POST", _PATH, "n", "s", "k")
    assert a == b


def test_signature_changes_with_nonce_and_path():
    base = build_signature("POST", _PATH, "n1", "s", "k")
    assert build_signature("POST", _PATH, "n2", "s", "k") != base
    assert build_signature("POST", _PATH + "?a=1", "n1", "s", "k") != base


def test_signature_differs_by_method():
    assert build_signature("POST", _PATH, "n", "s", "k") != build_signature(
        "GET", _PATH, "n", "s", "k"
    )


def test_headers_carry_signed_fields():
    headers = ca_headers(_PATH, nonce="fixed-nonce")

    assert headers["x-ca-key"] == DEFAULT_CA_KEY
    assert headers["x-ca-nonce"] == "fixed-nonce"
    assert headers["x-ca-signature-headers"] == "x-ca-key,x-ca-nonce"
    assert headers["x-ca-signature"] == _expected(
        "POST", _PATH, "fixed-nonce", DEFAULT_CA_KEY, DEFAULT_CA_SECRET
    )


def test_headers_generate_a_nonce_when_omitted():
    first = ca_headers(_PATH)
    second = ca_headers(_PATH)
    assert first["x-ca-nonce"] and second["x-ca-nonce"]
    assert first["x-ca-nonce"] != second["x-ca-nonce"]


def test_headers_use_configured_credentials():
    headers = ca_headers(
        _PATH, nonce="n", ca_key="my-key", ca_secret="my-secret"
    )
    assert headers["x-ca-key"] == "my-key"
    assert headers["x-ca-signature"] == _expected("POST", _PATH, "n", "my-key", "my-secret")


def test_headers_include_editor_origin_and_referer():
    headers = ca_headers(_PATH, nonce="n")
    assert headers["Origin"] == "https://editor.csdn.net"
    assert headers["Referer"] == "https://editor.csdn.net/"
    assert headers["Accept"] == "*/*"
    assert headers["content-type"] == "application/json"


def test_headers_omit_user_agent_when_not_requested():
    assert "User-Agent" not in ca_headers(_PATH, nonce="n")


def test_headers_include_user_agent_when_given():
    assert ca_headers(_PATH, nonce="n", user_agent="UA/1")["User-Agent"] == "UA/1"


def test_settings_defaults_come_from_one_place():
    import settings

    assert settings.DEFAULT_CA_KEY == DEFAULT_CA_KEY
    assert settings.DEFAULT_CA_SECRET == DEFAULT_CA_SECRET


@pytest.mark.parametrize("module_name", ["publishers.csdn", "publishers.csdn_image"])
def test_publishers_keep_no_private_ca_copy(module_name):
    import importlib

    module = importlib.import_module(module_name)
    assert not hasattr(module, "_CA_KEY")
    assert not hasattr(module, "_CA_SECRET")
