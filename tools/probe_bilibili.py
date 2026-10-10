"""探测 B站 专栏（图文）发布接口。

流程：
  1. 用系统 WebView2 打开 B站 登录页，扫码后拿 SESSDATA / bili_jct
  2. 校验登录并获取 WBI 签名所需的 img_key / sub_key
  3. 尝试拉分类列表、创建测试草稿、删除草稿，打印完整响应

只创建一篇**测试草稿**（随后尽力删除），不会发布、不影响已有内容。

运行：py tools/probe_bilibili.py

已知情况（改动前请读完）：
  - 删除专栏的接口是**确证**的（见 BAC「图文操作」）：
      POST https://member.bilibili.com/x/web/article/delete   aid=<cvid>&csrf=<bili_jct>
  - 创建/发布专栏的接口**尚未确认**。B站专栏编辑器
      https://member.bilibili.com/platform/upload/text/new-edit
    背后的保存接口没有任何公开文档，下面 CANDIDATES 里都是待验证的猜测，
    脚本会逐个试并把响应原样打印出来。
  - 最可靠的做法是自己在浏览器里抓一次：打开上面的编辑器 → F12 → Network →
    点「保存为草稿」→ 找到那个 POST 请求 → 复制为 cURL，然后把请求内容贴给开发者。
"""

import hashlib
import io
import json
import sys
import time
import urllib.parse
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import http_client
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

# 待验证：创建专栏草稿的候选接口。全部会被尝试，响应原样打印。
CANDIDATES = [
    ("POST", "https://member.bilibili.com/x/web/article/add", "form"),
    ("POST", "https://member.bilibili.com/x/web/article/draft/add", "form"),
    ("POST", "https://api.bilibili.com/x/article/creative/draft/add", "form"),
    ("POST", "https://member.bilibili.com/x/article/creative/draft/add", "form"),
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


def fetch_wbi_keys(client) -> tuple[str, str]:
    nav = client.get("https://api.bilibili.com/x/web-interface/nav").json()
    data = nav.get("data", {})
    wbi = data.get("wbi_img", {})
    img_key = wbi.get("img_url", "").rsplit("/", 1)[-1].split(".")[0]
    sub_key = wbi.get("sub_url", "").rsplit("/", 1)[-1].split(".")[0]
    print("isLogin:", data.get("isLogin"), "uname:", data.get("uname"))
    print("img_key:", img_key, "sub_key:", sub_key)
    return img_key, sub_key


def probe_login(client):
    print("\n[2] 校验登录 + 获取 wbi keys")
    return fetch_wbi_keys(client)


def probe_categories(client):
    print("\n[3] 尝试获取专栏分类列表")
    for url in [
        "https://api.bilibili.com/x/article/creative/article/category",
        "https://member.bilibili.com/x/article/creative/article/category",
        "https://member.bilibili.com/x/web/article/category",
        "https://api.bilibili.com/x/article/creative/category/list",
    ]:
        try:
            r = client.get(url)
            print(f"  {url} -> HTTP {r.status_code}")
            print("   ", r.text[:300])
        except Exception as e:
            print(f"  {url} -> 异常 {e}")


def probe_create_draft(client, img_key, sub_key, csrf):
    print("\n[4] 尝试创建测试草稿（逐个候选接口）")
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

    aid = None
    for method, url, body_kind in CANDIDATES:
        print(f"\n  --- {method} {url} ({body_kind}) ---")
        try:
            if body_kind == "json":
                r = client.post(url, params={"csrf": csrf}, json=signed)
            else:
                r = client.post(url, data=signed)
            print("  HTTP", r.status_code)
            payload = _pretty(r.json())
            print(" ", payload[:900])
            if r.status_code == 200:
                data = r.json()
                if data.get("code") == 0:
                    candidate = (data.get("data") or {}).get("aid") or (
                        data.get("data") or {}
                    ).get("cvid")
                    if candidate:
                        aid = candidate
                        print("  >>> 命中！草稿 id:", aid)
                        break
        except Exception as e:
            print("  异常:", e)
    return aid


def probe_delete(client, img_key, sub_key, csrf, aid):
    print("\n[5] 删除测试草稿（确证接口）")
    url = "https://member.bilibili.com/x/web/article/delete"
    try:
        r = client.post(url, data={"aid": aid, "csrf": csrf})
        print("  HTTP", r.status_code, r.text[:300])
    except Exception as e:
        print("  异常:", e)


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

    csrf = cookies.get("bili_jct", "")
    if not csrf:
        print("⚠️ 缺少 bili_jct，写操作会返回 -111 (csrf 校验失败)")

    # 走共享工厂，代理设置才会生效
    with http_client.client(
        cookies={k: v for k, v in cookies.items()},
        headers={"User-Agent": UA, "Referer": "https://member.bilibili.com/"},
        timeout=30.0,
        follow_redirects=True,
    ) as client:
        img_key, sub_key = probe_login(client)
        if not img_key or not sub_key:
            print("未取到 wbi keys，后续签名会失败，仍继续尝试。")
        probe_categories(client)
        aid = probe_create_draft(client, img_key, sub_key, csrf)
        if aid:
            probe_delete(client, img_key, sub_key, csrf, aid)
        else:
            print("\n未拿到草稿 id —— 说明上面的候选接口都不对。")
            print("请在浏览器里抓一次真实请求，见本文件顶部说明。")

    print("\n探测完成。请把完整输出复制给开发者。")


if __name__ == "__main__":
    main()
