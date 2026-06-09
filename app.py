import os
from pathlib import Path

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QAction, QDragEnterEvent, QDropEvent, QFont
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QHBoxLayout, QVBoxLayout,
    QSplitter, QListWidget, QListWidgetItem, QTabWidget,
    QTextEdit, QToolBar, QStatusBar, QLabel, QPushButton,
    QFileDialog, QMessageBox, QProgressBar
)

from parser import parse_markdown
from settings import Settings
from login_window import CsdnLoginWindow
from csdn_uploader import CSDNUploader
from image_handler import ImageHandler


class UploadWorker(QThread):
    progress = Signal(int, int, str, bool)
    finished = Signal(object)

    def __init__(self, handler, images):
        super().__init__()
        self.handler = handler
        self.images = images

    def run(self):
        results = self.handler.upload_all(
            self.images, progress_callback=self._on_progress
        )
        self.finished.emit(results)

    def _on_progress(self, current, total, path, success):
        self.progress.emit(current, total, path, success)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.settings = Settings()
        self.file_paths = []
        self.csdn_uploader = CSDNUploader()
        self.image_handler = ImageHandler(self.csdn_uploader)
        self.current_content = ""
        self.current_result = None
        self._setup_ui()
        self._restore_login()

    def _setup_ui(self):
        self.setWindowTitle("Blog Compiler v0.2")
        self.resize(1300, 850)

        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        self._build_toolbar()

        splitter = QSplitter(Qt.Horizontal)

        self.file_list = QListWidget()
        self.file_list.setMinimumWidth(200)
        self.file_list.setMaximumWidth(350)
        self.file_list.itemClicked.connect(self._on_file_selected)

        self.content_tabs = QTabWidget()
        self.original_view = QTextEdit()
        self.original_view.setReadOnly(True)
        self.original_view.setFont(QFont("Consolas", 10))

        preview_tab = QWidget()
        preview_layout = QVBoxLayout(preview_tab)
        self.preview_placeholder = QLabel("选择文件后查看解析信息")
        self.preview_placeholder.setAlignment(Qt.AlignCenter)
        preview_layout.addWidget(self.preview_placeholder)

        self.content_tabs.addTab(self.original_view, "原文")
        self.content_tabs.addTab(preview_tab, "预览")

        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(4, 4, 4, 4)

        op_label = QLabel("操作面板")
        op_font = QFont()
        op_font.setBold(True)
        op_label.setFont(op_font)
        right_layout.addWidget(op_label)

        self.btn_login = QPushButton("登录 CSDN")
        self.btn_login.clicked.connect(self._login_csdn)
        right_layout.addWidget(self.btn_login)

        self.btn_upload = QPushButton("上传图片到 CSDN")
        self.btn_upload.clicked.connect(self._upload_images)
        self.btn_upload.setEnabled(False)
        right_layout.addWidget(self.btn_upload)

        self.btn_ai = QPushButton("AI 改写")
        self.btn_ai.setEnabled(False)
        right_layout.addWidget(self.btn_ai)

        self.btn_export = QPushButton("导出")
        self.btn_export.setEnabled(False)
        right_layout.addWidget(self.btn_export)

        right_layout.addSpacing(10)
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
        self.login_status = QLabel("CSDN: 未登录")
        self.file_count_label = QLabel("文件: 0")
        self.image_count_label = QLabel("图片: 0")
        self.status_bar.addWidget(self.status_label, 1)
        self.status_bar.addPermanentWidget(self.login_status)
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
        self.current_content = ""
        self.current_result = None
        self._update_status()
        self.log("已清空文件列表")

    def _on_file_selected(self, item):
        filepath = item.data(Qt.UserRole)
        try:
            content = Path(filepath).read_text(encoding="utf-8")
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
            has_images = len(result.images) > 0
            self.btn_upload.setEnabled(has_images and self.csdn_uploader.cookies)

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

    def _restore_login(self):
        saved = self.settings.get_encrypted("csdn_cookies")
        if saved:
            try:
                import json
                cookies = json.loads(saved)
                self.csdn_uploader.login(cookies)
                self.image_handler.set_uploader(self.csdn_uploader)
                self._update_login_status(True)
                self.log("🔑 已恢复 CSDN 登录状态")
                self._verify_login()
            except Exception:
                pass

    def _verify_login(self):
        ok = self.csdn_uploader.verify_login()
        if not ok:
            self.log("⚠️ CSDN Cookie 已过期，请重新登录")
            self.csdn_uploader.cookies = {}
            self.settings.set_encrypted("csdn_cookies", "{}")
            self._update_login_status(False)
        else:
            self.log("✅ CSDN 登录状态有效")

    def _login_csdn(self):
        dialog = CsdnLoginWindow(self)
        dialog.login_successful.connect(self._on_login_success)
        dialog.exec()

    def _on_login_success(self, cookies):
        self.csdn_uploader.login(cookies)
        self.image_handler.set_uploader(self.csdn_uploader)
        self._update_login_status(True)

        import json
        self.settings.set_encrypted("csdn_cookies", json.dumps(cookies))

        self.log("✅ CSDN 登录成功")
        self._enable_buttons_after_login()

    def _update_login_status(self, logged_in: bool):
        if logged_in:
            self.login_status.setText("CSDN: ✅ 已登录")
            self.btn_login.setText("已登录 CSDN")
        else:
            self.login_status.setText("CSDN: ❌ 未登录")
            self.btn_login.setText("登录 CSDN")

    def _enable_buttons_after_login(self):
        if self.current_result and len(self.current_result.images) > 0:
            self.btn_upload.setEnabled(True)

    def _upload_images(self):
        if not self.current_result or not self.current_result.images:
            QMessageBox.information(self, "提示", "当前文件没有需要上传的图片")
            return

        if not self.csdn_uploader.cookies:
            QMessageBox.warning(self, "提示", "请先登录 CSDN")
            return

        images = self.current_result.images
        self.log(f"🖼️ 开始上传 {len(images)} 张图片...")

        self.progress_bar.setVisible(True)
        self.progress_bar.setMaximum(len(images))
        self.progress_bar.setValue(0)

        self.worker = UploadWorker(self.image_handler, images)
        self.worker.progress.connect(self._on_upload_progress)
        self.worker.finished.connect(self._on_upload_finished)
        self.worker.start()

    def _on_upload_progress(self, current, total, path, success):
        self.progress_bar.setValue(current)
        status = "✅" if success else "❌"
        self.log(f"  {status} [{current}/{total}] {Path(path).name}")

    def _on_upload_finished(self, results):
        self.progress_bar.setVisible(False)
        success_count = sum(1 for r in results if r.success)
        fail_count = len(results) - success_count
        self.log(f"📊 上传完成: {success_count} 成功, {fail_count} 失败")

        if success_count > 0 and self.current_content:
            new_content = self.image_handler.replace_in_markdown(
                self.current_content, results
            )
            self.current_content = new_content
            self.original_view.setText(new_content)
            self.current_result = parse_markdown(new_content)
            self.log("✅ 已替换图片链接为 CSDN URL")

            self.btn_export.setEnabled(True)

        if fail_count > 0:
            fail_paths = [r.original_path for r in results if not r.success]
            for p in fail_paths:
                self.log(f"  ❌ 上传失败: {p}")
