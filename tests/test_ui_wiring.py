"""界面连线的回归测试。

这里测的是**信号接线**，不是方法本身。之前踩过的坑：语气下拉框用
`activated` 重载信号直连方法，信号带的是**索引**而不是文字，
导致「自定义...」永远匹配不上、窗口打不开——而单独调用那个方法是好的。
只测方法根本发现不了这类问题。
"""

import pytest

from PySide6.QtWidgets import QInputDialog

import app as app_module

pytestmark = pytest.mark.usefixtures("qapp")


class TestToneCombo:
    """语气下拉框：重复选「自定义...」必须每次都能弹出输入窗口。"""

    @staticmethod
    def _stub_dialog(monkeypatch, text="像一位耐心的师兄", ok=True):
        calls = []

        def fake(*args, **kwargs):
            calls.append(args)
            return text, ok

        monkeypatch.setattr(QInputDialog, "getMultiLineText", staticmethod(fake))
        return calls

    def _activate_custom(self, window):
        idx = window.tone_combo.findText("自定义...")
        window.tone_combo.setCurrentIndex(idx)
        window.tone_combo.activated.emit(idx)

    def test_signal_delivers_text_not_index(self, main_window, monkeypatch):
        """activated 有 int/str 两个重载；接线必须保证拿到的是文字。"""
        calls = self._stub_dialog(monkeypatch)
        self._activate_custom(main_window)
        assert len(calls) == 1, "选「自定义...」没有弹出输入窗口（信号可能传的是索引）"

    def test_repeated_selection_opens_dialog_every_time(self, main_window, monkeypatch):
        """这是用户报的问题：停在自定义项上再选一次，必须还能弹窗。"""
        calls = self._stub_dialog(monkeypatch)
        for expected in (1, 2, 3):
            self._activate_custom(main_window)
            assert len(calls) == expected

    def test_custom_text_is_saved(self, main_window, monkeypatch):
        self._stub_dialog(monkeypatch, text="  简洁的工程笔记风  ")
        self._activate_custom(main_window)

        assert main_window._custom_tone_text == "简洁的工程笔记风"
        assert main_window.settings.get("ai_tone_custom") == "简洁的工程笔记风"
        assert main_window.settings.get("ai_tone") == "自定义..."

    def test_combo_resets_so_state_is_unambiguous(self, main_window, monkeypatch):
        """处理完不能让下拉框停在「自定义...」，否则用户看不出到底选了哪个。"""
        self._stub_dialog(monkeypatch)
        self._activate_custom(main_window)
        assert main_window.tone_combo.currentText() != "自定义..."

    def test_cancel_falls_back_to_previous_tone(self, main_window, monkeypatch):
        self._stub_dialog(monkeypatch, text="", ok=False)
        previous = main_window._tone_before_custom
        self._activate_custom(main_window)

        assert main_window.settings.get("ai_tone") == previous
        assert main_window.tone_combo.currentText() == previous

    def test_choosing_a_preset_updates_the_setting(self, main_window, monkeypatch):
        self._stub_dialog(monkeypatch)
        idx = main_window.tone_combo.findText("教程风")
        main_window.tone_combo.setCurrentIndex(idx)
        main_window.tone_combo.activated.emit(idx)

        assert main_window.settings.get("ai_tone") == "教程风"
        assert main_window._tone_before_custom == "教程风"


