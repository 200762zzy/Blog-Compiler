import json
import re
from dataclasses import dataclass

import httpx

import http_client


@dataclass
class RewriteConfig:
    api_key: str = ""
    api_base: str = ""
    model: str = ""
    temperature: float = 0.7
    max_tokens: int = 32768
    chunk_size: int = 8000
    system_prompt: str = ""


#: 模型预设。列表第一项就是「未配置时的默认厂商」。
#: 所有默认值都从这里取，不要在别处再写一份模型名，否则会出现
#: 「界面显示一个厂商、实际请求发到另一个」这类矛盾。
SUPPORTED_MODELS: list[dict] = [
    {"label": "OpenAI GPT-5.5", "value": "gpt-5.5", "base": "https://api.openai.com/v1"},
    {"label": "OpenAI GPT-5.4-mini", "value": "gpt-5.4-mini", "base": "https://api.openai.com/v1"},
    {"label": "DeepSeek-V4-Pro", "value": "deepseek-v4-pro", "base": "https://api.deepseek.com/v1"},
    {"label": "DeepSeek-Flash", "value": "deepseek-flash", "base": "https://api.deepseek.com/v1"},
    {"label": "Kimi K3", "value": "kimi-k3", "base": "https://api.moonshot.cn/v1"},
    {"label": "Kimi K2.6", "value": "kimi-k2.6", "base": "https://api.moonshot.cn/v1"},
    {"label": "通义 Qwen3.8-Max", "value": "qwen3.8-max", "base": "https://dashscope.aliyuncs.com/compatible-mode/v1"},
    {"label": "通义 Qwen3.8-Flash", "value": "qwen3.8-flash", "base": "https://dashscope.aliyuncs.com/compatible-mode/v1"},
    {"label": "智谱 GLM-5.3", "value": "glm-5.3", "base": "https://open.bigmodel.cn/api/paas/v4"},
    {"label": "智谱 GLM-4.7", "value": "glm-4.7", "base": "https://open.bigmodel.cn/api/paas/v4"},
    {"label": "硅基流动 (点刷新获取)", "value": "custom", "base": "https://api.siliconflow.cn/v1"},
    {"label": "火山方舟 (点刷新获取)", "value": "custom", "base": "https://ark.cn-beijing.volces.com/api/v3"},
    {"label": "OpenRouter (点刷新获取)", "value": "custom", "base": "https://openrouter.ai/api/v1"},
    {"label": "Ollama 本地 (点刷新获取)", "value": "custom", "base": "http://localhost:11434/v1"},
    {"label": "自定义 (可编辑)", "value": "custom", "base": ""},
]

DEFAULT_MODEL = SUPPORTED_MODELS[0]["value"]
DEFAULT_API_BASE = SUPPORTED_MODELS[0]["base"]


def default_config(api_key: str = "") -> RewriteConfig:
    """带默认厂商的配置对象，免得默认值散落各处而互相矛盾。"""
    return RewriteConfig(
        api_key=api_key, api_base=DEFAULT_API_BASE, model=DEFAULT_MODEL
    )


def resolve_model_name(model_text: str) -> str:
    """把下拉框里的文本解析成模型 ID。

    下拉框是可编辑的：用户选中预设项时拿到的是 label（如 "OpenAI GPT-5.5"），
    这个文本不能直接当模型名发给 API，要还原成 value；
    只有真正手输的自定义名字才原样使用。
    """
    candidate = (model_text or "").strip()
    if not candidate:
        return DEFAULT_MODEL
    for entry in SUPPORTED_MODELS:
        if candidate in (entry["label"], entry["value"]):
            return entry["value"]
    return candidate


CONTINUATION_PROMPT = """请继续保持与上文一致的风格和语气，直接接着改写下面的内容。
不要重复前文内容，不要加总结性语句，直接从断点处继续：

{content}"""


def _error_detail(resp) -> str:
    detail = f"HTTP {resp.status_code}"
    try:
        detail += f"\n响应: {resp.json()}"
    except Exception:
        detail += f"\n响应: {resp.text[:500]}"
    return detail


def needs_max_completion_tokens(resp) -> bool:
    """判断这次失败是不是「不接受 max_tokens」造成的。

    OpenAI 的新一代模型（GPT-5 系列等）把 max_tokens 换成了
    max_completion_tokens，旧参数名会直接返回 400。只在错误信息明确提到
    新参数名时才回退，避免把真正的错误（如 Key 无效）吞掉重试。
    """
    if getattr(resp, "status_code", 0) != 400:
        return False
    body = getattr(resp, "text", "") or ""
    return "max_completion_tokens" in body


def retry_with_max_completion_tokens(payload: dict) -> dict:
    """把 payload 里的 max_tokens 换成新参数名，保留其余字段与顺序。"""
    retried = {}
    for key, value in payload.items():
        retried["max_completion_tokens" if key == "max_tokens" else key] = value
    return retried


