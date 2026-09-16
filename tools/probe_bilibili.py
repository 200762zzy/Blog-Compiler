"""探测 B站 专栏（图文）发布接口。

流程：
  1. 用系统 WebView2 打开 B站登录页，扫码后拿 SESSDATA / bili_jct
  2. 校验登录并获取 wbi 签名所需的 img_key / sub_key
  3. 尝试拉分类列表、创建测试草稿、删除草稿，打印完整响应

只创建一篇**测试草稿**（随后尝试删除），不会发布、不影响已有内容。

运行：py tools/probe_bilibili.py
"""

import hashlib
import io
import json
import sys
import time
import urllib.parse
from pathlib import Path

import httpx

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from login_window import spawn_webview_login

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

_MIXIN_KEY_ENC_TAB = [
    46, 47, 18, 2, 53, 8, 23, 32, 15, 50, 10, 31, 58, 3, 45, 35,
    27, 43, 5, 49, 33, 9, 42, 19, 29, 28, 14, 39, 12, 38, 41, 13,
    37, 48, 7, 16, 24, 55, 40, 61, 26, 17, 0, 1, 60, 51, 30, 4,
    22, 25, 54, 21, 56, 59, 6, 63, 57, 62, 11, 36, 20, 34, 44, 52,
]


def _mixin_key(orig: str) -> str:
    return "".join(orig[i] for i in _MIXIN_KEY_ENC_TAB)[:32]


def sign(params: dict, img_key: str, sub_key: str) -> dict:
    key = _mixin_key(img_key + sub_key)
    p = dict(params)
    p["wts"] = int(time.time())
    ordered = {k: p[k] for k in sorted(p)}
    query = urllib.parse.urlencode(ordered)
    p["w_rid"] = hashlib.md5((query + key).encode()).hexdigest()
    return p


def _pretty(obj):
    try:
        return json.dumps(obj, ensure_ascii=False, indent=2)
    except Exception:
        return str(obj)


def main():
    print("=" * 60)
    print("B站 专栏 API 探测")
    print("=" * 60)

    print("\n[1] 打开 B站 登录窗口（扫码）...")
    cookies, err = spawn_webview_login(
        "https://passport.bilibili.com/login",
        "bilibili.com",
        "登录 B站",
        auth_cookie="SESSDATA",
        timeout=300,
    )
    if not cookies:
        print("登录失败:", err)
        return
    print("登录成功，cookie 数:", len(cookies))
    print("has SESSDATA:", bool(cookies.get("SESSDATA")))
    print("has bili_jct:", bool(cookies.get("bili_jct")))
    print("has DedeUserID:", bool(cookies.get("DedeUserID")))

    cookie_header = "; ".join(f"{k}={v}" for k, v in cookies.items())
    headers = {
        "User-Agent": UA,
        "Referer": "https://member.bilibili.com/",
        "Cookie": cookie_header,
    }
    client = httpx.Client(headers=headers, timeout=30.0, follow_redirects=True)

    print("\n[2] 校验登录 + 获取 wbi keys")
    nav = client.get("https://api.bilibili.com/x/web-interface/nav").json()
    data = nav.get("data", {})
    wbi = data.get("wbi_img", {})
    img_key = wbi.get("img_url", "").rsplit("/", 1)[-1].split(".")[0]
    sub_key = wbi.get("sub_url", "").rsplit("/", 1)[-1].split(".")[0]
    print("isLogin:", data.get("isLogin"), "uname:", data.get("uname"))
    print("img_key:", img_key, "sub_key:", sub_key)

    csrf = cookies.get("bili_jct", "")

    print("\n[3] 尝试获取专栏分类列表")
    for url in [
        "https://api.bilibili.com/x/article/creative/article/category",
        "https://api.bilibili.com/x/article/creative/category/list",
        "https://api.bilibili.com/x/article/creative/article/categories",
    ]:
        try:
            r = client.get(url)
            print(f"  {url} -> HTTP {r.status_code}")
            print("   ", r.text[:300])
        except Exception as e:
            print(f"  {url} -> 异常 {e}")

    print("\n[4] 尝试创建测试草稿 (draft/add)")
    params = {
        "title": "[API探测] 可删除",
        "category": 1,
        "content": "<p>探测脚本创建的测试草稿，可删除。</p>",
        "summary": "探测",
        "template_id": 0,
        "image_urls": "[]",
        "origin_image_urls": "[]",
        "csrf": csrf,
    }
    signed = sign(params, img_key, sub_key)
    try:
        r = client.post("https://api.bilibili.com/x/article/creative/draft/add", data=signed)
        print("HTTP", r.status_code)
        print(_pretty(r.json())[:1800])
        aid = (r.json().get("data") or {}).get("aid")
    except Exception as e:
        print("异常:", e)
        aid = None
    print(">>> 草稿 aid:", aid)

    if aid:
        print("\n[5] 删除测试草稿")
        d = sign({"aid": aid, "csrf": csrf}, img_key, sub_key)
        try:
            rd = client.post("https://api.bilibili.com/x/article/creative/draft/del", data=d)
            print("HTTP", rd.status_code, rd.text[:300])
        except Exception as e:
            print("异常:", e)
    else:
        print("\n未拿到 aid，请把上面的响应发给我。")

    print("\n探测完成。请把完整输出复制给开发者。")


if __name__ == "__main__":
    main()
