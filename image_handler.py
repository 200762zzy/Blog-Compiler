"""
Image handling utilities for Blog Compiler.

This module provides the canonical regex pattern for matching Markdown images
(![alt](path)) so that parser.py and exporter.py use a single source of truth.
"""

import re
from typing import List


IMAGE_PATTERN = r'!\[(.*?)\]\((.+?)(?:\s+"[^"]*")?\)'
"""Captures alt text (group 1) and URL/path (group 2) from Markdown images, optional title attribute stripped."""


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
