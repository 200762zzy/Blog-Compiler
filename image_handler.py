from dataclasses import dataclass, field
from typing import List


@dataclass
class ImageUploadResult:
    original_path: str = ""
    csdn_url: str = ""
    success: bool = False
    error: str = ""


class ImageHandler:
    def __init__(self):
        self.csdn_logged_in = False

    def upload_all(self, images: List[str]) -> List[ImageUploadResult]:
        results = []
        for path in images:
            result = ImageUploadResult(original_path=path)
            try:
                url = self._upload_single(path)
                if url:
                    result.csdn_url = url
                    result.success = True
                else:
                    result.error = "上传返回空 URL"
            except Exception as e:
                result.error = str(e)
            results.append(result)
        return results

    def _upload_single(self, path: str) -> str:
        raise NotImplementedError("Phase 2 实现")

    def replace_image_links(self, markdown: str, results: List[ImageUploadResult]) -> str:
        for r in results:
            if r.success:
                markdown = markdown.replace(r.original_path, r.csdn_url)
        return markdown
