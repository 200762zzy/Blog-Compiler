from ai_rewriter import AIRewriter, RewriteConfig, _split_into_blocks

import pytest
def _rewriter(chunk_size=100):
    return AIRewriter(RewriteConfig(chunk_size=chunk_size))


def test_small_content_returned_unchanged():
    r = _rewriter(chunk_size=1000)
    content = "# 标题\n\n正文内容"
    assert r._split_content(content) == [content]


def test_split_into_blocks_keeps_fence_intact():
    content = "a\n\n```py\nx\n\ny\n```\n\nb"
    blocks = _split_into_blocks(content)
    assert "```py\nx\n\ny\n```" in blocks


def test_code_block_with_blank_lines_not_split():
    r = _rewriter(chunk_size=60)
    code = "```python\nline1\n\nline2\n\nline3\n```"
    content = ("段落一" * 5) + "\n\n" + code + "\n\n" + ("段落二" * 5)
    chunks = r._split_content(content)
    assert any(code in c for c in chunks)
    for c in chunks:
        assert c.count("```") % 2 == 0


def test_large_code_block_kept_whole():
    r = _rewriter(chunk_size=50)
    code = "```\n" + ("x" * 200) + "\n```"
    chunks = r._split_content(code)
    assert code in chunks


def test_chunks_do_not_exceed_limit_for_paragraphs():
    r = _rewriter(chunk_size=80)
    content = "\n\n".join(["段落" * 10 for _ in range(6)])
    chunks = r._split_content(content)
    assert len(chunks) > 1
    assert all(len(c) <= 80 for c in chunks)


class _FakeStreamResponse:
    def __init__(self, ctype, lines=None, body=None):
        self.status_code = 200
        self.headers = {"content-type": ctype}
        self._lines = lines or []
        self._body = body or {}

    def iter_lines(self):
        return iter(self._lines)

    def read(self):
        pass

    def json(self):
        return self._body


class _FakeStream:
    def __init__(self, resp):
        self._resp = resp

    def __enter__(self):
        return self._resp

    def __exit__(self, *args):
        return False


class _FakeClient:
    def __init__(self, resp):
        self._resp = resp

    def stream(self, *args, **kwargs):
        return _FakeStream(self._resp)


def test_rewrite_stream_parses_sse():
    r = AIRewriter(RewriteConfig(api_key="k"))
    r._client = _FakeClient(
        _FakeStreamResponse(
            "text/event-stream; charset=utf-8",
            lines=[
                'data: {"choices":[{"delta":{"content":"你"}}]}',
                "",
                'data: {"choices":[{"delta":{"content":"好"}}]}',
                "data: [DONE]",
            ],
        )
    )
    parts = []
    out = r.rewrite_stream("hello", on_chunk=parts.append)
    assert out == "你好"
    assert "".join(parts) == "你好"


def test_rewrite_stream_falls_back_to_json():
    r = AIRewriter(RewriteConfig(api_key="k"))
    r._client = _FakeClient(
        _FakeStreamResponse(
            "application/json",
            body={"choices": [{"message": {"content": "fallback"}}]},
        )
    )
    out = r.rewrite_stream("hello")
    assert out == "fallback"


class _FakePostResponse:
    status_code = 200

    def __init__(self, body):
        self._body = body

    def json(self):
        return self._body


class _FakePostClient:
    def __init__(self, body):
        self._body = body

    def post(self, *args, **kwargs):
        return _FakePostResponse(self._body)


def test_generate_meta_parses_json_from_text():
    r = AIRewriter(RewriteConfig(api_key="k"))
    r._client = _FakePostClient(
        {"choices": [{"message": {"content": '好的：{"title":"标题","tags":"a,b","summary":"摘要"}'}}]}
    )
    meta = r.generate_meta("# 文章")
    assert meta == {"title": "标题", "tags": "a,b", "summary": "摘要"}


class _FakeGetResponse:
    def __init__(self, body, status=200):
        self.status_code = status
        self._body = body

    def json(self):
        return self._body


class _FakeGetClient:
    def __init__(self, resp):
        self._resp = resp

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def get(self, *args, **kwargs):
        return self._resp


def test_list_models_parses_sorts_and_dedupes(monkeypatch):
    import ai_rewriter

    monkeypatch.setattr(
        ai_rewriter.http_client,
        "client",
        lambda **kwargs: _FakeGetClient(
            _FakeGetResponse({"data": [{"id": "b"}, {"id": "a"}, {"id": "a"}]})
        ),
    )
    assert AIRewriter.list_models("https://x/v1", "k") == ["a", "b"]


def test_list_models_requires_key():
    with pytest.raises(ValueError):
        AIRewriter.list_models("https://x/v1", "")


def test_supported_models_are_current():
    values = {m["value"] for m in AIRewriter.supported_models()}
    assert "deepseek-v4-pro" in values
    assert "kimi-k3" in values
    assert "glm-5.3" in values
    assert "gpt-4o" not in values
    assert "moonshot-v1-8k" not in values
