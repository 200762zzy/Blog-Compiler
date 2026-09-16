"""Standalone WebView2 login helper (runs in a subprocess).

Invoked as:
  <python|exe> --login-webview <login_url> <domain_filter> <title> [success_prefix]

Shows the platform login page in a WebView2 window (pywebview, using the system
WebView2 runtime), waits for the user to finish scanning/logging in, then prints
a single JSON line prefixed with MARKER to stdout and exits.

Running in a separate process avoids a GUI-loop conflict with PySide6.
"""

import json
import sys
import time

MARKER = "__BLOGC_COOKIES__"


def flatten(cookies) -> dict:
    """pywebview's get_cookies() returns a list of SimpleCookie objects."""
    out = {}
    if cookies is None:
        return out
    if isinstance(cookies, (list, tuple)):
        for item in cookies:
            try:
                for k, morsel in item.items():
                    out[k] = morsel.value if hasattr(morsel, "value") else str(morsel)
            except Exception:
                continue
    elif hasattr(cookies, "items"):
        for k, v in cookies.items():
            out[k] = v.value if hasattr(v, "value") else str(v)
    return out


def _is_success(url, domain_filter, success_prefix):
    if not url:
        return False
    if success_prefix:
        return url.startswith(success_prefix)
    low = url.lower()
    return "login" not in low and "passport" not in low and domain_filter in url


def run(login_url, domain_filter, title="登录", success_prefix=None, outfile=None, timeout=600):
    try:
        import webview
    except Exception as e:
        _emit({"error": f"pywebview 不可用: {e}"}, outfile)
        return 2

    state = {"cookies": None, "error": None}

    window = webview.create_window(title, login_url, width=520, height=740)

    def worker():
        start = time.time()
        time.sleep(2)
        while time.time() - start < timeout:
            try:
                url = window.get_current_url()
            except Exception:
                url = None
            if _is_success(url, domain_filter, success_prefix):
                time.sleep(2)
                try:
                    state["cookies"] = flatten(window.get_cookies())
                except Exception as e:
                    state["error"] = f"获取 Cookie 失败: {e}"
                break
            time.sleep(1)
        try:
            window.destroy()
        except Exception:
            pass

    webview.start(worker)

    if state["cookies"]:
        _emit({"cookies": state["cookies"]}, outfile)
        return 0
    _emit({"error": state["error"] or "登录超时或未获取到 Cookie"}, outfile)
    return 1


def _emit(payload: dict, outfile=None):
    text = json.dumps(payload, ensure_ascii=False)
    if outfile:
        try:
            with open(outfile, "w", encoding="utf-8") as f:
                f.write(text)
        except Exception:
            pass
    print(MARKER + text)
