import json
import re
from dataclasses import dataclass

import httpx

import http_client


@dataclass
class RewriteConfig:
    api_key: str = ""
    api_base: str = "https://api.openai.com/v1"
    model: str = "gpt-4o-mini"
    temperature: float = 0.7
    max_tokens: int = 32768
    chunk_size: int = 8000
    system_prompt: str = ""


CONTINUATION_PROMPT = """请继续保持与上文一致的风格和语气，直接接着改写下面的内容。
不要重复前文内容，不要加总结性语句，直接从断点处继续：

{content}"""


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
        self.config = config or RewriteConfig()
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

    def _stream_call(self, content: str, is_continuation: bool, on_chunk) -> str:
        self.last_error = ""
        headers = {
            "Authorization": f"Bearer {self.config.api_key}",
            "Content-Type": "application/json",
        }
        system_content = self.config.system_prompt
        if is_continuation:
            system_content = "你正在继续改写一篇文章，保持风格一致，直接继续。"

        payload = {
            "model": self.config.model,
            "messages": [
                {"role": "system", "content": system_content},
                {"role": "user", "content": content},
            ],
            "temperature": self.config.temperature,
            "max_tokens": self.config.max_tokens,
            "stream": True,
        }

        url = f"{self.config.api_base.rstrip('/')}/chat/completions"
        collected = []

        with self._client.stream("POST", url, json=payload, headers=headers) as resp:
            if resp.status_code != 200:
                resp.read()
                detail = f"HTTP {resp.status_code}"
                try:
                    detail += f"\n响应: {resp.json()}"
                except Exception:
                    detail += f"\n响应: {resp.text[:500]}"
                self.last_error = detail
                raise RuntimeError(f"API 请求失败\n{detail}")

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
        system_content = self.config.system_prompt
        if is_continuation:
            system_content = "你正在继续改写一篇文章，保持风格一致，直接继续。"

        payload = {
            "model": self.config.model,
            "messages": [
                {"role": "system", "content": system_content},
                {"role": "user", "content": content},
            ],
            "temperature": self.config.temperature,
            "max_tokens": self.config.max_tokens,
        }

        resp = self._client.post(
            f"{self.config.api_base.rstrip('/')}/chat/completions",
            json=payload,
            headers=headers,
        )

        if resp.status_code != 200:
            detail = f"HTTP {resp.status_code}"
            try:
                detail += f"\n响应: {resp.json()}"
            except Exception:
                detail += f"\n响应: {resp.text[:500]}"
            self.last_error = detail
            raise RuntimeError(f"API 请求失败\n{detail}")

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
    def supported_models() -> list[dict]:
        return [
            {"label": "GPT-4o-mini", "value": "gpt-4o-mini", "base": "https://api.openai.com/v1"},
            {"label": "GPT-4o", "value": "gpt-4o", "base": "https://api.openai.com/v1"},
            {"label": "DeepSeek-V3", "value": "deepseek-chat", "base": "https://api.deepseek.com/v1"},
            {"label": "DeepSeek-R1", "value": "deepseek-reasoner", "base": "https://api.deepseek.com/v1"},
            {"label": "DeepSeek-V4-Flash", "value": "deepseek-v4-flash", "base": "https://api.deepseek.com/v1"},
            {"label": "Moonshot-v1", "value": "moonshot-v1-8k", "base": "https://api.moonshot.cn/v1"},
            {"label": "Qwen-Max", "value": "qwen-max", "base": "https://dashscope.aliyuncs.com/compatible-mode/v1"},
            {"label": "GLM-4", "value": "glm-4", "base": "https://open.bigmodel.cn/api/paas/v4"},
            {"label": "自定义 (可编辑)", "value": "custom", "base": ""},
        ]
