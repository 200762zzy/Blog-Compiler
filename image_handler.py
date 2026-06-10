import re
from typing import List


class ImageHandler:
    @staticmethod
    def extract_images(markdown: str) -> List[str]:
        return re.findall(r'!\[.*?\]\((.+?)\)', markdown)

    @staticmethod
    def count_images(markdown: str) -> int:
        return len(re.findall(r'!\[.*?\]\(.+?\)', markdown))