class TestRewriteMode:
    """「调整当前结果」必须把右边现有内容送出去，而不是回到原文。"""

    @staticmethod
    def _capture(window, monkeypatch):
        captured = {}

        class FakeWorker:
            def __init__(self, rewriter, content, stream=True):
                captured["content"] = content
                captured["prompt"] = rewriter.config.system_prompt
                signal = type("S", (), {"connect": lambda *a, **k: None})()
                self.chunk = self.finished = self.error = self.cancelled = signal

            def start(self):
                pass

            def isRunning(self):
                return False

        monkeypatch.setattr(app_module, "RewriteWorker", FakeWorker)
        return captured

    @staticmethod
    def _ready(window, monkeypatch):
        from ai_rewriter import RewriteConfig

        window.ai_rewriter = app_module.AIRewriter(RewriteConfig(api_key="test"))
        window.current_content = "原文内容"
        window.original_view.setPlainText("原文内容")
        return window

    def test_refine_sends_the_current_result(self, main_window, monkeypatch):
        self._ready(main_window, monkeypatch)
        captured = self._capture(main_window, monkeypatch)
        main_window.rewritten_view.setPlainText("第一版结果")
        main_window.rb_mode_refine.setChecked(True)
        main_window.refine_input.setPlainText("第二段压短")

        main_window._ai_rewrite()

        assert captured["content"] == "第一版结果"
        assert "不要重写全文" in captured["prompt"]
        assert "第二段压短" in captured["prompt"]

    def test_rewrite_mode_sends_the_original(self, main_window, monkeypatch):
        self._ready(main_window, monkeypatch)
        captured = self._capture(main_window, monkeypatch)
        main_window.rewritten_view.setPlainText("第一版结果")
        main_window.rb_mode_rewrite.setChecked(True)

        main_window._ai_rewrite()

        assert captured["content"] == "原文内容"
        assert "不要重写全文" not in captured["prompt"]

    def test_refine_survives_a_second_round(self, main_window, monkeypatch):
        """回归：_begin_stream 会清空「改写后」，若先清后读就会丢掉自己的输入。"""
        self._ready(main_window, monkeypatch)
        captured = self._capture(main_window, monkeypatch)
        main_window.rb_mode_refine.setChecked(True)

        main_window.rewritten_view.setPlainText("第一版结果")
        main_window._ai_rewrite()
        main_window._on_rewrite_finished("第二版结果", main_window._rewrite_gen)

        main_window.refine_input.setPlainText("再加一句")
        main_window._ai_rewrite()

        assert captured["content"] == "第二版结果", "第二轮调整没有基于上一版结果"

    def test_empty_instruction_still_refines(self, main_window, monkeypatch):
        self._ready(main_window, monkeypatch)
        captured = self._capture(main_window, monkeypatch)
        main_window.rewritten_view.setPlainText("当前结果")
        main_window.rb_mode_refine.setChecked(True)
        main_window.refine_input.setPlainText("")

        main_window._ai_rewrite()

        assert captured["content"] == "当前结果"
        assert "没有提出具体意见" in captured["prompt"]

    def test_each_round_becomes_a_draft(self, main_window, monkeypatch):
        self._ready(main_window, monkeypatch)
        self._capture(main_window, monkeypatch)
        main_window.rb_mode_refine.setChecked(True)

        for i in range(3):
            main_window.rewritten_view.setPlainText(f"第{i}版")
            main_window._ai_rewrite()
            main_window._on_rewrite_finished(f"第{i + 1}版结果", main_window._rewrite_gen)

        assert len(main_window.drafts) >= 2, "每轮结果都该留下草稿"


@pytest.fixture
def laid_out(main_window, qapp):
    """让窗口真正完成布局。

    不 show + resize 的话，splitter 尺寸和滚动条 maximum 都是 0，
    和滚动/尺寸相关的断言会假失败。
    """
    main_window.resize(1280, 800)
    main_window.show()
    qapp.processEvents()
    return main_window


class TestPanelMaximize:
    """点展开按钮要把对应面板撑满，再点还原。"""

    def test_maximize_and_restore(self, laid_out):
        laid_out._set_preview_visible(True)
        laid_out._maximize_panel("rewritten")

        sizes = laid_out.compare.sizes()
        assert sizes[1] == max(sizes), f"改写后没有占满: {sizes}"
        assert sizes[0] == 0 and sizes[2] == 0

        laid_out._restore_panels()
        sizes = laid_out.compare.sizes()
        assert all(s > 0 for s in sizes), f"还原后仍有面板是 0 宽: {sizes}"

    def test_toggle_returns_to_restored(self, laid_out):
        laid_out._set_preview_visible(True)
        laid_out._toggle_panel_max("original")
        assert laid_out._maximized_panel == "original"
        laid_out._toggle_panel_max("original")
        assert laid_out._maximized_panel is None


