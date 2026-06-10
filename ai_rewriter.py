from dataclasses import dataclass

import httpx


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


class AIRewriter:
    def __init__(self, config: RewriteConfig | None = None):
        self.config = config or RewriteConfig()
        self.last_error = ""
        self._cancelled = False
        self._client = httpx.Client(timeout=120.0)

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

    def _split_content(self, content: str) -> list[str]:
        if len(content) <= self.config.chunk_size:
            return [content]

        chunks = []
        paragraphs = content.split("\n\n")
        current = ""

        for para in paragraphs:
            if len(current) + len(para) + 2 > self.config.chunk_size:
                if current:
                    chunks.append(current.strip())
                current = para
            else:
                if current:
                    current += "\n\n" + para
                else:
                    current = para

        if current:
            chunks.append(current.strip())

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
