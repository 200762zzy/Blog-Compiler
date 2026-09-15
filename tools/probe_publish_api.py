"""探测 CSDN / 掘金的发布接口响应结构（用于实现「更新已发布文章」）。

脚本会创建一篇**测试草稿**（不会发布、不影响任何已有文章），
打印完整 JSON 响应，用来确认：
  - 创建接口是否返回文章 ID（draft_id / articleId）
  - 更新接口的参数与响应结构

随后会尽力删除测试草稿（掘金支持删除；CSDN 请到草稿箱手动删除）。

运行：py tools/probe_publish_api.py
"""

import io
import json
import sys
import uuid
from pathlib import Path
from urllib.parse import urlparse

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import http_client
from settings import Settings


def _pretty(obj):
    try:
        return json.dumps(obj, ensure_ascii=False, indent=2)
    except Exception:
        return str(obj)


def probe_csdn(settings):
    print("\n" + "=" * 60)
    print("CSDN 探测")
    print("=" * 60)

    raw = settings.get("csdn_cookies")
    if not raw:
        print("未登录 CSDN，跳过。请在程序中登录后重试。")
        return
    try:
        cookies = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        print("CSDN Cookie 解析失败，跳过。")
        return

    import hmac
    import hashlib
    from base64 import b64encode

    from publishers.csdn import _SAVE_URL, _CA_KEY, _CA_SECRET, _USER_AGENT

    ca_key = settings.get("ca_key") or _CA_KEY
    ca_secret = settings.get("ca_secret") or _CA_SECRET

    def save(payload):
        nonce = str(uuid.uuid4())
        parsed = urlparse(_SAVE_URL)
        path = parsed.path + ("?" + parsed.query if parsed.query else "")
        to_enc = (
            f"POST\n*/*\n\napplication/json\n\n"
            f"x-ca-key:{ca_key}\n"
            f"x-ca-nonce:{nonce}\n"
            f"{path}"
        )
        sign = b64encode(
            hmac.new(ca_secret.encode(), to_enc.encode(), hashlib.sha256).digest()
        ).decode()
        headers = {
            "x-ca-key": ca_key,
            "x-ca-nonce": nonce,
            "x-ca-signature": sign,
            "x-ca-signature-headers": "x-ca-key,x-ca-nonce",
            "content-type": "application/json",
            "origin": "https://editor.csdn.net",
            "referer": "https://editor.csdn.net/",
            "user-agent": _USER_AGENT,
        }
        with http_client.client(cookies=cookies, timeout=30.0) as client:
            return client.post(_SAVE_URL, headers=headers, json=payload)

    base = {
        "title": "[API探测] 可删除",
        "markdowncontent": "这是探测脚本创建的测试草稿，可删除。",
        "content": "<p>这是探测脚本创建的测试草稿，可删除。</p>",
        "readType": "public",
        "tags": " ",
        "status": 2,
        "categories": "",
        "type": "original",
        "original_link": "",
        "authorized_status": False,
        "not_auto_saved": "1",
        "source": "pc_mdeditor",
        "cover_images": [],
        "cover_type": 0,
        "is_new": 1,
        "vote_id": 0,
        "pubStatus": "draft",
    }

    print("\n[1] 创建测试草稿 (is_new=1) ...")
    resp = save(dict(base))
    print("HTTP", resp.status_code)
    try:
        data = resp.json()
    except Exception:
        print("非 JSON 响应:", resp.text[:500])
        return
    print(_pretty(data))

    info = data.get("data") or {}
    aid = info.get("id") or info.get("articleId") or ""
    url = info.get("url") or ""
    if not aid and url:
        tail = url.rstrip("/").split("/")[-1]
        if tail.isdigit():
            aid = tail
    print("\n>>> 推断的文章 ID:", aid or "(未找到)")
    print(">>> 草稿链接:", url or "(无)")

    if aid:
        print("\n[2] 尝试更新该草稿 (articleId + is_new=0) ...")
        upd = dict(base)
        upd["articleId"] = aid
        upd["is_new"] = 0
        resp2 = save(upd)
        print("HTTP", resp2.status_code)
        try:
            print(_pretty(resp2.json()))
        except Exception:
            print("非 JSON 响应:", resp2.text[:500])
        print("\n若 [2] 返回成功且未新建文章，则更新接口可用。")
    else:
        print("\n未拿到文章 ID，无法验证更新；请把上面的响应发给我。")


def probe_juejin(settings):
    print("\n" + "=" * 60)
    print("掘金 探测")
    print("=" * 60)

    raw = settings.get("juejin_cookies")
    if not raw:
        print("未登录掘金，跳过。请在程序中登录后重试。")
        return
    try:
        cookies = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        print("掘金 Cookie 解析失败，跳过。")
        return

    from publishers.juejin import (
        _DRAFT_URL, _HEADERS_BASE, _build_cookie_header,
        _DEFAULT_CATEGORY_ID, _DEFAULT_TAG_IDS,
    )

    headers = {**_HEADERS_BASE, "cookie": _build_cookie_header(cookies)}
    draft_payload = {
        "category_id": _DEFAULT_CATEGORY_ID,
        "tag_ids": _DEFAULT_TAG_IDS,
        "title": "[API探测] 可删除",
        "brief_content": "探测脚本创建的测试草稿，可删除。",
        "edit_type": 10,
        "mark_content": "这是探测脚本创建的测试草稿，可删除。",
        "cover_image": "",
        "html_content": "deprecated",
        "link_url": "",
        "theme_ids": [],
    }

    print("\n[1] 创建测试草稿 ...")
    with http_client.client(timeout=30.0) as client:
        resp = client.post(_DRAFT_URL, headers=headers, json=draft_payload)
    print("HTTP", resp.status_code)
    try:
        data = resp.json()
    except Exception:
        print("非 JSON 响应:", resp.text[:500])
        return
    print(_pretty(data))

    draft_id = (data.get("data") or {}).get("id")
    print("\n>>> draft_id:", draft_id or "(未找到)")

    if draft_id:
        print("\n[2] 尝试更新草稿 (article_draft/update) ...")
        upd_url = "https://api.juejin.cn/content_api/v1/article_draft/update"
        upd_payload = dict(draft_payload)
        upd_payload["id"] = draft_id
        upd_payload["draft_id"] = draft_id
        with http_client.client(timeout=30.0) as client:
            r2 = client.post(upd_url, headers=headers, json=upd_payload)
        print("HTTP", r2.status_code)
        try:
            print(_pretty(r2.json()))
        except Exception:
            print("非 JSON 响应:", r2.text[:500])

        print("\n[3] 删除测试草稿 ...")
        del_url = "https://api.juejin.cn/content_api/v1/article_draft/delete"
        with http_client.client(timeout=30.0) as client:
            r3 = client.post(del_url, headers=headers, json={"draft_id": draft_id})
        print("HTTP", r3.status_code)
        try:
            print(_pretty(r3.json()))
        except Exception:
            print(r3.text[:300])
    else:
        print("\n未拿到 draft_id，无法验证更新；请把上面的响应发给我。")


def main():
    settings = Settings()
    http_client.set_proxy(settings.get("http_proxy", ""))

    print("提示：本脚本只创建测试草稿，不发布、不改动已有文章。")
    probe_csdn(settings)
    probe_juejin(settings)
    print("\n探测完成。请把上面的完整输出复制给开发者。")


if __name__ == "__main__":
    main()
