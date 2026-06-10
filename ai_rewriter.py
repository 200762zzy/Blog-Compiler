import re
from dataclasses import dataclass

import httpx


SYSTEM_PROMPT = """你是一位CSDN技术博主，请将下面的笔记内容改写成CSDN博客风格：

要求：
1. 保持技术准确性，不要编造不存在的功能
2. 语气专业但不枯燥，可以加入个人经验分享
3. 为长段落添加小标题分隔，提升可读性
4. **代码块、表格保持原样，不要修改其中的内容**
5. 对于笔记中的图片 ![](path)：
   - 根据图片文件名和周围的文字内容，生成有意义的 alt 描述文本
   - **删除括号中的路径**，只保留 ![]()
   - 示例：![image-20260604.png](path) → ![终端输出截图：ls -la 命令的执行结果]
   - 如果无法推断图片内容，简单标注为 ![相关截图]
6. 输出格式为 Markdown"""


@dataclass
class RewriteConfig:
    api_key: str = ""
    api_base: str = "https://api.openai.com/v1"
    model: str = "gpt-4o-mini"
    temperature: float = 0.7
    max_tokens: int = 8192
    chunk_size: int = 3000
    system_prompt: str = SYSTEM_PROMPT


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
        results = []

        for i, chunk in enumerate(chunks):
            if self._cancelled:
                break
            result = self._call_api(chunk)
            results.append(result)

        return "\n\n".join(results)

    def _call_api(self, content: str) -> str:
        self.last_error = ""
        headers = {
            "Authorization": f"Bearer {self.config.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.config.model,
            "messages": [
                {"role": "system", "content": self.config.system_prompt},
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

        return choices[0]["message"]["content"].strip()

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
