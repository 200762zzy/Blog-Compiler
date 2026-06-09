import re
from dataclasses import dataclass, field
from typing import List

import mistune


@dataclass
class ParseResult:
    images: List[str] = field(default_factory=list)
    code_block_count: int = 0
    paragraph_count: int = 0
    table_count: int = 0
    headings: List[tuple] = field(default_factory=list)
    raw_markdown: str = ""
    is_valid: bool = True
    error: str = ""


def parse_markdown(content: str) -> ParseResult:
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

    images = re.findall(r'!\[.*?\]\((.+?)\)', content)
    result.images = images

    code_fences = re.findall(r'```', content)
    result.code_block_count = len(code_fences) // 2

    result.paragraph_count = len([p for p in content.split('\n\n') if p.strip()])

    table_lines = [l for l in content.split('\n') if l.strip().startswith('|') and l.strip().endswith('|')]
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
