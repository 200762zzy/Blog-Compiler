import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

import mistune
from image_handler import ImageHandler, resolve_map


@dataclass
class ParseResult:
    images: List[str] = field(default_factory=list)
    #: {正文里的原始引用: 磁盘上的绝对路径}，用于上传/发布时定位文件
    resolved_images: dict = field(default_factory=dict)
    code_block_count: int = 0
    paragraph_count: int = 0
    table_count: int = 0
    headings: List[tuple] = field(default_factory=list)
    raw_markdown: str = ""
    is_valid: bool = True
    error: str = ""


def parse_markdown(content: str, base_dir: Optional[Path | str] = None) -> ParseResult:
    """解析 Markdown。

    base_dir 是笔记所在目录，用来解析相对路径图片（Typora 默认就写 `./img/a.png`）。
    不传则只认绝对路径和 URL。
    """
    result = ParseResult(raw_markdown=content)

    if not content.strip():
        result.is_valid = False
        result.error = "内容为空"
        return result

    try:
        _ = mistune.html(content)
    except Exception as e:
        result.is_valid = False
        result.error = f"Markdown 解析失败: {e}"
        return result

    result.images = ImageHandler.extract_images(content)
    result.resolved_images = resolve_map(content, base_dir)

    code_fences = re.findall(r'```', content)
    result.code_block_count = len(code_fences) // 2

    result.paragraph_count = len([p for p in content.split('\n\n') if p.strip()])

    stripped_content = re.sub(r'```[\s\S]*?```', '', content)
    table_lines = [l for l in stripped_content.split('\n') if l.strip().startswith('|') and l.strip().endswith('|')]
    if table_lines:
        separator_lines = [l for l in table_lines if re.match(r'^\|[\s\-:|]+\|$', l.strip())]
        has_separator = any('---' in l or ':--' in l for l in separator_lines)
        if has_separator:
            has_data = len(table_lines) > len(separator_lines)
            if has_data:
                result.table_count = (len(table_lines) - 1) // 2
            else:
                result.table_count = len(table_lines) - 1

    heading_matches = re.findall(r'^(#{1,6})\s+(.+)$', content, re.MULTILINE)
    result.headings = [(len(m[0]), m[1].strip()) for m in heading_matches]

    return result
