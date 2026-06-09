import re
from pathlib import Path


class Exporter:
    @staticmethod
    def to_file(content: str, filepath: str):
        path = Path(filepath)
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
        def add_lang(m):
            fence = m.group(1)
            rest = m.group(2)
            if fence == "```" and not rest.startswith((" ", "\n", "")):
                return m.group(0)
            if fence == "```" and rest.strip() == "":
                return "```text\n"
            return m.group(0)

        content = re.sub(
            r'(```)[^\n]*(\n.*?)',
            add_lang,
            content,
            flags=re.DOTALL
        )
        return content

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

        content = re.sub(r'!\[(.*?)\]\((.*?)\)', clean_dim, content)
        return content

    @staticmethod
    def _fix_heading_spacing(content: str) -> str:
        content = re.sub(r'^(#{1,6})([^ \t\n#])', r'\1 \2', content, flags=re.MULTILINE)
        return content

    @staticmethod
    def get_export_filename(original_path: str, suffix: str = "_csdn") -> str:
        p = Path(original_path)
        return str(p.parent / f"{p.stem}{suffix}{p.suffix}")
