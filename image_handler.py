import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Callable

from csdn_uploader import CSDNUploader


@dataclass
class ImageUploadResult:
    original_path: str = ""
    csdn_url: str = ""
    success: bool = False
    error: str = ""
    method: str = ""


class ImageHandler:
    def __init__(self, uploader: CSDNUploader | None = None):
        self.uploader = uploader

    def set_uploader(self, uploader: CSDNUploader):
        self.uploader = uploader

    def extract_images(self, markdown: str) -> List[str]:
        return re.findall(r'!\[.*?\]\((.+?)\)', markdown)

    def upload_all(
        self, image_paths: List[str],
        progress_callback: Callable | None = None,
        use_fallback: bool = True
    ) -> List[ImageUploadResult]:
        if not self.uploader:
            raise RuntimeError("CSDNUploader 未设置")

        results = []
        total = len(image_paths)

        for i, path in enumerate(image_paths):
            result = ImageUploadResult(original_path=path)
            try:
                resolved = self._resolve_path(path)
                if not resolved:
                    result.error = f"图片文件不存在: {path}"
                else:
                    if use_fallback:
                        url = self.uploader.upload_with_fallback(str(resolved))
                        result.method = "fallback"
                    else:
                        url = self.uploader.upload_image(str(resolved))
                        result.method = "csdn"
                    result.csdn_url = url
                    result.success = True
            except Exception as e:
                result.error = str(e)

            results.append(result)

            if progress_callback:
                progress_callback(i + 1, total, path, result.success)

        return results

    def _resolve_path(self, path: str) -> Path | None:
        p = Path(path)
        if p.exists():
            return p

        candidates = [
            Path.cwd() / path,
            Path.cwd() / Path(path).name,
            Path.home() / path,
        ]
        for c in candidates:
            if c.exists():
                return c
        return None

    def replace_in_markdown(self, markdown: str, results: List[ImageUploadResult]) -> str:
        for r in results:
            if r.success:
                escaped = re.escape(r.original_path)
                markdown = re.sub(
                    rf'(!\[.*?\]\()({escaped})(\))',
                    rf'\1{r.csdn_url}\3',
                    markdown
                )
        return markdown
