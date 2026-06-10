from pathlib import Path

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QAction, QDragEnterEvent, QDropEvent, QFont
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout,
    QSplitter, QListWidget, QListWidgetItem, QAbstractItemView,
    QTabWidget, QTextEdit, QTextBrowser, QToolBar, QStatusBar,
    QLabel, QPushButton, QFileDialog, QMessageBox, QProgressBar,
    QDialog, QLineEdit, QComboBox, QFormLayout, QDialogButtonBox,
    QGroupBox, QSpinBox, QDoubleSpinBox, QHBoxLayout,
)

import mistune

from parser import parse_markdown
from settings import Settings
from ai_rewriter import AIRewriter, RewriteConfig
from exporter import Exporter
from image_uploader import upload_images
from csdn_publisher import publish as csdn_publish
from login_window import CsdnLoginWindow


class RewriteWorker(QThread):
    finished = Signal(str)
    error = Signal(str)
    cancelled = Signal()

    def __init__(self, rewriter, content):
        super().__init__()
        self.rewriter = rewriter
        self.content = content

    def cancel(self):
        self.rewriter.cancel()
        self.requestInterruption()

    def run(self):
        try:
            result = self.rewriter.rewrite(self.content)
            if self.isInterruptionRequested():
                self.cancelled.emit()
            else:
                self.finished.emit(result)
        except Exception as e:
            if self.isInterruptionRequested():
                self.cancelled.emit()
            else:
                self.error.emit(str(e))


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.settings = Settings()
        self.file_paths = []
        self.current_content = ""
        self.rewritten_content = ""
        self.current_result = None
        self._setup_ui()
        self._restore_ai_settings()
        self.csdn_cookies = None
        self._restore_csdn_settings()
        self._update_csdn_status()

    def _setup_ui(self):
        self.setWindowTitle("Blog Compiler")
        self.resize(1300, 850)

        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        self._build_toolbar()

        splitter = QSplitter(Qt.Horizontal)

        self.file_list = QListWidget()
        self.file_list.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.file_list.setMinimumWidth(200)
        self.file_list.setMaximumWidth(350)
        self.file_list.itemClicked.connect(self._on_file_selected)

        self.content_tabs = QTabWidget()
        self.original_view = QTextEdit()
        self.original_view.setReadOnly(True)
        self.original_view.setFont(QFont("Consolas", 10))

        preview_tab = QWidget()
        preview_layout = QVBoxLayout(preview_tab)

        self.preview_stats = QLabel("选择文件后自动生成预览")
        self.preview_stats.setWordWrap(True)
        preview_layout.addWidget(self.preview_stats)

        self.preview_render = QTextBrowser()
        self.preview_render.setOpenExternalLinks(False)
        preview_layout.addWidget(self.preview_render, 1)

        self.rewritten_view = QTextEdit()
        self.rewritten_view.setFont(QFont("Consolas", 10))

        self.content_tabs.addTab(self.original_view, "原文")
        self.content_tabs.addTab(preview_tab, "预览")
        self.content_tabs.addTab(self.rewritten_view, "改写后")
        self.content_tabs.setTabEnabled(2, False)

        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(4, 4, 4, 4)

        op_label = QLabel("操作面板")
        op_font = QFont()
        op_font.setBold(True)
        op_label.setFont(op_font)
        right_layout.addWidget(op_label)

        self.btn_ai = QPushButton("AI 改写")
        self.btn_ai.clicked.connect(self._ai_rewrite)
        self.btn_ai.setEnabled(False)
        right_layout.addWidget(self.btn_ai)

        self.btn_export = QPushButton("导出文件")
        self.btn_export.clicked.connect(self._export_file)
        self.btn_export.setEnabled(False)
        right_layout.addWidget(self.btn_export)

        self.btn_copy = QPushButton("复制到剪贴板")
        self.btn_copy.clicked.connect(self._export_clipboard)
        self.btn_copy.setEnabled(False)
        right_layout.addWidget(self.btn_copy)

        right_layout.addSpacing(8)
        img_label = QLabel("图片处理方式")
        img_label.setFont(op_font)
        right_layout.addWidget(img_label)

        from PySide6.QtWidgets import QButtonGroup, QRadioButton
        self.img_mode_group = QButtonGroup(self)
        self.rb_img_alt = QRadioButton("生成alt文本(删除路径)")
        self.rb_img_upload = QRadioButton("上传scdn.io图床并替换")
        self.rb_img_keep = QRadioButton("保留原路径")
        self.rb_img_alt.setChecked(True)
        self.img_mode_group.addButton(self.rb_img_alt, 1)
        self.img_mode_group.addButton(self.rb_img_upload, 2)
        self.img_mode_group.addButton(self.rb_img_keep, 3)
        right_layout.addWidget(self.rb_img_alt)
        right_layout.addWidget(self.rb_img_upload)
        right_layout.addWidget(self.rb_img_keep)

        right_layout.addSpacing(8)
        csdn_label = QLabel("CSDN 发布")
        csdn_label.setFont(op_font)
        right_layout.addWidget(csdn_label)

        self.csdn_status = QLabel("未登录")
        right_layout.addWidget(self.csdn_status)

        self.btn_csdn_login = QPushButton("登录 CSDN")
        self.btn_csdn_login.clicked.connect(self._login_csdn)
        right_layout.addWidget(self.btn_csdn_login)

        self.btn_publish = QPushButton("发布到 CSDN")
        self.btn_publish.clicked.connect(self._publish_to_csdn)
        self.btn_publish.setEnabled(False)
        right_layout.addWidget(self.btn_publish)

        right_layout.addSpacing(8)
        log_label = QLabel("运行日志")
        log_label.setFont(op_font)
        right_layout.addWidget(log_label)

        self.log_view = QTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setFont(QFont("Consolas", 9))
        self.log_view.setMaximumHeight(250)
        right_layout.addWidget(self.log_view)

        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        right_layout.addWidget(self.progress_bar)

        splitter.addWidget(self.file_list)
        splitter.addWidget(self.content_tabs)
        splitter.addWidget(right_panel)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 4)
        splitter.setStretchFactor(2, 1)

        main_layout.addWidget(splitter)

        self.status_bar = QStatusBar()
        self.status_label = QLabel("就绪")
        self.file_count_label = QLabel("文件: 0")
        self.image_count_label = QLabel("图片: 0")
        self.status_bar.addWidget(self.status_label, 1)
        self.status_bar.addPermanentWidget(self.file_count_label)
        self.status_bar.addPermanentWidget(self.image_count_label)
        self.setStatusBar(self.status_bar)

        self.setAcceptDrops(True)

    def _build_toolbar(self):
        toolbar = QToolBar("主工具栏")
        toolbar.setMovable(False)
        self.addToolBar(toolbar)

        self.action_add = QAction("+ 添加文件", self)
        self.action_add.triggered.connect(self._add_files)
        toolbar.addAction(self.action_add)

        self.action_clear = QAction("清空列表", self)
        self.action_clear.triggered.connect(self._clear_files)
        toolbar.addAction(self.action_clear)

        toolbar.addSeparator()

        self.action_dark = QAction("暗色模式", self)
        self.action_dark.setCheckable(True)
        self.action_dark.triggered.connect(self._toggle_dark)
        toolbar.addAction(self.action_dark)

        toolbar.addSeparator()

        self.action_settings = QAction("⚙ 设置", self)
        self.action_settings.triggered.connect(self._show_settings)
        toolbar.addAction(self.action_settings)

    def _add_files(self):
        files, _ = QFileDialog.getOpenFileNames(
            self, "选择 Markdown 文件", "", "Markdown (*.md *.markdown);;所有文件 (*)"
        )
        for f in files:
            self._add_file(f)

    def _add_file(self, filepath):
        if filepath in self.file_paths:
            return
        self.file_paths.append(filepath)
        name = Path(filepath).name
        item = QListWidgetItem(name)
        item.setData(Qt.UserRole, filepath)
        self.file_list.addItem(item)
        self._update_status()
        self.log(f"已添加: {name}")

    def _clear_files(self):
        self.file_paths.clear()
        self.file_list.clear()
        self.original_view.clear()
        self.rewritten_view.clear()
        self.current_content = ""
        self.current_result = None
        self.rewritten_content = ""
        self.content_tabs.setTabEnabled(2, False)
        self._update_status()
        self.log("已清空文件列表")

    def _on_file_selected(self, item):
        filepath = item.data(Qt.UserRole)
        try:
            content = Path(filepath).read_text(encoding="utf-8")
        except UnicodeDecodeError:
            try:
                import locale
                enc = locale.getpreferredencoding()
                content = Path(filepath).read_text(encoding=enc)
            except Exception:
                content = Path(filepath).read_text(encoding="gbk")
        except Exception as e:
            QMessageBox.warning(self, "读取失败", f"无法读取文件:\n{e}")
            return

        self.current_content = content
        self.original_view.setText(content)
        result = parse_markdown(content)
        self.current_result = result

        if not result.is_valid:
            self.log(f"⚠️ 解析警告: {result.error}")
        else:
            self.log(
                f"📄 {Path(filepath).name} — "
                f"段落: {result.paragraph_count} | "
                f"代码块: {result.code_block_count} | "
                f"图片: {len(result.images)} | "
                f"表格: {result.table_count}"
            )
            self.image_count_label.setText(f"图片: {len(result.images)}")
            self.content_tabs.setTabText(0, f"原文 ({Path(filepath).name})")
            self.btn_ai.setEnabled(self.ai_rewriter is not None)
            self.content_tabs.setTabEnabled(2, False)
            self.rewritten_content = ""
            self.btn_export.setEnabled(False)
            self.btn_copy.setEnabled(False)

            heading_lines = "\n".join(
                f"  {'  ' * (lvl-1)}H{lvl} {h}"
                for lvl, h in result.headings[:20]
            )
            img_names = "\n".join(
                f"  📷 {Path(p).name}" for p in result.images[:10]
            )
            if len(result.images) > 10:
                img_names += f"\n  ...及其他 {len(result.images) - 10} 张"
            self.preview_stats.setText(
                f"📊 段落: {result.paragraph_count}  "
                f"代码块: {result.code_block_count}  "
                f"图片: {len(result.images)}  "
                f"表格: {result.table_count}\n\n"
                f"标题结构:\n{heading_lines if heading_lines else '  (无标题)'}"
                f"\n\n图片列表:\n{img_names if img_names else '  (无)'}"
            )
            self.preview_render.setHtml(mistune.html(content))

    def _toggle_dark(self, checked):
        if checked:
            self._apply_dark_theme()
            self.settings.set("dark_mode", True)
            self.log("🌙 已切换暗色模式")
        else:
            self._apply_light_theme()
            self.settings.set("dark_mode", False)
            self.log("☀️ 已切换亮色模式")

    def _apply_dark_theme(self):
        self.setStyleSheet("""
            QMainWindow, QWidget {
                background-color: #1e1e1e;
                color: #d4d4d4;
            }
            QTextEdit {
                background-color: #252526;
                color: #d4d4d4;
                border: 1px solid #3c3c3c;
            }
            QListWidget {
                background-color: #252526;
                color: #d4d4d4;
                border: 1px solid #3c3c3c;
            }
            QListWidget::item:selected {
                background-color: #094771;
            }
            QToolBar {
                background-color: #333333;
                border: none;
                spacing: 4px;
            }
            QPushButton {
                background-color: #0e639c;
                color: white;
                border: none;
                padding: 6px 12px;
                border-radius: 3px;
            }
            QPushButton:hover {
                background-color: #1177bb;
            }
            QPushButton:disabled {
                background-color: #555555;
                color: #888888;
            }
            QStatusBar {
                background-color: #007acc;
                color: white;
            }
            QTabWidget::pane {
                background-color: #252526;
                border: 1px solid #3c3c3c;
            }
            QTabBar::tab {
                background-color: #2d2d2d;
                color: #888888;
                padding: 6px 16px;
            }
            QTabBar::tab:selected {
                background-color: #252526;
                color: #d4d4d4;
            }
            QProgressBar {
                background-color: #333333;
                border: 1px solid #555555;
                border-radius: 3px;
                text-align: center;
                color: white;
            }
            QProgressBar::chunk {
                background-color: #0e639c;
            }
        """)

    def _apply_light_theme(self):
        self.setStyleSheet("")

    def _apply_settings(self):
        if self.settings.get("dark_mode", False):
            self.action_dark.setChecked(True)
            self._apply_dark_theme()

    def _update_status(self):
        count = len(self.file_paths)
        self.file_count_label.setText(f"文件: {count}")

    def log(self, message: str):
        from datetime import datetime
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_view.append(f"[{timestamp}] {message}")

    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent):
        for url in event.mimeData().urls():
            path = url.toLocalFile()
            if path.lower().endswith(('.md', '.markdown')):
                self._add_file(path)

    def _restore_ai_settings(self):
        api_key = self.settings.get_encrypted("ai_api_key")
        api_base = self.settings.get("ai_api_base", "https://api.openai.com/v1")
        model = self.settings.get("ai_model", "gpt-4o-mini")
        temperature = self.settings.get("ai_temperature", 0.7)
        max_tokens = self.settings.get("ai_max_tokens", 8192)
        if api_key:
            config = RewriteConfig(
                api_key=api_key, api_base=api_base, model=model,
                temperature=temperature, max_tokens=max_tokens,
            )
            self.ai_rewriter = AIRewriter(config)
            if self.current_content:
                self.btn_ai.setEnabled(True)
            self.log("🤖 AI 配置已加载")
        else:
            self.ai_rewriter = None

    def _show_settings(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("Blog Compiler 设置")
        dialog.resize(500, 400)

        layout = QVBoxLayout(dialog)

        ai_group = QGroupBox("AI 改写设置")
        ai_layout = QFormLayout(ai_group)

        self.settings_api_key = QLineEdit()
        self.settings_api_key.setEchoMode(QLineEdit.Password)
        saved_key = self.settings.get_encrypted("ai_api_key") or ""
        self.settings_api_key.setText(saved_key)
        ai_layout.addRow("API Key:", self.settings_api_key)

        self.settings_model = QComboBox()
        self.settings_model.setEditable(True)
        self.settings_model.lineEdit().setPlaceholderText("选择或输入模型名")
        models = AIRewriter.supported_models()
        saved_model = self.settings.get("ai_model", "gpt-4o-mini")
        found = False
        for m in models:
            self.settings_model.addItem(m["label"], m)
            if m["value"] == saved_model:
                self.settings_model.setCurrentIndex(self.settings_model.count() - 1)
                found = True
        if not found:
            self.settings_model.setEditText(saved_model)
        ai_layout.addRow("模型:", self.settings_model)

        self.settings_api_base = QLineEdit()
        self.settings_api_base.setPlaceholderText("https://api.openai.com/v1")
        saved_base = self.settings.get("ai_api_base", "https://api.openai.com/v1")
        self.settings_api_base.setText(saved_base)
        ai_layout.addRow("API 地址:", self.settings_api_base)

        temp_row = QHBoxLayout()
        self.settings_temperature = QDoubleSpinBox()
        self.settings_temperature.setRange(0.0, 2.0)
        self.settings_temperature.setSingleStep(0.1)
        self.settings_temperature.setValue(self.settings.get("ai_temperature", 0.7))
        temp_row.addWidget(self.settings_temperature)
        temp_row.addWidget(QLabel("(0~2, 越高越有创造性)"))
        ai_layout.addRow("Temperature:", temp_row)

        token_row = QHBoxLayout()
        self.settings_max_tokens = QSpinBox()
        self.settings_max_tokens.setRange(256, 65536)
        self.settings_max_tokens.setSingleStep(256)
        self.settings_max_tokens.setValue(self.settings.get("ai_max_tokens", 8192))
        token_row.addWidget(self.settings_max_tokens)
        token_row.addWidget(QLabel("(单次最大输出 token)"))
        ai_layout.addRow("Max Tokens:", token_row)

        self.settings_model.currentIndexChanged.connect(self._on_model_changed)
        layout.addWidget(ai_group)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(lambda: self._save_settings(dialog))
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)

        dialog.exec()

    def _on_model_changed(self, index):
        data = self.settings_model.currentData()
        if data and data.get("base"):
            self.settings_api_base.setText(data["base"])

    def _save_settings(self, dialog):
        api_key = self.settings_api_key.text().strip()
        model_text = self.settings_model.currentText().strip()
        model_data = self.settings_model.currentData()

        if model_data and model_data.get("value") != "custom":
            model = model_data["value"]
            api_base = self.settings_api_base.text().strip() or model_data["base"]
        else:
            model = model_text if model_text and model_text != "自定义 (可编辑)" else "gpt-4o-mini"
            api_base = self.settings_api_base.text().strip() or "https://api.deepseek.com/v1"

        if api_key:
            self.settings.set_encrypted("ai_api_key", api_key)
        self.settings.set("ai_model", model)
        self.settings.set("ai_api_base", api_base)

        temperature = self.settings_temperature.value()
        max_tokens = self.settings_max_tokens.value()
        self.settings.set("ai_temperature", temperature)
        self.settings.set("ai_max_tokens", max_tokens)

        config = RewriteConfig(
            api_key=api_key, api_base=api_base, model=model,
            temperature=temperature, max_tokens=max_tokens,
        )
        self.ai_rewriter = AIRewriter(config)
        if self.current_content:
            self.btn_ai.setEnabled(True)

        self.log("✅ AI 设置已保存")
        dialog.accept()

    def _ai_rewrite(self):
        if self._is_rewriting():
            self._cancel_rewrite()
            return

        if not self.current_content:
            QMessageBox.information(self, "提示", "请先选择一个文件")
            return

        if not self.ai_rewriter or not self.ai_rewriter.config.api_key:
            QMessageBox.warning(self, "提示", "请先在设置中配置 API Key")
            self._show_settings()
            return

        mode = self._get_image_mode()
        rewrite_content = self.current_content

        if mode == "upload" and self.current_result:
            self.log("🖼️ 开始上传图片到 scdn.io...")
            self.status_label.setText("正在上传图片...")
            QApplication.processEvents()
            try:
                local_images = [p for p in self.current_result.images if Path(p).exists()]
                if local_images:
                    mapping = upload_images(local_images)
                    for local_path, remote_url in mapping.items():
                        rewrite_content = rewrite_content.replace(
                            f"({local_path})", f"({remote_url})"
                        )
                        self.log(f"  ✅ {Path(local_path).name} → {remote_url}")
                    self.log(f"🖼️ 图片上传完成 ({len(mapping)} 张)")
                else:
                    self.log("🖼️ 无本地图片需上传，跳过")
            except Exception as e:
                QMessageBox.warning(self, "图片上传失败", str(e))
                self.log(f"❌ 图片上传失败: {e}")
                return

        system_prompt = self._build_system_prompt(mode)
        self.ai_rewriter.config.system_prompt = system_prompt

        self.log("🤖 开始 AI 改写...")
        self.status_label.setText("AI 改写中...")
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 0)
        self.btn_ai.setText("取消改写")
        self.btn_ai.setEnabled(True)
        self.btn_export.setEnabled(False)
        self.btn_copy.setEnabled(False)

        self.rewrite_worker = RewriteWorker(self.ai_rewriter, rewrite_content)
        self.rewrite_worker.finished.connect(self._on_rewrite_finished)
        self.rewrite_worker.error.connect(self._on_rewrite_error)
        self.rewrite_worker.cancelled.connect(self._on_rewrite_cancelled)
        self.rewrite_worker.start()

    def _is_rewriting(self):
        return hasattr(self, "rewrite_worker") and self.rewrite_worker.isRunning()

    def _cancel_rewrite(self):
        self.rewrite_worker.cancel()
        self.rewrite_worker.wait(5000)
        self.log("⏹️ AI 改写已取消")

    def _on_rewrite_finished(self, result):
        self.rewritten_content = result
        self.rewritten_view.setText(result)
        self.content_tabs.setTabEnabled(2, True)
        self.content_tabs.setCurrentIndex(2)

        self._reset_rewrite_ui()
        self.btn_export.setEnabled(True)
        self.btn_copy.setEnabled(True)
        self.btn_publish.setEnabled(True)

        self.log("✅ AI 改写完成")

    def _on_rewrite_error(self, error_msg):
        self._reset_rewrite_ui()

        QMessageBox.critical(self, "AI 改写失败", f"改写出错:\n{error_msg}")
        self.log(f"❌ AI 改写失败: {error_msg}")

    def _on_rewrite_cancelled(self):
        self._reset_rewrite_ui()
        self.log("⏹️ AI 改写已取消")

    def _reset_rewrite_ui(self):
        self.progress_bar.setVisible(False)
        self.progress_bar.setRange(0, 100)
        self.status_label.setText("就绪")
        self.btn_ai.setText("AI 改写")

    def _export_file(self):
        content = self.rewritten_content or self.current_content
        if not content:
            QMessageBox.information(self, "提示", "没有可导出的内容")
            return

        if not self.file_paths or self.file_list.currentRow() < 0:
            default_name = "output.md"
        else:
            default_name = Exporter.get_export_filename(
                self.file_paths[self.file_list.currentRow()]
            )

        filepath, _ = QFileDialog.getSaveFileName(
            self, "导出文件", default_name,
            "Markdown (*.md);;所有文件 (*)"
        )
        if not filepath:
            return

        content = Exporter.adapt_csdn_format(content)
        def ask_overwrite(path):
            reply = QMessageBox.question(
                self, "文件已存在",
                f"{path}\n\n文件已存在，是否覆盖？",
                QMessageBox.Yes | QMessageBox.No
            )
            return reply == QMessageBox.Yes
        result = Exporter.to_file(content, filepath, overwrite_callback=ask_overwrite)
        if result is None:
            return
        self.log(f"📝 已导出到: {filepath}")
        QMessageBox.information(self, "导出成功", f"文件已保存到:\n{filepath}")

    def _export_clipboard(self):
        content = self.rewritten_content or self.current_content
        if not content:
            QMessageBox.information(self, "提示", "没有可导出的内容")
            return

        content = Exporter.adapt_csdn_format(content)
        Exporter.to_clipboard(content)
        self.log("📋 已复制到剪贴板")
        QMessageBox.information(self, "复制成功", "内容已复制到剪贴板，可直接粘贴到 CSDN 编辑器")

    def _get_image_mode(self) -> str:
        checked = self.img_mode_group.checkedId()
        return {1: "alt", 2: "upload", 3: "keep"}.get(checked, "alt")

    def _build_system_prompt(self, mode: str) -> str:
        base = "你是一位CSDN技术博主，请将下面的笔记内容改写成CSDN博客风格：\n\n要求：\n1. 保持技术准确性，不要编造不存在的功能\n2. 语气专业但不枯燥，可以加入个人经验分享\n3. 为长段落添加小标题分隔，提升可读性\n4. **代码块、表格保持原样，不要修改其中的内容**\n5. 输出格式为 Markdown"

        img_rules = {
            "alt": (
                "\n\n图片处理：\n"
                "- 对于笔记中的图片 ![](path)：\n"
                "  - 根据图片文件名和周围的文字内容，生成有意义的 alt 描述文本\n"
                "  - **删除括号中的路径**，只保留 ![]()\n"
                "  - 示例：![image-20260604.png](path) → ![终端输出截图：ls -la 命令的执行结果]\n"
                "  - 如果无法推断图片内容，简单标注为 ![相关截图]"
            ),
            "upload": (
                "\n\n图片处理：\n"
                "- 对于笔记中的图片 ![](url)：\n"
                "  - **保留 URL 不变**，不要删除或修改括号中的地址\n"
                "  - 根据上下文优化 alt 描述文本（方括号中的内容）\n"
                "  - 如果 alt 文本已有意义内容则保留，否则补充描述"
            ),
            "keep": (
                "\n\n图片处理：\n"
                "- **不要修改任何图片标记**，保持 ![](path) 原样不变"
            ),
        }
        return base + img_rules.get(mode, img_rules["alt"])

    def _restore_csdn_settings(self):
        raw = self.settings.get("csdn_cookies")
        if raw:
            try:
                import json
                self.csdn_cookies = json.loads(raw)
                self.log("🔑 CSDN Cookie 已加载")
            except Exception:
                self.csdn_cookies = None

    def _update_csdn_status(self):
        if self.csdn_cookies:
            self.csdn_status.setText("✅ 已登录")
            self.btn_csdn_login.setText("切换账号")
        else:
            self.csdn_status.setText("❌ 未登录")
            self.btn_csdn_login.setText("登录 CSDN")

    def _login_csdn(self):
        login_dlg = CsdnLoginWindow(self)
        login_dlg.login_successful.connect(self._on_csdn_login)
        login_dlg.exec()

    def _on_csdn_login(self, cookies):
        self.csdn_cookies = cookies
        import json
        self.settings.set("csdn_cookies", json.dumps(cookies))
        self._update_csdn_status()
        self.log("🔑 CSDN 登录成功")

    def _publish_to_csdn(self):
        content = self.rewritten_view.toPlainText() or self.current_content
        if not content:
            QMessageBox.information(self, "提示", "没有可发布的内容")
            return

        if not self.csdn_cookies:
            reply = QMessageBox.question(
                self, "未登录",
                "尚未登录 CSDN，是否现在登录？",
                QMessageBox.Yes | QMessageBox.No
            )
            if reply == QMessageBox.Yes:
                self._login_csdn()
            if not self.csdn_cookies:
                return

        filepath = (
            self.file_paths[self.file_list.currentRow()]
            if self.file_paths and self.file_list.currentRow() >= 0
            else None
        )

        import re as _re
        h1 = _re.search(r'^#\s+(.+)$', content, _re.MULTILINE)
        default_title = h1.group(1).strip() if h1 else (
            Path(filepath).stem if filepath else "未命名文章"
        )

        content = Exporter.adapt_csdn_format(content)
        from PySide6.QtWidgets import (
            QLineEdit, QComboBox, QCheckBox,
            QDialogButtonBox, QFormLayout,
        )

        pub_dialog = QDialog(self)
        pub_dialog.setWindowTitle("CSDN 发布设置")
        pub_layout = QFormLayout(pub_dialog)

        pub_title = QLineEdit(default_title)
        pub_layout.addRow("标题:", pub_title)

        pub_tags = QLineEdit("技术")
        pub_tags.setPlaceholderText("多个标签用逗号分隔")
        pub_layout.addRow("标签:", pub_tags)

        pub_categories = QLineEdit()
        pub_categories.setPlaceholderText("可选")
        pub_layout.addRow("分类:", pub_categories)

        pub_type = QComboBox()
        pub_type.addItems(["原创", "转载", "翻译"])
        pub_layout.addRow("类型:", pub_type)

        pub_base64 = QCheckBox("将图片转为 base64 嵌入（体积大但 100% 可靠）")
        pub_layout.addRow(pub_base64)

        pub_buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        pub_buttons.button(QDialogButtonBox.Ok).setText("发布")
        pub_buttons.accepted.connect(pub_dialog.accept)
        pub_buttons.rejected.connect(pub_dialog.reject)
        pub_layout.addRow(pub_buttons)

        if pub_dialog.exec() != QDialog.Accepted:
            return

        title = pub_title.text().strip() or default_title
        tags = pub_tags.text().strip() or "技术"
        categories = pub_categories.text().strip()
        pub_type_str = pub_type.currentText()
        type_map = {"原创": "original", "转载": "reprint", "翻译": "translate"}
        use_base64 = pub_base64.isChecked()

        if use_base64:
            self.log("🖼️ 正在将图片转为 base64...")
            self.status_label.setText("正在嵌入图片...")
            QApplication.processEvents()
            content = self._embed_images_base64(content)

        self.log(f"📤 正在发布到 CSDN: {title}")
        self.status_label.setText("发布中...")
        QApplication.processEvents()

        try:
            result = csdn_publish(
                title=title,
                markdown_content=content,
                cookies=self.csdn_cookies,
                is_new=True,
                tags=tags,
                categories=categories,
                article_type=type_map.get(pub_type_str, "original"),
            )
            url = result.get("data", {}).get("url", "")
            msg = "✅ 发布成功！"
            if url:
                msg += f"\n文章链接: {url}"
            QMessageBox.information(self, "发布成功", msg)
            self.log(f"✅ CSDN 发布成功: {url or ''}")
        except PermissionError as e:
            self.log(f"❌ 登录过期: {e}")
            self.csdn_cookies = None
            self.settings.set("csdn_cookies", "")
            self._update_csdn_status()
            reply = QMessageBox.question(
                self, "登录过期",
                f"{e}\n\n是否重新登录？",
                QMessageBox.Yes | QMessageBox.No
            )
            if reply == QMessageBox.Yes:
                self._login_csdn()
        except Exception as e:
            self.log(f"❌ 发布失败: {e}")
            QMessageBox.critical(self, "发布失败", str(e))
        finally:
            self.status_label.setText("就绪")

    @staticmethod
    def _embed_images_base64(markdown: str) -> str:
        import base64 as _b64
        import re as _re
        img_re = _re.compile(r'!\[(.*?)\]\((.+?)\)')

        def _replace(m):
            alt = m.group(1)
            url = m.group(2)
            if url.startswith("data:"):
                return m.group(0)
            try:
                p = Path(url)
                if p.exists():
                    data = p.read_bytes()
                else:
                    import httpx as _hx
                    resp = _hx.get(url, timeout=30.0, follow_redirects=True)
                    resp.raise_for_status()
                    data = resp.content
                b64 = _b64.b64encode(data).decode()
                ext = p.suffix.lower() if p.suffix else ".png"
                mime_map = {
                    ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
                    ".png": "image/png", ".gif": "image/gif",
                    ".webp": "image/webp",
                }
                mime = mime_map.get(ext, "image/png")
                return f"![{alt}](data:{mime};base64,{b64})"
            except Exception:
                return m.group(0)

        return img_re.sub(_replace, markdown)
