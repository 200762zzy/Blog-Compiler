"""
Image handling utilities for Blog Compiler.

This module provides the canonical regex pattern for matching Markdown images
(![alt](path)) so that parser.py and exporter.py use a single source of truth.
It also owns the "turn a Markdown image reference into a real file on disk"
logic, because relative paths (Typora 的常见写法 `./img/a.png`) must be resolved
against the note's own directory rather than the process working directory.
"""

import re
from pathlib import Path
from typing import List, Optional


IMAGE_PATTERN = r'!\[(.*?)\]\((.+?)(?:\s+"[^"]*")?\)'
"""Captures alt text (group 1) and URL/path (group 2) from Markdown images, optional title attribute stripped."""


def is_url(target: str) -> bool:
    return target.startswith(("http://", "https://", "data:"))


def resolve_image(target: str, base_dir: Optional[Path | str] = None) -> Optional[Path]:
    """把一个 Markdown 里的图片引用解析成磁盘上的真实文件。

    依次尝试：
      1. 按原样（绝对路径，或相对当前工作目录的路径）
      2. 相对笔记所在目录（这是 Typora 等编辑器的默认相对基准）
      3. 把路径分隔符反过来再试一次（md 里写 / 而实际是 Windows 的 \\，反之亦然）

    返回第一个存在的文件；都不存在则返回 None。
    """
    if not target or is_url(target):
        return None

    raw = target.strip().strip('"').strip("'")
    if not raw:
        return None

    candidates = [Path(raw)]
    if base_dir:
        candidates.append(Path(base_dir) / raw)
    # 斜杠方向不一致的情况
    swapped = raw.replace("\\", "/") if "\\" in raw else raw.replace("/", "\\")
    if swapped != raw:
        candidates.append(Path(swapped))
        if base_dir:
            candidates.append(Path(base_dir) / swapped)

    for path in candidates:
        try:
            if path.exists() and path.is_file():
                return path
        except OSError:
            continue
    return None


def resolve_map(markdown: str, base_dir: Optional[Path | str] = None) -> dict:
    """{Markdown 里的原始引用: 解析后的绝对路径}，只包含确实能找到的文件。

    调用方拿它把正文里的相对路径换成绝对路径，交给上传/发布流程使用，
    这样导出的文档仍然保留用户原本写的相对路径。
    """
    mapping = {}
    for target in ImageHandler.extract_images(markdown):
        resolved = resolve_image(target, base_dir)
        if resolved is not None:
            mapping[target] = resolved
    return mapping


def apply_resolved_paths(markdown: str, mapping: dict) -> str:
    """把正文里的图片引用替换成解析后的绝对路径（只替换命中的那些）。"""
    if not mapping:
        return markdown

    def replacer(match):
        target = match.group(2)
        resolved = mapping.get(target)
        if resolved is None:
            return match.group(0)
        return f"![{match.group(1)}]({resolved})"

    return ImageHandler.replace_images(markdown, replacer)


class ImageHandler:
    @staticmethod
    def extract_images(markdown: str) -> List[str]:
        return [m.group(2) for m in re.finditer(IMAGE_PATTERN, markdown)]

    @staticmethod
    def count_images(markdown: str) -> int:
        return len(re.findall(IMAGE_PATTERN, markdown))

    @staticmethod
    def replace_images(markdown: str, replacer):
        """Replace each image match using a replacer function (match → new string)."""
        return re.sub(IMAGE_PATTERN, replacer, markdown)