class TestBadConfigDoesNotCrashStartup:
    """回归：早期版本把下拉框索引（整数）写进了 ai_tone，导致启动即崩。

    崩溃点在 `_restore_ai_settings` → `findText(4)`：
    QComboBox.findText 只接受字符串，收到 int 直接抛 TypeError。
    这类脏数据必须容错，否则用户升级后连程序都打不开。
    """

    @staticmethod
    def _write_bad_config(config_dir, tone):
        import json

        config_dir.mkdir(parents=True, exist_ok=True)
        (config_dir / "config.json").write_text(
            json.dumps({"ai_tone": tone, "ai_tone_custom": ""}), encoding="utf-8"
        )

    @pytest.mark.parametrize("bad_tone", [4, 0, None, [], {"a": 1}, "不存在的语气"])
    def test_startup_survives(self, qapp, isolated_settings, bad_tone):
        import app as app_module

        self._write_bad_config(isolated_settings, bad_tone)

        window = app_module.MainWindow()
        try:
            assert window.tone_combo.currentText() in app_module.MainWindow.TONE_PRESETS
        finally:
            updater = getattr(window, "_updater", None)
            if updater is not None and updater.isRunning():
                updater.wait(3000)
            window.close()
            window.deleteLater()

    def test_bad_value_is_rewritten_on_disk(self, qapp, isolated_settings):
        """修正结果要落盘，不能每次启动都重新纠一遍。"""
        import json

        import app as app_module

        self._write_bad_config(isolated_settings, 4)
        window = app_module.MainWindow()
        try:
            saved = json.loads((isolated_settings / "config.json").read_text(encoding="utf-8"))
            assert saved["ai_tone"] == "技术博主风"
        finally:
            window.close()
            window.deleteLater()

    def test_valid_custom_tone_is_kept(self, qapp, isolated_settings):
        """自定义语气文本还在时，不该被当成脏数据清掉。"""
        import json

        import app as app_module

        self._write_bad_config(isolated_settings, "自定义...")
        config = json.loads((isolated_settings / "config.json").read_text(encoding="utf-8"))
        config["ai_tone_custom"] = "像一位耐心的师兄"
        (isolated_settings / "config.json").write_text(
            json.dumps(config, ensure_ascii=False), encoding="utf-8"
        )

        window = app_module.MainWindow()
        try:
            assert window.settings.get("ai_tone") == "自定义..."
            assert window._custom_tone_text == "像一位耐心的师兄"
        finally:
            window.close()
            window.deleteLater()


class TestModelHint:
    """「使用模型」标签以前从没被赋值，一直是空白。"""

    def test_shows_a_warning_without_api_key(self, main_window):
        main_window.ai_rewriter = None
        main_window._update_model_hint()
        assert "API Key" in main_window.model_hint.text()

    def test_shows_model_and_endpoint(self, main_window):
        from ai_rewriter import RewriteConfig

        main_window.ai_rewriter = app_module.AIRewriter(
            RewriteConfig(api_key="k", model="my-model", api_base="https://api.example.com/v1")
        )
        main_window._update_model_hint()

        text = main_window.model_hint.text()
        assert "my-model" in text
        assert "api.example.com" in text


class TestScrollSync:
    def test_proportional_sync_between_panes(self, laid_out, qapp):
        laid_out._set_preview_visible(True)
        laid_out.original_view.setPlainText("\n".join(f"行{i}" for i in range(200)))
        laid_out.rewritten_view.setPlainText("\n".join(f"行{i}" for i in range(300)))
        qapp.processEvents()
        laid_out._scroll_sync_enabled = True

        src = laid_out.original_view.verticalScrollBar()
        dst = laid_out.rewritten_view.verticalScrollBar()
        assert src.maximum() > 0 and dst.maximum() > 0, "测试前提不成立：滚动条没有范围"

        src.setValue(src.maximum() // 2)
        qapp.processEvents()

        assert dst.value() > 0, "另一半没有跟随滚动"

    def test_disabled_sync_does_not_move_the_other_pane(self, laid_out, qapp):
        laid_out._set_preview_visible(True)
        laid_out.original_view.setPlainText("\n".join(f"行{i}" for i in range(200)))
        laid_out.rewritten_view.setPlainText("\n".join(f"行{i}" for i in range(200)))
        qapp.processEvents()
        laid_out._scroll_sync_enabled = False

        ob = laid_out.original_view.verticalScrollBar()
        dst = laid_out.rewritten_view.verticalScrollBar()
        ob.setValue(ob.maximum() // 3)
        qapp.processEvents()
        pinned = dst.value()

        ob.setValue(0)
        qapp.processEvents()

        assert dst.value() == pinned, "关闭同步后另一边仍被带动"
