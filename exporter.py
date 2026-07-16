import re
from pathlib import Path
from image_handler import ImageHandler


class Exporter:
    PLATFORM_ADAPTERS = {
        "CSDN": lambda c: Exporter.adapt_csdn_format(c),
        "掘金": lambda c: Exporter._adapt_juejin(c),
        "博客园": lambda c: c,
    }

    @staticmethod
    def adapt_for(platform: str, content: str) -> str:
        adapter = Exporter.PLATFORM_ADAPTERS.get(platform)
        if adapter:
            return adapter(content)
        return content

    @staticmethod
    def _adapt_juejin(content: str) -> str:
        content = Exporter._ensure_codeblock_lang(content)
        content = Exporter._handle_image_dimensions(content)
        return content
    @staticmethod
    def to_file(content: str, filepath: str, overwrite_callback=None):
        path = Path(filepath)
        if path.exists() and overwrite_callback:
            if not overwrite_callback(str(path)):
                return None
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return str(path)

    @staticmethod
    def to_clipboard(content: str):
        try:
            from PySide6.QtWidgets import QApplication
            cb = QApplication.clipboard()
            cb.setText(content)
            return True
        except Exception:
            import pyperclip
            pyperclip.copy(content)
            return True

    @staticmethod
    def adapt_csdn_format(markdown: str) -> str:
        content = markdown

        content = Exporter._ensure_codeblock_lang(content)
        content = Exporter._fix_table_format(content)
        content = Exporter._handle_image_dimensions(content)
        content = Exporter._fix_heading_spacing(content)

        return content

    @staticmethod
    def _ensure_codeblock_lang(content: str) -> str:
        lines = content.split("\n")
        result = []
        in_code = False
        for line in lines:
            if line.startswith("```"):
                if not in_code:
                    lang = line[3:].strip()
                    if not lang:
                        line = "```text"
                    in_code = True
                else:
                    in_code = False
            result.append(line)
        return "\n".join(result)

    @staticmethod
    def _fix_table_format(content: str) -> str:
        lines = content.split("\n")
        result = []
        for line in lines:
            stripped = line.strip()
            if re.match(r'^\|.+\|$', stripped):
                parts = [p.strip() for p in stripped.split("|")]
                parts = [p for p in parts if p != ""]
                if all(re.match(r'^[\s\-:|]+$', p) for p in parts):
                    line = "| " + " | ".join(parts) + " |"
                    line = re.sub(r':-+:', r':---:', line)
                    line = re.sub(r'-+', '---', line)
                else:
                    line = "| " + " | ".join(parts) + " |"
            result.append(line)
        return "\n".join(result)

    @staticmethod
    def _handle_image_dimensions(content: str) -> str:
        def clean_dim(m):
            alt = m.group(1)
            url = m.group(2)
            url_clean = re.sub(r'\s*=\s*\d+x\s*$', '', url)
            url_clean = re.sub(r'\s*=\s*\d+%\s*$', '', url_clean)
            return f"![{alt}]({url_clean})"

        content = ImageHandler.replace_images(content, clean_dim)
        return content

    @staticmethod
    def _fix_heading_spacing(content: str) -> str:
        content = re.sub(r'^(#{1,6})([^ \t\n#])', r'\1 \2', content, flags=re.MULTILINE)
        return content

    @staticmethod
    def get_export_filename(original_path: str, suffix: str = "_csdn") -> str:
        p = Path(original_path)
        return str(p.parent / f"{p.stem}{suffix}{p.suffix}")
