"""Standalone WebView2 login helper (runs in a subprocess).

Invoked as:
  <python|exe> --login-webview <json>

where <json> is:
  {
    "url": "<login page url>",
    "domain": "<domain filter>",
    "title": "<window title>",
    "success_prefix": "<url prefix>|null",
    "auth_cookie": "<cookie name that appears after login>|null",
    "outfile": "<path to write result json>|null",
    "timeout": 600
  }

Shows the platform login page in a WebView2 window (pywebview, system WebView2),
waits for the user to finish, then writes {"cookies": {...}} (or {"error": ...})
to <outfile> and prints a MARKER-prefixed line to stdout.

Running in a separate process avoids a GUI-loop conflict with PySide6.
"""

import json
import sys
import time

MARKER = "__BLOGC_COOKIES__"

# Some login pages hand off to the system browser via target=_blank / window.open.
# Redirect those navigations back into the current WebView2 window instead.
_PATCH_JS = """
(function () {
  if (window.__blogcPatched) return;
  window.__blogcPatched = true;
  window.open = function (url) {
    if (url) { window.location.href = url; }
    return null;
  };
})();
"""


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


def _is_success_url(url, domain_filter, success_prefix):
    if not url:
        return False
    if success_prefix:
        return url.startswith(success_prefix)
    low = url.lower()
    return "login" not in low and "passport" not in low and domain_filter in url


def run(config: dict) -> int:
    login_url = config.get("url")
    domain_filter = config.get("domain", "")
    title = config.get("title", "登录")
    success_prefix = config.get("success_prefix")
    auth_cookie = config.get("auth_cookie")
    outfile = config.get("outfile")
    timeout = config.get("timeout", 600)

    try:
        import webview
    except Exception as e:
        _emit({"error": f"pywebview 不可用: {e}"}, outfile)
        return 2

    try:
        webview.settings["OPEN_EXTERNAL_LINKS_IN_BROWSER"] = False
    except Exception:
        pass

    state = {"cookies": None, "error": None}

    window = webview.create_window(title, login_url, width=520, height=740)

    def on_loaded(*args):
        try:
            window.evaluate_js(_PATCH_JS)
        except Exception:
            pass

    try:
        window.events.loaded += on_loaded
    except Exception:
        pass

    def worker():
        start = time.time()
        time.sleep(2)
        while time.time() - start < timeout:
            try:
                cookies = flatten(window.get_cookies())
            except Exception:
                cookies = {}

            if auth_cookie and cookies.get(auth_cookie):
                state["cookies"] = cookies
                break

            if not auth_cookie:
                try:
                    url = window.get_current_url()
                except Exception:
                    url = None
                if _is_success_url(url, domain_filter, success_prefix):
                    state["cookies"] = cookies
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
