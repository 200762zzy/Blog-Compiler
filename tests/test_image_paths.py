"""图片路径解析：相对路径图片要能定位到真实文件。

Typora 默认把图片放在笔记旁边的 `./assets/` 之类目录，正文里写的是相对路径。
以前只认绝对路径和 URL，于是这些图片被静默跳过——不上传、也不提示。
"""

from pathlib import Path

import pytest

from image_handler import (
    ImageHandler,
    apply_resolved_paths,
    is_url,
    resolve_image,
    resolve_map,
)


@pytest.fixture
def note_dir(work_dir):
    """一个带相对路径图片的笔记目录。"""
    assets = work_dir / "assets"
    assets.mkdir(parents=True, exist_ok=True)
    (work_dir / "note.md").write_text("# 标题", encoding="utf-8")
    (assets / "shot.png").write_bytes(b"png")
    (work_dir / "top.png").write_bytes(b"png")
    return work_dir


class TestIsUrl:
    @pytest.mark.parametrize("target", [
        "https://x/a.png", "http://x/a.png", "data:image/png;base64,AAA",
    ])
    def test_urls(self, target):
        assert is_url(target) is True

    @pytest.mark.parametrize("target", ["./assets/a.png", "C:\\a.png", "a.png", ""])
    def test_not_urls(self, target):
        assert is_url(target) is False


class TestResolveImage:
    def test_relative_to_base_dir(self, note_dir):
        assert resolve_image("./assets/shot.png", note_dir) == note_dir / "assets" / "shot.png"

    def test_relative_without_dot_prefix(self, note_dir):
        assert resolve_image("assets/shot.png", note_dir) == note_dir / "assets" / "shot.png"

    def test_absolute_path(self, note_dir):
        absolute = note_dir / "top.png"
        assert resolve_image(str(absolute), note_dir) == absolute

    @pytest.mark.parametrize("target", [
        "https://example.com/a.png", "data:image/png;base64,AAAA",
    ])
    def test_urls_are_not_local_files(self, target, note_dir):
        assert resolve_image(target, note_dir) is None

    def test_missing_file_returns_none(self, note_dir):
        assert resolve_image("./assets/gone.png", note_dir) is None

    def test_without_base_dir_only_absolute_works(self, note_dir):
        assert resolve_image("assets/shot.png", None) is None
        assert resolve_image(str(note_dir / "top.png"), None) is not None

    def test_backslashes_are_tolerated(self, note_dir):
        """Markdown 里可能写 Windows 风格的反斜杠。"""
        assert resolve_image(".\\assets\\shot.png", note_dir) is not None

    def test_forward_slashes_are_tolerated(self, note_dir):
        assert resolve_image("assets/shot.png", note_dir) is not None

    def test_directory_is_not_a_file(self, note_dir):
        assert resolve_image("./assets", note_dir) is None

    def test_blank_target(self, note_dir):
        assert resolve_image("   ", note_dir) is None


class TestResolveMap:
    def test_maps_only_existing_files(self, note_dir):
        content = "![a](./assets/shot.png)\n\n![b](./assets/gone.png)"
        mapping = resolve_map(content, note_dir)

        assert "./assets/shot.png" in mapping
        assert "./assets/gone.png" not in mapping
        assert mapping["./assets/shot.png"] == note_dir / "assets" / "shot.png"

    def test_urls_are_skipped(self, note_dir):
        mapping = resolve_map("![a](https://x/a.png)", note_dir)
        assert mapping == {}

    def test_without_images(self, note_dir):
        assert resolve_map("没有图片的正文", note_dir) == {}


class TestApplyResolvedPaths:
    def test_relative_reference_becomes_absolute(self, note_dir):
        content = "![截图](./assets/shot.png)"
        mapping = resolve_map(content, note_dir)

        result = apply_resolved_paths(content, mapping)

        assert str(note_dir / "assets" / "shot.png") in result
        assert "./assets/shot.png" not in result

    def test_unresolved_references_are_left_alone(self, note_dir):
        content = "![a](./assets/gone.png)"
        mapping = resolve_map(content, note_dir)

        assert apply_resolved_paths(content, mapping) == content

    def test_urls_are_left_alone(self, note_dir):
        content = "![a](https://x/a.png)"
        assert apply_resolved_paths(content, resolve_map(content, note_dir)) == content

    def test_alt_text_and_title_survive(self, note_dir):
        content = '![终端截图](./assets/shot.png "标题")'
        mapping = resolve_map(content, note_dir)

        result = apply_resolved_paths(content, mapping)

        assert result.startswith("![终端截图](")
        assert str(note_dir / "assets" / "shot.png") in result

    def test_empty_mapping_is_a_noop(self):
        content = "![a](x.png)"
        assert apply_resolved_paths(content, {}) == content

    def test_mixed_content(self, note_dir):
        content = (
            "![本地](./assets/shot.png)\n\n"
            "![远程](https://x/a.png)\n\n"
            "![丢失](./assets/gone.png)"
        )
        result = apply_resolved_paths(content, resolve_map(content, note_dir))

        assert str(note_dir / "assets" / "shot.png") in result
        assert "https://x/a.png" in result
        assert "./assets/gone.png" in result


class TestParserIntegration:
    def test_parse_markdown_resolves_relative_images(self, note_dir):
        from parser import parse_markdown

        content = "![a](./assets/shot.png)\n\n正文"
        result = parse_markdown(content, base_dir=note_dir)

        assert result.images == ["./assets/shot.png"]        # 原文引用保持不变
        assert result.resolved_images["./assets/shot.png"] == note_dir / "assets" / "shot.png"

    def test_parse_markdown_without_base_dir(self, note_dir):
        from parser import parse_markdown

        result = parse_markdown("![a](./assets/shot.png)", base_dir=None)

        assert result.images == ["./assets/shot.png"]
        assert result.resolved_images == {}

    def test_parse_markdown_still_handles_absolute_paths(self, note_dir):
        from parser import parse_markdown

        absolute = note_dir / "top.png"
        result = parse_markdown(f"![a]({absolute})", base_dir=note_dir)

        assert result.resolved_images[str(absolute)] == absolute
