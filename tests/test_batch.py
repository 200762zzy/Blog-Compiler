"""批量处理：一次改写文件列表里的所有笔记。

重点是「单篇失败不能拖垮整批」，以及「每篇按自己的目录解析相对路径图片」——
批量场景下不能共用一个基准目录。
"""

from pathlib import Path

import pytest

from PySide6.QtWidgets import QApplication

import app as app_module


class StubRewriter:
    """假的重写器：按内容前缀返回可预期的结果，可以指定某篇失败。"""

    def __init__(self, fail_on=(), empty_on=()):
        self.fail_on = set(fail_on)
        self.empty_on = set(empty_on)
        self.seen_prompts = []
        self.seen_contents = []
        self.cancelled = False

        class _Config:
            def __init__(self):
                self.system_prompt = ""
                self.api_key = "test"

        self.config = _Config()

    def rewrite(self, content: str) -> str:
        self.seen_contents.append(content)
        self.seen_prompts.append(self.config.system_prompt)
        if any(marker in content for marker in self.fail_on):
            raise RuntimeError("模拟接口失败")
        if any(marker in content for marker in self.empty_on):
            return "   "
        return f"改写结果（{len(content)} 字）\n\n{content[:20]}"

    def cancel(self):
        self.cancelled = True


def _run_worker(worker):
    """同步跑完 worker（在测试里直接调 run，省掉事件循环等待）。"""
    results = []
    worker.file_done.connect(lambda p, ok, d: results.append((Path(p).name, ok, d)))
    worker.run()
    return results


class TestBatchWorker:
    def test_writes_sibling_output_files(self, work_dir):
        files = []
        for name in ("a.md", "b.md"):
            f = work_dir / name
            f.write_text(f"# {name}\n\n正文内容足够长一些", encoding="utf-8")
            files.append(str(f))

        worker = app_module.BatchWorker(StubRewriter(), files, "提示词")
        results = _run_worker(worker)

        assert [ok for _, ok, _ in results] == [True, True]
        for name in ("a.rewritten.md", "b.rewritten.md"):
            out = work_dir / name
            assert out.exists()
            assert "改写结果" in out.read_text(encoding="utf-8")

    def test_does_not_overwrite_the_original(self, work_dir):
        note = work_dir / "a.md"
        note.write_text("# 标题\n\n原文内容", encoding="utf-8")
        original = note.read_text(encoding="utf-8")

        app_module.BatchWorker(StubRewriter(), [str(note)], "提示词").run()

        assert note.read_text(encoding="utf-8") == original

    def test_one_failure_does_not_stop_the_rest(self, work_dir):
        good = work_dir / "good.md"
        bad = work_dir / "bad.md"
        also_good = work_dir / "also.md"
        good.write_text("# 好\n\n正文", encoding="utf-8")
        bad.write_text("# 坏\n\n正文 BOOM 正文", encoding="utf-8")
        also_good.write_text("# 也好\n\n正文", encoding="utf-8")

        rewriter = StubRewriter(fail_on=["BOOM"])
        worker = app_module.BatchWorker(
            rewriter, [str(good), str(bad), str(also_good)], "提示词"
        )
        results = _run_worker(worker)

        by_name = {name: ok for name, ok, _ in results}
        assert by_name["good.md"] is True
        assert by_name["bad.md"] is False
        assert by_name["also.md"] is True, "一篇失败不该中断后面的文件"
        # 失败的没产出文件
        assert not (work_dir / "bad.rewritten.md").exists()

    def test_empty_model_output_counts_as_failure(self, work_dir):
        note = work_dir / "a.md"
        note.write_text("# 标题\n\nEMPTY_MARK 正文", encoding="utf-8")

        results = _run_worker(
            app_module.BatchWorker(
                StubRewriter(empty_on=["EMPTY_MARK"]), [str(note)], "提示词"
            )
        )

        assert results[0][1] is False
        assert "空内容" in results[0][2]
        assert not (work_dir / "a.rewritten.md").exists()

    def test_relative_images_resolve_against_each_files_own_dir(self, work_dir):
        """两篇笔记各自的 assets 目录不同，不能用一个基准目录。"""
        paths = []
        for project in ("p1", "p2"):
            d = work_dir / project
            (d / "assets").mkdir(parents=True, exist_ok=True)
            (d / "assets" / "shot.png").write_bytes(b"png")
            note = d / "note.md"
            note.write_text("![截图](./assets/shot.png)", encoding="utf-8")
            paths.append(str(note))

        rewriter = StubRewriter()
        app_module.BatchWorker(rewriter, paths, "提示词", image_mode="keep").run()

        for content, project in zip(rewriter.seen_contents, ("p1", "p2")):
            expected = str(work_dir / project / "assets" / "shot.png")
            assert expected in content, f"{project} 的相对路径没有按自己的目录解析"

    def test_base64_mode_embeds_images(self, work_dir):
        d = work_dir / "p"
        d.mkdir(parents=True, exist_ok=True)
        (d / "shot.png").write_bytes(b"\x89PNG\r\n\x1a\nfake")
        note = d / "note.md"
        note.write_text("![截图](./shot.png)", encoding="utf-8")

        rewriter = StubRewriter()
        app_module.BatchWorker(rewriter, [str(note)], "提示词", image_mode="base64").run()

        assert "data:image/png;base64," in rewriter.seen_contents[0]

    def test_prompt_is_applied_to_every_file(self, work_dir):
        files = []
        for name in ("a.md", "b.md"):
            f = work_dir / name
            f.write_text("# 标题\n\n正文", encoding="utf-8")
            files.append(str(f))

        rewriter = StubRewriter()
        app_module.BatchWorker(rewriter, files, "我的专属提示词").run()

        assert rewriter.seen_prompts == ["我的专属提示词", "我的专属提示词"]

    def test_missing_file_is_reported_not_raised(self, work_dir):
        results = _run_worker(
            app_module.BatchWorker(StubRewriter(), [str(work_dir / "nope.md")], "提示词")
        )
        assert results[0][1] is False


