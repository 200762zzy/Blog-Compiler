"""导出/复制要按平台的 Markdown 方言处理。

以前这两个动作写死了 CSDN 方言，连发布对话框里选的平台都不看：
打算发掘金时导出，图片尺寸标记（`=300x`）不会被去掉——掘金不认这个语法。
"""

import pytest

import app as app_module


class TestRememberedPlatforms:
    def test_empty_by_default(self, main_window):
        assert main_window._remembered_platforms() == []

    def test_remembers_one_platform(self, main_window):
        main_window._remember_platforms(["掘金"])
        assert main_window._remembered_platforms() == ["掘金"]

    def test_remembers_several(self, main_window):
        main_window._remember_platforms(["CSDN", "掘金"])
        assert set(main_window._remembered_platforms()) == {"CSDN", "掘金"}

    @pytest.mark.parametrize("garbage", [4, None, "掘金", {"a": 1}, [1, 2], ["不存在的平台"]])
    def test_garbage_config_is_ignored(self, main_window, garbage):
        """配置被手改坏了也不能让导出出错。"""
        main_window.settings.set("last_publish_platforms", garbage)
        assert main_window._remembered_platforms() == []

    def test_unknown_names_are_filtered_out(self, main_window):
        main_window.settings.set("last_publish_platforms", ["掘金", "知乎", 7])
        assert main_window._remembered_platforms() == ["掘金"]


class TestExportAdapter:
    def test_single_platform_uses_its_dialect(self, main_window):
        main_window._remember_platforms(["掘金"])
        content = "![a](http://x/y.png =300x)"

        result, label = main_window._prepare_for_export(content)

        assert "=300x" not in result, "掘金方言应该去掉图片尺寸标记"
        assert label == "掘金"

    def test_multiple_platforms_keep_original(self, main_window):
        """勾了多个平台时没有唯一方言，保持原文最不容易出错。"""
        main_window._remember_platforms(["CSDN", "掘金"])
        content = "![a](http://x/y.png =300x)"

        result, label = main_window._prepare_for_export(content)

        assert result == content
        assert "多个平台" in label

    def test_no_platform_keeps_original(self, main_window):
        content = "```\ncode\n```"

        result, label = main_window._prepare_for_export(content)

        assert result == content
        assert "未指定平台" in label

    def test_csdn_dialect_adds_code_language(self, main_window):
        main_window._remember_platforms(["CSDN"])
        result, _ = main_window._prepare_for_export("```\ncode\n```")
        assert "```text" in result

    def test_csdn_dialect_is_not_forced_on_other_platforms(self, main_window):
        """博客园的适配器是原样返回，不该被套上 CSDN 的改动。"""
        main_window._remember_platforms(["博客园"])
        result, label = main_window._prepare_for_export("```\ncode\n```")

        assert result == "```\ncode\n```"
        assert label == "博客园"


class TestDraftsPersist:
    """草稿以前只在内存里，关掉程序就没了。"""

    @staticmethod
    def _load_note(window, path):
        from PySide6.QtCore import Qt
        from PySide6.QtWidgets import QListWidgetItem

        item = QListWidgetItem(str(path))
        item.setData(Qt.UserRole, str(path))
        window._on_file_selected(item)
        return item

    def test_draft_survives_reload(self, main_window, work_dir):
        note = work_dir / "a.md"
        note.write_text("# 标题\n\n正文", encoding="utf-8")
        self._load_note(main_window, note)

        main_window._save_draft("第一版改写内容")
        assert len(main_window.drafts) == 1

        from PySide6.QtWidgets import QApplication

        app = QApplication.instance()
        second = app_module.MainWindow()
        try:
            self._load_note(second, note)
            assert len(second.drafts) == 1
            assert second.drafts[0]["content"] == "第一版改写内容"
        finally:
            updater = getattr(second, "_updater", None)
            if updater is not None and updater.isRunning():
                updater.wait(3000)
            second.close()
            second.deleteLater()

    def test_each_file_keeps_its_own_history(self, main_window, work_dir):
        first = work_dir / "a.md"
        second = work_dir / "b.md"
        for f in (first, second):
            f.write_text("# 标题", encoding="utf-8")

        self._load_note(main_window, first)
        main_window._save_draft("A 的内容")

        self._load_note(main_window, second)
        assert main_window.drafts == [], "另一个文件不该看到别处的草稿"
        main_window._save_draft("B 的内容")

        self._load_note(main_window, first)
        assert [d["content"] for d in main_window.drafts] == ["A 的内容"]

    def test_duplicate_content_is_not_stored_twice(self, main_window, work_dir):
        note = work_dir / "a.md"
        note.write_text("# 标题", encoding="utf-8")
        self._load_note(main_window, note)

        main_window._save_draft("同样的内容")
        main_window._save_draft("同样的内容")

        assert len(main_window.drafts) == 1

    def test_history_is_capped(self, main_window, work_dir):
        note = work_dir / "a.md"
        note.write_text("# 标题", encoding="utf-8")
        self._load_note(main_window, note)

        for i in range(app_module.DRAFT_KEEP + 5):
            main_window._save_draft(f"第 {i} 版")

        assert len(main_window.drafts) == app_module.DRAFT_KEEP
        assert main_window.drafts[-1]["content"] == f"第 {app_module.DRAFT_KEEP + 4} 版"

    def test_garbage_draft_store_does_not_crash(self, main_window, work_dir):
        note = work_dir / "a.md"
        note.write_text("# 标题", encoding="utf-8")
        main_window.settings.set("drafts", "不是字典")
        self._load_note(main_window, note)
        assert main_window.drafts == []


class TestOpenPublishResolvesRelativeImages:
    def test_relative_paths_are_absolutised_before_publishing(
        self, main_window, work_dir, monkeypatch
    ):
        """发布流程要能读到图片文件，所以进对话框前先换成绝对路径。"""
        assets = work_dir / "assets"
        assets.mkdir(parents=True, exist_ok=True)
        (assets / "shot.png").write_bytes(b"png")
        note = work_dir / "a.md"
        note.write_text("![截图](./assets/shot.png)", encoding="utf-8")

        from PySide6.QtCore import Qt
        from PySide6.QtWidgets import QListWidgetItem

        item = QListWidgetItem(str(note))
        item.setData(Qt.UserRole, str(note))
        main_window._on_file_selected(item)

        captured = {}

        class FakeDialog:
            def __init__(self, parent, content, default_title):
                captured["content"] = content

            def exec(self):
                return 0

        monkeypatch.setattr(app_module, "PublishDialog", FakeDialog)
        main_window._open_publish_dialog()

        assert str(assets / "shot.png") in captured["content"]
        assert "./assets/shot.png" not in captured["content"]
