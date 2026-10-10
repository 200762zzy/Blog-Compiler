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


class _RejectingResponse:
    """400 + 明文指向 max_completion_tokens，模拟新一代 OpenAI 模型的拒绝。"""

    status_code = 400

    def __init__(self, text=None):
        self.text = text or (
            "Unsupported parameter: 'max_tokens' is not supported with this model. "
            "Use 'max_completion_tokens' instead."
        )

    def json(self):
        raise ValueError("no json")


class _RecordingClient:
    """记录每次请求的 payload，用来断言重试时参数被换掉了。"""

    def __init__(self, responses):
        self._responses = list(responses)
        self.payloads = []

    def post(self, url, json=None, headers=None):
        self.payloads.append(json)
        return self._responses.pop(0)

    def stream(self, method, url, json=None, headers=None):
        self.payloads.append(json)
        return _FakeStream(self._responses.pop(0))


class TestMaxTokensFallback:
    """GPT-5 系列不接受 max_tokens，会直接 400；必须自动换成 max_completion_tokens。"""

    def test_detects_only_the_specific_rejection(self):
        from ai_rewriter import needs_max_completion_tokens

        assert needs_max_completion_tokens(_RejectingResponse()) is True

    def test_plain_400_is_not_treated_as_parameter_mismatch(self):
        from ai_rewriter import needs_max_completion_tokens

        assert needs_max_completion_tokens(_RejectingResponse(text="invalid api key")) is False

    def test_other_status_codes_are_not_retried(self):
        from ai_rewriter import needs_max_completion_tokens

        resp = _RejectingResponse()
        resp.status_code = 401
        assert needs_max_completion_tokens(resp) is False

    def test_rewrite_replaces_parameter_name(self):
        from ai_rewriter import retry_with_max_completion_tokens

        original = {"model": "m", "max_tokens": 1024, "temperature": 0.7, "stream": True}
        retried = retry_with_max_completion_tokens(original)
        assert "max_tokens" not in retried
        assert retried["max_completion_tokens"] == 1024
        assert retried["temperature"] == 0.7
        assert retried["stream"] is True
        assert list(retried) == ["model", "max_completion_tokens", "temperature", "stream"]

    def test_non_streaming_call_retries_with_new_parameter(self):
        r = AIRewriter(RewriteConfig(api_key="k", model="gpt-5.5", max_tokens=512))
        client = _RecordingClient(
            [
                _RejectingResponse(),
                _FakePostResponse({"choices": [{"message": {"content": "改写结果"}}]}),
            ]
        )
        r._client = client

        text, _reason = r._call_api("原文")

        assert text == "改写结果"
        assert len(client.payloads) == 2
        assert client.payloads[0]["max_tokens"] == 512
        assert client.payloads[1]["max_completion_tokens"] == 512
        assert "max_tokens" not in client.payloads[1]

    def test_failure_is_still_reported_when_retry_also_fails(self):
        r = AIRewriter(RewriteConfig(api_key="k", model="gpt-5.5"))
        r._client = _RecordingClient([_RejectingResponse(), _RejectingResponse()])

        with pytest.raises(RuntimeError, match="API 请求失败"):
            r._call_api("原文")

    def test_successful_call_sends_max_tokens_unchanged(self):
        r = AIRewriter(RewriteConfig(api_key="k", model="deepseek-v4-pro", max_tokens=2048))
        client = _RecordingClient(
            [_FakePostResponse({"choices": [{"message": {"content": "ok"}}]})]
        )
        r._client = client

        r._call_api("原文")

        assert client.payloads[0]["max_tokens"] == 2048
        assert len(client.payloads) == 1


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


def test_supported_models_are_well_formed():
    models = AIRewriter.supported_models()
    assert models, "预设不能为空"

    for m in models:
        assert m["label"] and m["value"], m
        assert isinstance(m["base"], str), m

    # 具体型号会随厂商更新，不该在测试里钉死；但预设必须自洽：
    assert len({m["label"] for m in models}) == len(models), "label 不能重复"
    # 非 custom 的预设必须能推出 API 地址，否则选完模型会发不出去
    for m in models:
        if m["value"] != "custom":
            assert m["base"].startswith("http"), m


def test_default_config_points_at_the_first_preset():
    """默认值只能有一个来源，否则界面显示 A 厂商、请求发去 B 厂商。"""
    from ai_rewriter import DEFAULT_API_BASE, DEFAULT_MODEL, default_config

    first = AIRewriter.supported_models()[0]
    assert (DEFAULT_MODEL, DEFAULT_API_BASE) == (first["value"], first["base"])

    config = default_config()
    assert (config.model, config.api_base) == (DEFAULT_MODEL, DEFAULT_API_BASE)


def test_rewriter_fills_in_blank_model_and_base():
    from ai_rewriter import DEFAULT_API_BASE, DEFAULT_MODEL

    rewriter = AIRewriter(RewriteConfig(api_key="k"))
    assert rewriter.config.model == DEFAULT_MODEL
    assert rewriter.config.api_base == DEFAULT_API_BASE


def test_rewriter_keeps_explicit_model_and_base():
    rewriter = AIRewriter(
        RewriteConfig(api_key="k", model="my-model", api_base="https://mine/v1")
    )
    assert rewriter.config.model == "my-model"
    assert rewriter.config.api_base == "https://mine/v1"


def test_default_model_is_a_real_preset():
    from ai_rewriter import DEFAULT_MODEL

    assert DEFAULT_MODEL in {m["value"] for m in AIRewriter.supported_models()}


class TestResolveModelName:
    """下拉框可编辑，选中预设时 currentText() 是 label，不能直接当模型名发出去。"""

    def test_label_is_mapped_to_value(self):
        from ai_rewriter import resolve_model_name

        for m in AIRewriter.supported_models():
            assert resolve_model_name(m["label"]) == m["value"]

    def test_value_passes_through(self):
        from ai_rewriter import resolve_model_name

        assert resolve_model_name("gpt-5.4-mini") == "gpt-5.4-mini"

    def test_custom_text_passes_through(self):
        from ai_rewriter import resolve_model_name

        assert resolve_model_name("my-local-llama") == "my-local-llama"

    def test_blank_falls_back_to_default(self):
        from ai_rewriter import DEFAULT_MODEL, resolve_model_name

        assert resolve_model_name("") == DEFAULT_MODEL
        assert resolve_model_name("   ") == DEFAULT_MODEL
        assert resolve_model_name(None) == DEFAULT_MODEL

    def test_surrounding_whitespace_is_trimmed(self):
        from ai_rewriter import resolve_model_name

        assert resolve_model_name("  kimi-k3  ") == "kimi-k3"