class TestBatchDialog:
    @staticmethod
    def _dialog(main_window, files):
        main_window.ai_rewriter = StubRewriter()
        dlg = app_module.BatchDialog(main_window, files)
        return dlg

    def test_lists_every_file(self, main_window, work_dir):
        files = []
        for name in ("a.md", "b.md", "c.md"):
            f = work_dir / name
            f.write_text("# 标题", encoding="utf-8")
            files.append(str(f))

        dlg = self._dialog(main_window, files)
        try:
            assert dlg.file_list.count() == 3
        finally:
            dlg.close()
            dlg.deleteLater()

    def test_marks_success_status(self, main_window, work_dir):
        note = work_dir / "a.md"
        note.write_text("# 标题\n\n正文", encoding="utf-8")
        dlg = self._dialog(main_window, [str(note)])
        try:
            dlg._on_file_done(str(note), True, str(work_dir / "a.rewritten.md"))
            assert "完成" in dlg.file_list.item(0).text()
        finally:
            dlg.close()
            dlg.deleteLater()

    def test_marks_failure_status(self, main_window, work_dir):
        note = work_dir / "a.md"
        note.write_text("# 标题", encoding="utf-8")
        dlg = self._dialog(main_window, [str(note)])
        try:
            dlg._on_file_done(str(note), False, "RuntimeError: 模拟失败")
            assert "失败" in dlg.file_list.item(0).text()
            assert "模拟失败" in dlg.log_view.toPlainText()
        finally:
            dlg.close()
            dlg.deleteLater()

    def test_summary_is_logged(self, main_window, work_dir):
        note = work_dir / "a.md"
        note.write_text("# 标题", encoding="utf-8")
        dlg = self._dialog(main_window, [str(note)])
        try:
            dlg._on_all_done(3, 1)
            text = dlg.log_view.toPlainText()
            assert "成功 3 篇" in text
            assert "失败 1 篇" in text
            assert dlg.btn_start.isEnabled(), "结束后应能再跑一次"
        finally:
            dlg.close()
            dlg.deleteLater()

    def test_refuses_without_api_key(self, main_window, work_dir, monkeypatch):
        note = work_dir / "a.md"
        note.write_text("# 标题", encoding="utf-8")
        main_window.ai_rewriter = None

        warned = []
        monkeypatch.setattr(
            app_module.QMessageBox, "warning",
            staticmethod(lambda *a, **k: warned.append(a)),
        )

        dlg = app_module.BatchDialog(main_window, [str(note)])
        try:
            dlg._start()
            assert warned, "没有 API Key 时应该给出提示"
            assert dlg.worker is None, "不该启动线程"
        finally:
            dlg.close()
            dlg.deleteLater()

    def test_remembers_tone_and_image_choice(self, main_window, work_dir, monkeypatch):
        note = work_dir / "a.md"
        note.write_text("# 标题\n\n正文", encoding="utf-8")
        main_window.ai_rewriter = StubRewriter()

        dlg = app_module.BatchDialog(main_window, [str(note)])
        try:
            dlg.tone_combo.setCurrentText("教程风")
            dlg.image_combo.setCurrentIndex(2)

            started = {}

            class FakeWorker:
                def __init__(self, *a, **k):
                    started["args"] = a
                    signal = type("S", (), {"connect": lambda *x, **y: None})()
                    self.progress = self.file_done = self.all_done = signal

                def start(self):
                    started["started"] = True

                def isRunning(self):
                    return False

            monkeypatch.setattr(app_module, "BatchWorker", FakeWorker)
            dlg._start()

            assert started.get("started"), "应该启动了后台线程"
            assert main_window.settings.get("batch_tone") == "教程风"
            assert main_window.settings.get("batch_image_mode") == 2
        finally:
            dlg.close()
            dlg.deleteLater()

    def test_open_batch_dialog_requires_files(self, main_window, monkeypatch):
        main_window.file_paths = []
        shown = []
        monkeypatch.setattr(
            app_module.QMessageBox, "information",
            staticmethod(lambda *a, **k: shown.append(a)),
        )
        main_window._open_batch_dialog()
        assert shown, "没有文件时应提示先添加文件"