def _split_into_blocks(content: str) -> list[str]:
    """Split markdown into blocks, keeping fenced code blocks atomic.

    Fenced code blocks (``` or ~~~) are never split internally, so chunked
    rewriting cannot cut a code block in half or mangle its contents.
    """
    blocks: list[str] = []
    para: list[str] = []
    code: list[str] = []
    in_fence = False
    fence = ""

    def flush_para():
        if not para:
            return
        text = "\n".join(para)
        para.clear()
        for part in re.split(r"\n[ \t]*\n", text):
            if part.strip():
                blocks.append(part.strip("\n"))

    for line in content.split("\n"):
        stripped = line.lstrip()
        if in_fence:
            code.append(line)
            if stripped.startswith(fence):
                blocks.append("\n".join(code))
                code.clear()
                in_fence = False
            continue
        if stripped.startswith("```") or stripped.startswith("~~~"):
            flush_para()
            in_fence = True
            fence = "```" if stripped.startswith("```") else "~~~"
            code.append(line)
            continue
        para.append(line)

    if in_fence:
        blocks.append("\n".join(code))
        code.clear()
    flush_para()
    return blocks


class AIRewriter:
    def __init__(self, config: RewriteConfig | None = None):
        self.config = config or default_config()
        if not self.config.api_base:
            self.config.api_base = DEFAULT_API_BASE
        if not self.config.model:
            self.config.model = DEFAULT_MODEL
        self.last_error = ""
        self._cancelled = False
        self._client = http_client.client(timeout=120.0)

    def cancel(self):
        self._cancelled = True

    def rewrite(self, markdown_content: str) -> str:
        self._cancelled = False
        if not self.config.api_key:
            raise ValueError("API Key 未设置，请在设置中配置")

        chunks = self._split_content(markdown_content)
        all_parts = []

        for i, chunk in enumerate(chunks):
            if self._cancelled:
                break

            if i == 0:
                full, reason = self._call_api(chunk)
            else:
                prompt = CONTINUATION_PROMPT.format(content=chunk)
                full, reason = self._call_api(prompt, is_continuation=True)

            all_parts.append(full)

            if reason == "length":
                self.last_error = "output truncated by token limit, consider increasing max_tokens"

        return "\n\n".join(all_parts)

    def rewrite_stream(self, markdown_content: str, on_chunk=None) -> str:
        """Like rewrite(), but emits text incrementally via on_chunk(text)."""
        self._cancelled = False
        if not self.config.api_key:
            raise ValueError("API Key 未设置，请在设置中配置")

        chunks = self._split_content(markdown_content)
        all_parts = []

        for i, chunk in enumerate(chunks):
            if self._cancelled:
                break

            if i == 0:
                content = chunk
                is_continuation = False
            else:
                content = CONTINUATION_PROMPT.format(content=chunk)
                is_continuation = True

            if i > 0 and on_chunk:
                on_chunk("\n\n")

            all_parts.append(self._stream_call(content, is_continuation, on_chunk))

        return "\n\n".join(all_parts)

    def _request_payload(self, content: str, is_continuation: bool, **extra) -> dict:
        system_content = self.config.system_prompt
        if is_continuation:
            system_content = "你正在继续改写一篇文章，保持风格一致，直接继续。"
        return {
            "model": self.config.model,
            "messages": [
                {"role": "system", "content": system_content},
                {"role": "user", "content": content},
            ],
            "temperature": self.config.temperature,
            "max_tokens": self.config.max_tokens,
            **extra,
        }

    def _stream_call(self, content: str, is_continuation: bool, on_chunk) -> str:
        self.last_error = ""
        headers = {
            "Authorization": f"Bearer {self.config.api_key}",
            "Content-Type": "application/json",
        }
        payload = self._request_payload(content, is_continuation, stream=True)

        url = f"{self.config.api_base.rstrip('/')}/chat/completions"
        collected = []

        with self._client.stream("POST", url, json=payload, headers=headers) as resp:
            if resp.status_code != 200:
                resp.read()
                if needs_max_completion_tokens(resp):
                    payload = retry_with_max_completion_tokens(payload)
                    resp = self._client.post(url, json=payload, headers=headers)
                    if resp.status_code != 200:
                        self.last_error = _error_detail(resp)
                        raise RuntimeError(f"API 请求失败\n{self.last_error}")
                    ctype = resp.headers.get("content-type", "")
                    if "event-stream" not in ctype:
                        data = resp.json()
                        choices = data.get("choices", [])
                        if not choices:
                            raise RuntimeError(f"API 返回异常 (无 choices): {data}")
                        text = choices[0]["message"]["content"].strip()
                        if on_chunk:
                            on_chunk(text)
                        return text
                    return self._consume_stream(resp, on_chunk, collected)

                self.last_error = _error_detail(resp)
                raise RuntimeError(f"API 请求失败\n{self.last_error}")

            ctype = resp.headers.get("content-type", "")
            if "event-stream" not in ctype:
                data = resp.json()
                choices = data.get("choices", [])
                if not choices:
                    raise RuntimeError(f"API 返回异常 (无 choices): {data}")
                text = choices[0]["message"]["content"].strip()
                if on_chunk:
                    on_chunk(text)
                return text

            return self._consume_stream(resp, on_chunk, collected)

    def _consume_stream(self, resp, on_chunk, collected: list) -> str:
        for line in resp.iter_lines():
            if self._cancelled:
                break
            if not line:
                continue
            data_str = line[5:].strip() if line.startswith("data:") else line.strip()
            if not data_str or data_str == "[DONE]":
                continue
            try:
                obj = json.loads(data_str)
            except json.JSONDecodeError:
                continue
            choices = obj.get("choices") or []
            if not choices:
                continue
            delta = choices[0].get("delta") or {}
            piece = delta.get("content")
            if piece:
                collected.append(piece)
                if on_chunk:
                    on_chunk(piece)
            if choices[0].get("finish_reason") == "length":
                self.last_error = "output truncated by token limit, consider increasing max_tokens"

        return "".join(collected)

    def _call_api(self, content: str, is_continuation: bool = False) -> tuple[str, str]:
        self.last_error = ""
        headers = {
            "Authorization": f"Bearer {self.config.api_key}",
            "Content-Type": "application/json",
        }
        payload = self._request_payload(content, is_continuation)

        url = f"{self.config.api_base.rstrip('/')}/chat/completions"
        resp = self._client.post(url, json=payload, headers=headers)

        if resp.status_code != 200 and needs_max_completion_tokens(resp):
            payload = retry_with_max_completion_tokens(payload)
            resp = self._client.post(url, json=payload, headers=headers)

        if resp.status_code != 200:
            self.last_error = _error_detail(resp)
            raise RuntimeError(f"API 请求失败\n{self.last_error}")

        data = resp.json()
        choices = data.get("choices", [])
        if not choices:
            raise RuntimeError(f"API 返回异常 (无 choices): {data}")

        finish_reason = choices[0].get("finish_reason", "stop")
        return choices[0]["message"]["content"].strip(), finish_reason

    def generate_meta(self, markdown_content: str) -> dict:
        """Ask the model for a title / tags / summary for the given article."""
        if not self.config.api_key:
            raise ValueError("API Key 未设置，请在设置中配置")

        prompt = (
            "请根据下面的 Markdown 文章，生成一个 JSON 对象（只输出 JSON，"
            "不要包含解释或代码块标记）：\n"
            '{"title": "不超过 30 字的吸引人标题", '
            '"tags": "逗号分隔的 3-5 个标签", '
            '"summary": "不超过 80 字的摘要"}\n\n'
            "文章内容：\n" + markdown_content[:4000]
        )
        headers = {
            "Authorization": f"Bearer {self.config.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.config.model,
            "messages": [
                {"role": "system", "content": "你是资深技术编辑，擅长起标题和提炼标签。"},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.5,
            "max_tokens": 512,
        }
        url = f"{self.config.api_base.rstrip('/')}/chat/completions"
        resp = self._client.post(url, json=payload, headers=headers)
        if resp.status_code != 200:
            raise RuntimeError(f"API 请求失败 HTTP {resp.status_code}: {resp.text[:300]}")

        choices = resp.json().get("choices", [])
        if not choices:
            raise RuntimeError("API 返回异常 (无 choices)")
        text = choices[0]["message"]["content"]

        match = re.search(r"\{.*\}", text, re.DOTALL)
        if not match:
            raise RuntimeError(f"无法解析模型输出: {text[:200]}")
        data = json.loads(match.group(0))
        return {
            "title": str(data.get("title", "")).strip(),
            "tags": str(data.get("tags", "")).strip(),
            "summary": str(data.get("summary", "")).strip(),
        }

    def _split_content(self, content: str) -> list[str]:
        if len(content) <= self.config.chunk_size:
            return [content]

        chunks = []
        current = ""
        for block in _split_into_blocks(content):
            if current and len(current) + len(block) + 2 > self.config.chunk_size:
                chunks.append(current)
                current = block
            elif current:
                current += "\n\n" + block
            else:
                current = block

        if current:
            chunks.append(current)

        return chunks

    @staticmethod
    def list_models(api_base: str, api_key: str, timeout: float = 20.0) -> list[str]:
        """Fetch available model IDs from an OpenAI-compatible /models endpoint."""
        if not api_key:
            raise ValueError("API Key 未设置")
        url = f"{api_base.rstrip('/')}/models"
        with http_client.client(timeout=timeout) as client:
            resp = client.get(url, headers={"Authorization": f"Bearer {api_key}"})
        if resp.status_code != 200:
            raise RuntimeError(f"HTTP {resp.status_code}: {resp.text[:200]}")
        data = resp.json()
        items = data.get("data") if isinstance(data, dict) else data
        if not isinstance(items, list):
            raise RuntimeError("响应格式异常")
        ids = []
        for it in items:
            if isinstance(it, dict) and it.get("id"):
                ids.append(str(it["id"]))
            elif isinstance(it, str):
                ids.append(it)
        return sorted(set(ids))

    @staticmethod
    def supported_models() -> list[dict]:
        return SUPPORTED_MODELS
