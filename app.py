from pathlib import Path

from PySide6.QtCore import Qt, QThread, Signal, QUrl, QByteArray
from PySide6.QtGui import QAction, QDragEnterEvent, QDropEvent, QFont, QDesktopServices, QPixmap, QPainter, QIcon
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout,
    QSplitter, QListWidget, QListWidgetItem, QAbstractItemView,
    QTabWidget, QTextEdit, QTextBrowser, QToolBar, QStatusBar,
    QLabel, QPushButton, QFileDialog, QMessageBox, QProgressBar,
    QDialog, QLineEdit, QComboBox, QFormLayout, QDialogButtonBox,
    QGroupBox, QSpinBox, QDoubleSpinBox, QHBoxLayout, QFrame,
    QCheckBox, QPlainTextEdit,
)

from PySide6.QtSvg import QSvgRenderer

import mistune

from parser import parse_markdown
from settings import Settings
from ai_rewriter import AIRewriter, RewriteConfig
from exporter import Exporter
from image_uploader import upload_images
from icons import get as get_icon
from version import VERSION
from publishers import init_publishers, get_publishers, get_publisher


class UpdateChecker(QThread):
    update_available = Signal(str, str)

    def run(self):
        try:
            import httpx
            resp = httpx.get(
                "https://api.github.com/repos/200762zzy/Blog-Compiler/releases/latest",
                timeout=10.0
            )
            data = resp.json()
            latest_tag = data.get("tag_name", "").lstrip("v")
            if latest_tag and self._is_newer(latest_tag, VERSION):
                url = data.get("html_url", "")
                self.update_available.emit(latest_tag, url)
        except Exception:
            pass

    @staticmethod
    def _is_newer(latest: str, current: str) -> bool:
        try:
            l = tuple(int(x) for x in latest.split("."))
            c = tuple(int(x) for x in current.split("."))
            return l > c
        except Exception:
            return False


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
        self.drafts = []
        self._rewrite_gen = 0
        self._setup_ui()
        self._restore_ai_settings()
        self._custom_tone_text = ""
        init_publishers(self.settings)
        self._update_all_publisher_status()
        self._check_for_updates()

        ico = QIcon("icon.ico")
        if ico.isNull():
            ico = QIcon(str(Path(__file__).parent / "icon.ico"))
        if ico.isNull():
            import sys as _sys
            base = getattr(_sys, '_MEIPASS', Path(__file__).parent)
            ico = QIcon(str(Path(base) / "icon.ico"))
        self.setWindowIcon(ico)

    def _check_for_updates(self):
        self._updater = UpdateChecker()
        self._updater.update_available.connect(self._on_update_available)
        self._updater.start()

    def _on_update_available(self, version: str, url: str):
        msg = QMessageBox(self)
        msg.setIcon(QMessageBox.Information)
        msg.setWindowTitle("发现新版本")
        msg.setText(f"Blog Compiler v{version} 已发布")
        msg.setInformativeText(f"当前版本: v{VERSION}\n是否前往下载？")
        msg.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
        msg.button(QMessageBox.Yes).setText("前往下载")
        msg.button(QMessageBox.No).setText("稍后再说")
        if msg.exec() == QMessageBox.Yes:
            QDesktopServices.openUrl(QUrl(url))

    def _setup_ui(self):
        self.setWindowTitle("Blog Compiler")
        self.resize(1300, 850)

        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        self._build_command_bar()
        main_layout.addWidget(self._command_bar)

        splitter = QSplitter(Qt.Horizontal)
        splitter.setHandleWidth(1)
        splitter.setChildrenCollapsible(False)

        self.file_list = QListWidget()
        self.file_list.setObjectName("fileList")
        self.file_list.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.file_list.setMinimumWidth(200)
        self.file_list.setMaximumWidth(350)
        self.file_list.itemClicked.connect(self._on_file_selected)

        self.content_tabs = QTabWidget()
        self.content_tabs.setObjectName("contentTabs")
        self.original_view = QTextEdit()
        self.original_view.setObjectName("editor")
        self.original_view.setReadOnly(True)
        self.original_view.setFont(QFont("Consolas", 10))

        preview_tab = QWidget()
        preview_layout = QVBoxLayout(preview_tab)
        preview_layout.setContentsMargins(8, 8, 8, 8)

        self.preview_stats = QLabel("选择文件后自动生成预览")
        self.preview_stats.setObjectName("previewStats")
        self.preview_stats.setMaximumHeight(28)
        preview_layout.addWidget(self.preview_stats)

        self.image_status_list = QListWidget()
        self.image_status_list.setObjectName("imageStatus")
        self.image_status_list.setMaximumHeight(100)
        self.image_status_list.setVisible(False)
        preview_layout.addWidget(self.image_status_list)

        self.preview_render = QTextBrowser()
        self.preview_render.setObjectName("previewRender")
        self.preview_render.setOpenExternalLinks(False)
        preview_layout.addWidget(self.preview_render, 1)

        self.rewritten_view = QTextEdit()
        self.rewritten_view.setObjectName("editor")
        self.rewritten_view.setFont(QFont("Consolas", 10))

        self.content_tabs.addTab(self.original_view, "原文")
        self.content_tabs.addTab(preview_tab, "预览")
        self.content_tabs.addTab(self.rewritten_view, "改写后")
        self.content_tabs.setTabEnabled(2, False)

        right_panel = QWidget()
        right_panel.setObjectName("rightPanel")
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(8, 8, 8, 8)
        right_layout.setSpacing(8)

        def _make_card(title: str) -> tuple[QFrame, QVBoxLayout]:
            card = QFrame()
            card.setObjectName("card")
            cl = QVBoxLayout(card)
            cl.setContentsMargins(12, 10, 12, 10)
            cl.setSpacing(6)
            if title:
                tl = QLabel(title)
                tl.setObjectName("cardTitle")
                cl.addWidget(tl)
            right_layout.addWidget(card)
            return card, cl

        # Card 1: AI 改写
        card_ai, cl_ai = _make_card("AI 改写")
        tone_row = QHBoxLayout()
        tone_row.setSpacing(6)
        tone_label = QLabel("语气")
        tone_label.setObjectName("toneLabel")
        tone_row.addWidget(tone_label)
        self.tone_combo = QComboBox()
        self.tone_combo.addItems(["技术博主风", "学生笔记风", "教程风", "轻松口语化", "自定义..."])
        self.tone_combo.currentTextChanged.connect(self._on_tone_changed)
        tone_row.addWidget(self.tone_combo, 1)
        cl_ai.addLayout(tone_row)

        self.btn_ai = QPushButton(" AI 改写")
        self.btn_ai.setIcon(get_icon("ai"))
        self.btn_ai.setObjectName("primaryBtn")
        self.btn_ai.clicked.connect(self._ai_rewrite)
        self.btn_ai.setEnabled(False)
        cl_ai.addWidget(self.btn_ai)

        self.btn_export = QPushButton(" 导出文件")
        self.btn_export.setIcon(get_icon("export"))
        self.btn_export.setObjectName("secondaryBtn")
        self.btn_export.clicked.connect(self._export_file)
        self.btn_export.setEnabled(False)
        cl_ai.addWidget(self.btn_export)

        self.btn_copy = QPushButton(" 复制到剪贴板")
        self.btn_copy.setIcon(get_icon("copy"))
        self.btn_copy.setObjectName("secondaryBtn")
        self.btn_copy.clicked.connect(self._export_clipboard)
        self.btn_copy.setEnabled(False)
        cl_ai.addWidget(self.btn_copy)

        draft_row = QHBoxLayout()
        draft_row.setSpacing(4)
        self.draft_combo = QComboBox()
        self.draft_combo.setObjectName("draftCombo")
        self.draft_combo.setPlaceholderText("草稿历史")
        self.draft_combo.setEnabled(False)
        draft_row.addWidget(self.draft_combo, 1)
        self.btn_restore_draft = QPushButton("恢复")
        self.btn_restore_draft.setObjectName("draftBtn")
        self.btn_restore_draft.setEnabled(False)
        self.btn_restore_draft.clicked.connect(self._switch_draft)
        draft_row.addWidget(self.btn_restore_draft)
        cl_ai.addLayout(draft_row)

        # Card 2: 图片处理
        card_img, cl_img = _make_card("图片处理")
        from PySide6.QtWidgets import QButtonGroup, QRadioButton
        self.img_mode_group = QButtonGroup(self)
        self.rb_img_alt = QRadioButton("生成 alt 文本（删路径）")
        self.rb_img_upload = QRadioButton("上传 scdn.io 图床")
        self.rb_img_keep = QRadioButton("保留原路径")
        self.rb_img_alt.setChecked(True)
        self.img_mode_group.addButton(self.rb_img_alt, 1)
        self.img_mode_group.addButton(self.rb_img_upload, 2)
        self.img_mode_group.addButton(self.rb_img_keep, 3)
        cl_img.addWidget(self.rb_img_alt)
        cl_img.addWidget(self.rb_img_upload)
        cl_img.addWidget(self.rb_img_keep)

        # Card 3: 多平台发布
        card_pub, cl_pub = _make_card("多平台发布")
        self._pub_status_labels = {}
        self._pub_login_btns = {}
        for p in get_publishers():
            row = QHBoxLayout()
            status = QLabel("❌ 未登录")
            status.setObjectName(f"{p.name}Status")
            self._pub_status_labels[p.name] = status
            row.addWidget(QLabel(f"{p.name}:"))
            row.addWidget(status)

            login_btn = QPushButton("登录")
            login_btn.setObjectName("secondaryBtn")
            login_btn.clicked.connect(lambda checked, name=p.name: self._publisher_login(name))
            self._pub_login_btns[p.name] = login_btn
            row.addWidget(login_btn)

            cl_pub.addLayout(row)

        self.btn_multi_publish = QPushButton(" 多平台发布")
        self.btn_multi_publish.setIcon(get_icon("publish"))
        self.btn_multi_publish.setObjectName("primaryBtn")
        self.btn_multi_publish.clicked.connect(self._open_publish_dialog)
        self.btn_multi_publish.setEnabled(False)
        cl_pub.addWidget(self.btn_multi_publish)

        # Card 4: 日志
        card_log, cl_log = _make_card("")
        self.log_view = QTextEdit()
        self.log_view.setObjectName("logView")
        self.log_view.setReadOnly(True)
        self.log_view.setFont(QFont("Consolas", 9))
        self.log_view.setMaximumHeight(200)
        self.log_view.setPlaceholderText("运行日志将显示在这里")
        cl_log.addWidget(self.log_view)

        self.progress_bar = QProgressBar()
        self.progress_bar.setObjectName("progressBar")
        self.progress_bar.setVisible(False)
        cl_log.addWidget(self.progress_bar)

        right_layout.addStretch()

        splitter.addWidget(self.file_list)
        splitter.addWidget(self.content_tabs)
        splitter.addWidget(right_panel)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 4)
        splitter.setStretchFactor(2, 1)

        main_layout.addWidget(splitter, 1)

        self.status_bar = QStatusBar()
        self.status_bar.setObjectName("statusBar")
        self.status_label = QLabel("就绪")
        self.status_label.setObjectName("statusLabel")
        self.file_count_label = QLabel("文件: 0")
        self.file_count_label.setObjectName("statusLabel")
        self.image_count_label = QLabel("图片: 0")
        self.image_count_label.setObjectName("statusLabel")
        self.status_bar.addWidget(self.status_label, 1)
        self.status_bar.addPermanentWidget(self.file_count_label)
        self.status_bar.addPermanentWidget(self.image_count_label)
        self.setStatusBar(self.status_bar)

        self.setAcceptDrops(True)

    def _build_command_bar(self):
        bar = QFrame()
        bar.setObjectName("commandBar")
        bar.setFixedHeight(48)
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(12, 0, 12, 0)
        layout.setSpacing(4)

        logo_data = QByteArray(b'<svg viewBox="0 0 32 32" fill="none"><rect width="32" height="32" rx="6" fill="#06B6D4"/><text x="16" y="22" text-anchor="middle" fill="white" font-size="18" font-weight="bold" font-family="sans-serif">B</text></svg>')
        logo_pix = QPixmap(28, 28)
        logo_pix.fill(Qt.transparent)
        p = QPainter(logo_pix)
        QSvgRenderer(logo_data).render(p)
        p.end()
        logo_label = QLabel()
        logo_label.setPixmap(logo_pix)
        logo_label.setFixedSize(28, 28)
        layout.addWidget(logo_label)
        layout.addSpacing(8)

        title = QLabel("Blog Compiler")
        title.setObjectName("barTitle")
        layout.addWidget(title)
        layout.addSpacing(16)

        def _cmd_btn(text, icon_name, slot):
            btn = QPushButton(text)
            btn.setIcon(get_icon(icon_name))
            btn.setObjectName("cmdBtn")
            btn.clicked.connect(slot)
            layout.addWidget(btn)
            return btn

        self.action_add = _cmd_btn("添加文件", "add", self._add_files)
        self.action_clear = _cmd_btn("清空", "clear", self._clear_files)

        layout.addStretch()

        self.action_dark = QPushButton()
        self.action_dark.setIcon(get_icon("dark"))
        self.action_dark.setObjectName("cmdIconBtn")
        self.action_dark.setCheckable(True)
        self.action_dark.setToolTip("切换暗色/亮色模式")
        self.action_dark.clicked.connect(self._toggle_dark)
        layout.addWidget(self.action_dark)

        self.action_settings = QPushButton()
        self.action_settings.setIcon(get_icon("settings"))
        self.action_settings.setObjectName("cmdIconBtn")
        self.action_settings.setToolTip("设置")
        self.action_settings.clicked.connect(self._show_settings)
        layout.addWidget(self.action_settings)

        self._command_bar = bar

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
                try:
                    content = Path(filepath).read_text(encoding="gbk")
                except Exception as e2:
                    QMessageBox.warning(self, "读取失败", f"无法读取文件:\n{e2}")
                    return
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

            self.preview_stats.setText(
                f"📊 {result.paragraph_count}段 · {result.code_block_count}代码块"
                f" · {len(result.images)}图 · {result.table_count}表"
            )
            tooltip_lines = ["📊 解析详情"]
            tooltip_lines.append(f"段落: {result.paragraph_count}")
            tooltip_lines.append(f"代码块: {result.code_block_count}")
            tooltip_lines.append(f"图片: {len(result.images)}")
            tooltip_lines.append(f"表格: {result.table_count}")
            if result.headings:
                tooltip_lines.append("")
                tooltip_lines.append("标题结构:")
                for lvl, h in result.headings[:15]:
                    tooltip_lines.append(f"  {'  ' * (lvl-1)}H{lvl} {h}")
                if len(result.headings) > 15:
                    tooltip_lines.append(f"  ...及其他 {len(result.headings) - 15} 个")
            if result.images:
                tooltip_lines.append("")
                tooltip_lines.append("图片列表:")
                for p in result.images[:10]:
                    tooltip_lines.append(f"  📷 {Path(p).name}")
                if len(result.images) > 10:
                    tooltip_lines.append(f"  ...及其他 {len(result.images) - 10} 张")
            self.preview_stats.setToolTip("\n".join(tooltip_lines))
            self.preview_render.setHtml(mistune.html(content))

            self.image_status_list.clear()
            self.image_status_list.setVisible(False)

    def _toggle_dark(self, checked):
        if checked:
            self._apply_dark_theme()
            self.action_dark.setIcon(get_icon("light"))
            self.action_dark.setToolTip("切换亮色模式")
            self.settings.set("dark_mode", True)
            self.log("已切换暗色模式")
        else:
            self._apply_light_theme()
            self.action_dark.setIcon(get_icon("dark"))
            self.action_dark.setToolTip("切换暗色模式")
            self.settings.set("dark_mode", False)
            self.log("已切换亮色模式")

    def _apply_dark_theme(self):
        self.setStyleSheet("""
            QMainWindow, QWidget#rightPanel {
                background-color: #1a1a1a;
                color: #E2E8F0;
            }
            QWidget {
                background-color: transparent;
                color: #E2E8F0;
                font-size: 13px;
            }
            QFrame#commandBar {
                background-color: #1f1f1f;
                border-bottom: 1px solid #2e2e2e;
            }
            QLabel#barTitle {
                font-size: 14px;
                font-weight: 600;
                color: #E2E8F0;
            }
            QPushButton#cmdBtn {
                background-color: transparent;
                color: #94A3B8;
                border: none;
                padding: 6px 12px;
                border-radius: 6px;
                font-size: 13px;
            }
            QPushButton#cmdBtn:hover {
                background-color: #2e2e2e;
                color: #E2E8F0;
            }
            QPushButton#cmdIconBtn {
                background-color: transparent;
                color: #94A3B8;
                border: none;
                border-radius: 6px;
                padding: 6px;
                min-width: 32px;
                min-height: 32px;
            }
            QPushButton#cmdIconBtn:hover {
                background-color: #2e2e2e;
                color: #E2E8F0;
            }
            QPushButton#cmdIconBtn:checked {
                background-color: #06B6D4;
                color: white;
            }
            QFrame#card {
                background-color: #242424;
                border: 1px solid #2e2e2e;
                border-radius: 8px;
            }
            QLabel#cardTitle {
                font-size: 12px;
                font-weight: 600;
                color: #94A3B8;
                text-transform: uppercase;
                letter-spacing: 1px;
                padding-bottom: 4px;
            }
            QPushButton#primaryBtn {
                background-color: #06B6D4;
                color: white;
                border: none;
                border-radius: 6px;
                padding: 8px 16px;
                font-size: 13px;
                font-weight: 500;
            }
            QPushButton#primaryBtn:hover {
                background-color: #22D3EE;
            }
            QPushButton#primaryBtn:pressed {
                background-color: #0891B2;
            }
            QPushButton#primaryBtn:disabled {
                background-color: #155e75;
                color: #94A3B8;
            }
            QPushButton#secondaryBtn {
                background-color: transparent;
                color: #E2E8F0;
                border: 1px solid #3e3e3e;
                border-radius: 6px;
                padding: 7px 16px;
                font-size: 13px;
            }
            QPushButton#secondaryBtn:hover {
                background-color: #2e2e2e;
                border-color: #555555;
            }
            QPushButton#secondaryBtn:disabled {
                color: #555555;
                border-color: #333333;
            }
            QLabel#csdnStatus {
                font-size: 12px;
                color: #94A3B8;
            }
            QListWidget, QListWidget#fileList {
                background-color: #1e1e1e;
                color: #E2E8F0;
                border: none;
                border-radius: 0px;
                outline: none;
            }
            QListWidget::item {
                padding: 8px 12px;
                border-radius: 6px;
                margin: 2px 6px;
            }
            QListWidget::item:selected {
                background-color: #06B6D4;
                color: white;
            }
            QListWidget::item:hover:!selected {
                background-color: #2a2a2a;
            }
            QListWidget#imageStatus {
                background-color: #1e1e1e;
                border: 1px solid #2e2e2e;
                border-radius: 6px;
                font-size: 12px;
            }
            QListWidget#imageStatus::item {
                padding: 4px 8px;
                margin: 1px 4px;
                border-radius: 4px;
            }
            QTextEdit, QTextBrowser {
                background-color: #1e1e1e;
                color: #E2E8F0;
                border: none;
                border-radius: 0px;
                padding: 8px;
            }
            QTextEdit#editor {
                border: none;
            }
            QTextEdit#logView {
                background-color: #1a1a1a;
                border: 1px solid #2e2e2e;
                border-radius: 6px;
                font-size: 12px;
                padding: 6px;
            }
            QLabel#previewStats {
                background-color: #1e1e1e;
                border: 1px solid #2e2e2e;
                border-radius: 6px;
                padding: 10px;
                font-size: 12px;
            }
            QTabWidget#contentTabs::pane {
                background-color: #1e1e1e;
                border: none;
                border-top: 1px solid #2e2e2e;
            }
            QTabBar::tab {
                background-color: transparent;
                color: #64748B;
                border: none;
                padding: 8px 20px;
                font-size: 13px;
                border-bottom: 2px solid transparent;
            }
            QTabBar::tab:selected {
                color: #06B6D4;
                border-bottom: 2px solid #06B6D4;
            }
            QTabBar::tab:hover:!selected {
                color: #94A3B8;
                border-bottom: 2px solid #3e3e3e;
            }
            QComboBox, QComboBox#draftCombo {
                background-color: #1e1e1e;
                color: #E2E8F0;
                border: 1px solid #3e3e3e;
                border-radius: 6px;
                padding: 6px 10px;
                font-size: 12px;
                min-height: 20px;
            }
            QComboBox:hover {
                border-color: #555555;
            }
            QComboBox::drop-down {
                border: none;
                width: 24px;
            }
            QComboBox::down-arrow {
                image: none;
                border-left: 5px solid transparent;
                border-right: 5px solid transparent;
                border-top: 5px solid #94A3B8;
                margin-right: 6px;
            }
            QComboBox QAbstractItemView {
                background-color: #242424;
                color: #E2E8F0;
                border: 1px solid #3e3e3e;
                border-radius: 6px;
                selection-background-color: #06B6D4;
                selection-color: white;
                padding: 4px;
            }
            QPushButton#draftBtn {
                background-color: transparent;
                color: #94A3B8;
                border: 1px solid #3e3e3e;
                border-radius: 6px;
                padding: 4px 10px;
                font-size: 11px;
                min-width: 40px;
            }
            QPushButton#draftBtn:hover {
                background-color: #2e2e2e;
                color: #E2E8F0;
            }
            QPushButton#draftBtn:disabled {
                color: #555555;
                border-color: #333333;
            }
            QRadioButton {
                spacing: 8px;
                font-size: 12px;
                color: #94A3B8;
                padding: 4px 0;
            }
            QRadioButton::indicator {
                width: 16px;
                height: 16px;
                border-radius: 8px;
                border: 2px solid #555555;
                background-color: transparent;
            }
            QRadioButton::indicator:checked {
                border: 2px solid #06B6D4;
                background-color: #06B6D4;
            }
            QRadioButton::indicator:hover {
                border-color: #94A3B8;
            }
            QProgressBar#progressBar {
                background-color: #1e1e1e;
                border: none;
                border-radius: 4px;
                text-align: center;
                color: white;
                font-size: 11px;
                height: 6px;
            }
            QProgressBar::chunk {
                background-color: #06B6D4;
                border-radius: 4px;
            }
            QStatusBar#statusBar {
                background-color: #06B6D4;
                color: white;
                font-size: 12px;
                padding: 2px 12px;
                border: none;
            }
            QStatusBar::item {
                border: none;
            }
            QLabel#statusLabel {
                color: white;
                font-size: 12px;
            }
            QSplitter::handle {
                background-color: #2e2e2e;
            }
            QScrollBar:vertical {
                background-color: #1a1a1a;
                width: 8px;
                margin: 0;
                border-radius: 4px;
            }
            QScrollBar::handle:vertical {
                background-color: #333333;
                border-radius: 4px;
                min-height: 30px;
            }
            QScrollBar::handle:vertical:hover {
                background-color: #555555;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0;
                background: none;
            }
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
                background: none;
            }
            QScrollBar:horizontal {
                background-color: #1a1a1a;
                height: 8px;
                margin: 0;
                border-radius: 4px;
            }
            QScrollBar::handle:horizontal {
                background-color: #333333;
                border-radius: 4px;
                min-width: 30px;
            }
            QScrollBar::handle:horizontal:hover {
                background-color: #555555;
            }
            QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
                width: 0;
                background: none;
            }
            QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {
                background: none;
            }
            QDialog {
                background-color: #242424;
            }
            QGroupBox {
                border: 1px solid #2e2e2e;
                border-radius: 8px;
                margin-top: 8px;
                padding-top: 16px;
                font-size: 13px;
                color: #94A3B8;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 12px;
                padding: 0 6px;
            }
            QLineEdit {
                background-color: #1e1e1e;
                color: #E2E8F0;
                border: 1px solid #3e3e3e;
                border-radius: 6px;
                padding: 6px 10px;
                font-size: 13px;
            }
            QLineEdit:focus {
                border-color: #06B6D4;
            }
            QDoubleSpinBox, QSpinBox {
                background-color: #1e1e1e;
                color: #E2E8F0;
                border: 1px solid #3e3e3e;
                border-radius: 6px;
                padding: 4px 8px;
                font-size: 13px;
            }
            QCheckBox {
                spacing: 8px;
                font-size: 13px;
                color: #E2E8F0;
            }
            QCheckBox::indicator {
                width: 16px;
                height: 16px;
                border-radius: 4px;
                border: 2px solid #555555;
                background-color: transparent;
            }
            QCheckBox::indicator:checked {
                background-color: #06B6D4;
                border-color: #06B6D4;
            }
            QCheckBox::indicator:hover {
                border-color: #94A3B8;
            }
            QDialogButtonBox QPushButton {
                background-color: #06B6D4;
                color: white;
                border: none;
                border-radius: 6px;
                padding: 8px 20px;
                font-size: 13px;
                min-width: 80px;
            }
            QDialogButtonBox QPushButton:hover {
                background-color: #22D3EE;
            }
        """)

    def _apply_light_theme(self):
        self.setStyleSheet("""
            QMainWindow, QWidget#rightPanel {
                background-color: #F5F5F5;
                color: #1E293B;
            }
            QWidget {
                background-color: transparent;
                color: #1E293B;
                font-size: 13px;
            }
            QFrame#commandBar {
                background-color: #FFFFFF;
                border-bottom: 1px solid #E2E8F0;
            }
            QLabel#barTitle {
                font-size: 14px;
                font-weight: 600;
                color: #1E293B;
            }
            QPushButton#cmdBtn {
                background-color: transparent;
                color: #64748B;
                border: none;
                padding: 6px 12px;
                border-radius: 6px;
                font-size: 13px;
            }
            QPushButton#cmdBtn:hover {
                background-color: #F1F5F9;
                color: #1E293B;
            }
            QPushButton#cmdIconBtn {
                background-color: transparent;
                color: #64748B;
                border: none;
                border-radius: 6px;
                padding: 6px;
                min-width: 32px;
                min-height: 32px;
            }
            QPushButton#cmdIconBtn:hover {
                background-color: #F1F5F9;
                color: #1E293B;
            }
            QPushButton#cmdIconBtn:checked {
                background-color: #0891B2;
                color: white;
            }
            QFrame#card {
                background-color: #FFFFFF;
                border: 1px solid #E2E8F0;
                border-radius: 8px;
            }
            QLabel#cardTitle {
                font-size: 12px;
                font-weight: 600;
                color: #64748B;
                text-transform: uppercase;
                letter-spacing: 1px;
                padding-bottom: 4px;
            }
            QPushButton#primaryBtn {
                background-color: #0891B2;
                color: white;
                border: none;
                border-radius: 6px;
                padding: 8px 16px;
                font-size: 13px;
                font-weight: 500;
            }
            QPushButton#primaryBtn:hover {
                background-color: #0E7490;
            }
            QPushButton#primaryBtn:pressed {
                background-color: #155E75;
            }
            QPushButton#primaryBtn:disabled {
                background-color: #CBD5E1;
                color: #94A3B8;
            }
            QPushButton#secondaryBtn {
                background-color: transparent;
                color: #1E293B;
                border: 1px solid #CBD5E1;
                border-radius: 6px;
                padding: 7px 16px;
                font-size: 13px;
            }
            QPushButton#secondaryBtn:hover {
                background-color: #F8FAFC;
                border-color: #94A3B8;
            }
            QPushButton#secondaryBtn:disabled {
                color: #CBD5E1;
                border-color: #E2E8F0;
            }
            QLabel#csdnStatus {
                font-size: 12px;
                color: #64748B;
            }
            QListWidget, QListWidget#fileList {
                background-color: #FFFFFF;
                color: #1E293B;
                border: none;
                border-radius: 0px;
                outline: none;
            }
            QListWidget::item {
                padding: 8px 12px;
                border-radius: 6px;
                margin: 2px 6px;
            }
            QListWidget::item:selected {
                background-color: #0891B2;
                color: white;
            }
            QListWidget::item:hover:!selected {
                background-color: #F1F5F9;
            }
            QListWidget#imageStatus {
                background-color: #FFFFFF;
                border: 1px solid #E2E8F0;
                border-radius: 6px;
                font-size: 12px;
            }
            QListWidget#imageStatus::item {
                padding: 4px 8px;
                margin: 1px 4px;
                border-radius: 4px;
            }
            QTextEdit, QTextBrowser {
                background-color: #FFFFFF;
                color: #1E293B;
                border: none;
                border-radius: 0px;
                padding: 8px;
            }
            QTextEdit#editor {
                border: none;
            }
            QTextEdit#logView {
                background-color: #FAFAFA;
                border: 1px solid #E2E8F0;
                border-radius: 6px;
                font-size: 12px;
                padding: 6px;
            }
            QLabel#previewStats {
                background-color: #FFFFFF;
                border: 1px solid #E2E8F0;
                border-radius: 6px;
                padding: 10px;
                font-size: 12px;
            }
            QTabWidget#contentTabs::pane {
                background-color: #FFFFFF;
                border: none;
                border-top: 1px solid #E2E8F0;
            }
            QTabBar::tab {
                background-color: transparent;
                color: #94A3B8;
                border: none;
                padding: 8px 20px;
                font-size: 13px;
                border-bottom: 2px solid transparent;
            }
            QTabBar::tab:selected {
                color: #0891B2;
                border-bottom: 2px solid #0891B2;
            }
            QTabBar::tab:hover:!selected {
                color: #64748B;
                border-bottom: 2px solid #CBD5E1;
            }
            QComboBox, QComboBox#draftCombo {
                background-color: #FFFFFF;
                color: #1E293B;
                border: 1px solid #CBD5E1;
                border-radius: 6px;
                padding: 6px 10px;
                font-size: 12px;
                min-height: 20px;
            }
            QComboBox:hover {
                border-color: #94A3B8;
            }
            QComboBox::drop-down {
                border: none;
                width: 24px;
            }
            QComboBox::down-arrow {
                image: none;
                border-left: 5px solid transparent;
                border-right: 5px solid transparent;
                border-top: 5px solid #64748B;
                margin-right: 6px;
            }
            QComboBox QAbstractItemView {
                background-color: #FFFFFF;
                color: #1E293B;
                border: 1px solid #E2E8F0;
                border-radius: 6px;
                selection-background-color: #0891B2;
                selection-color: white;
                padding: 4px;
            }
            QPushButton#draftBtn {
                background-color: transparent;
                color: #64748B;
                border: 1px solid #CBD5E1;
                border-radius: 6px;
                padding: 4px 10px;
                font-size: 11px;
                min-width: 40px;
            }
            QPushButton#draftBtn:hover {
                background-color: #F1F5F9;
                color: #1E293B;
            }
            QPushButton#draftBtn:disabled {
                color: #CBD5E1;
                border-color: #E2E8F0;
            }
            QRadioButton {
                spacing: 8px;
                font-size: 12px;
                color: #64748B;
                padding: 4px 0;
            }
            QRadioButton::indicator {
                width: 16px;
                height: 16px;
                border-radius: 8px;
                border: 2px solid #CBD5E1;
                background-color: transparent;
            }
            QRadioButton::indicator:checked {
                border: 2px solid #0891B2;
                background-color: #0891B2;
            }
            QRadioButton::indicator:hover {
                border-color: #94A3B8;
            }
            QProgressBar#progressBar {
                background-color: #E2E8F0;
                border: none;
                border-radius: 4px;
                text-align: center;
                color: white;
                font-size: 11px;
                height: 6px;
            }
            QProgressBar::chunk {
                background-color: #0891B2;
                border-radius: 4px;
            }
            QStatusBar#statusBar {
                background-color: #0891B2;
                color: white;
                font-size: 12px;
                padding: 2px 12px;
                border: none;
            }
            QStatusBar::item {
                border: none;
            }
            QLabel#statusLabel {
                color: white;
                font-size: 12px;
            }
            QSplitter::handle {
                background-color: #E2E8F0;
            }
            QScrollBar:vertical {
                background-color: #F5F5F5;
                width: 8px;
                margin: 0;
                border-radius: 4px;
            }
            QScrollBar::handle:vertical {
                background-color: #CBD5E1;
                border-radius: 4px;
                min-height: 30px;
            }
            QScrollBar::handle:vertical:hover {
                background-color: #94A3B8;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0;
                background: none;
            }
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
                background: none;
            }
            QScrollBar:horizontal {
                background-color: #F5F5F5;
                height: 8px;
                margin: 0;
                border-radius: 4px;
            }
            QScrollBar::handle:horizontal {
                background-color: #CBD5E1;
                border-radius: 4px;
                min-width: 30px;
            }
            QScrollBar::handle:horizontal:hover {
                background-color: #94A3B8;
            }
            QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
                width: 0;
                background: none;
            }
            QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {
                background: none;
            }
            QDialog {
                background-color: #FFFFFF;
            }
            QGroupBox {
                border: 1px solid #E2E8F0;
                border-radius: 8px;
                margin-top: 8px;
                padding-top: 16px;
                font-size: 13px;
                color: #64748B;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 12px;
                padding: 0 6px;
            }
            QLineEdit {
                background-color: #FFFFFF;
                color: #1E293B;
                border: 1px solid #CBD5E1;
                border-radius: 6px;
                padding: 6px 10px;
                font-size: 13px;
            }
            QLineEdit:focus {
                border-color: #0891B2;
            }
            QDoubleSpinBox, QSpinBox {
                background-color: #FFFFFF;
                color: #1E293B;
                border: 1px solid #CBD5E1;
                border-radius: 6px;
                padding: 4px 8px;
                font-size: 13px;
            }
            QCheckBox {
                spacing: 8px;
                font-size: 13px;
                color: #1E293B;
            }
            QCheckBox::indicator {
                width: 16px;
                height: 16px;
                border-radius: 4px;
                border: 2px solid #CBD5E1;
                background-color: transparent;
            }
            QCheckBox::indicator:checked {
                background-color: #0891B2;
                border-color: #0891B2;
            }
            QCheckBox::indicator:hover {
                border-color: #94A3B8;
            }
            QDialogButtonBox QPushButton {
                background-color: #0891B2;
                color: white;
                border: none;
                border-radius: 6px;
                padding: 8px 20px;
                font-size: 13px;
                min-width: 80px;
            }
            QDialogButtonBox QPushButton:hover {
                background-color: #0E7490;
            }
        """)

    def _apply_settings(self):
        if self.settings.get("dark_mode", False):
            self.action_dark.setChecked(True)
            self.action_dark.setIcon(get_icon("light"))
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

    def _on_tone_changed(self, text: str):
        if text == "自定义...":
            from PySide6.QtWidgets import QInputDialog
            prev = self.settings.get("ai_tone_custom", "")
            new_text, ok = QInputDialog.getMultiLineText(
                self, "自定义语气", "请输入 persona 描述：", prev
            )
            if ok and new_text.strip():
                self._custom_tone_text = new_text.strip()
                self.settings.set("ai_tone_custom", self._custom_tone_text)
            elif ok:
                prev_idx = self.tone_combo.findText("技术博主风")
                if prev_idx >= 0:
                    self.tone_combo.blockSignals(True)
                    self.tone_combo.setCurrentIndex(prev_idx)
                    self.tone_combo.blockSignals(False)
            self.settings.set("ai_tone", self.tone_combo.currentText())

    def _restore_ai_settings(self):
        api_key = self.settings.get_encrypted("ai_api_key")
        api_base = self.settings.get("ai_api_base", "https://api.openai.com/v1")
        model = self.settings.get("ai_model", "gpt-4o-mini")
        temperature = self.settings.get("ai_temperature", 0.7)
        max_tokens = self.settings.get("ai_max_tokens", 32768)
        saved_tone = self.settings.get("ai_tone", "技术博主风")
        self._custom_tone_text = self.settings.get("ai_tone_custom", "")
        idx = self.tone_combo.findText(saved_tone)
        if idx >= 0:
            self.tone_combo.blockSignals(True)
            self.tone_combo.setCurrentIndex(idx)
            self.tone_combo.blockSignals(False)
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
        self.settings_max_tokens.setValue(self.settings.get("ai_max_tokens", 32768))
        token_row.addWidget(self.settings_max_tokens)
        token_row.addWidget(QLabel("(单次最大输出 token)"))
        ai_layout.addRow("Max Tokens:", token_row)

        self.settings_model.currentIndexChanged.connect(self._on_model_changed)
        layout.addWidget(ai_group)

        prompt_group = QGroupBox("自定义 System Prompt")
        prompt_layout = QVBoxLayout(prompt_group)
        self.settings_custom_prompt = QPlainTextEdit()
        self.settings_custom_prompt.setPlaceholderText(
            "在此处编写自定义 system prompt，留空则使用语气预设\n\n"
            "注意：prompt 中必须包含图片处理指令，否则图片可能不会被正确处理"
        )
        self.settings_custom_prompt.setPlainText(
            self.settings.get("ai_custom_prompt", "")
        )
        self.settings_custom_prompt.setMinimumHeight(120)
        prompt_layout.addWidget(self.settings_custom_prompt)
        self.settings_use_custom = QCheckBox("使用自定义 prompt（代替语气预设）")
        self.settings_use_custom.setChecked(
            self.settings.get("ai_use_custom_prompt", False)
        )
        prompt_layout.addWidget(self.settings_use_custom)
        layout.addWidget(prompt_group)

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
        self.settings.set("ai_tone", self.tone_combo.currentText())
        self.settings.set("ai_tone_custom", self._custom_tone_text)
        self.settings.set("ai_custom_prompt", self.settings_custom_prompt.toPlainText())
        self.settings.set("ai_use_custom_prompt", self.settings_use_custom.isChecked())

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

        cursor = self.original_view.textCursor()
        if cursor.hasSelection():
            reply = QMessageBox.question(
                self, "改写范围",
                "检测到您在原文中选中了一段文字，是否仅改写选中区域？\n\n"
                "选「否」则改写全文。",
                QMessageBox.Yes | QMessageBox.No
            )
            if reply == QMessageBox.Yes:
                self._rewrite_selection(cursor)
                return

        mode = self._get_image_mode()
        rewrite_content = self.current_content

        if mode == "upload" and self.current_result:
            self.log("🖼️ 开始上传图片到 scdn.io...")
            self.status_label.setText("正在上传图片...")
            QApplication.processEvents()
            local_images = [p for p in self.current_result.images if Path(p).exists()]
            if local_images:
                self.image_status_list.clear()
                self.image_status_list.setVisible(True)
                for local_path in local_images:
                    item = QListWidgetItem(f"⏳ {Path(local_path).name}")
                    item.setData(Qt.UserRole, local_path)
                    self.image_status_list.addItem(item)
                from image_uploader import upload_image as _upload_one
                mapping = {}
                for local_path in local_images:
                    self._set_image_status(local_path, "⏳ 上传中...")
                    QApplication.processEvents()
                    try:
                        remote_url = _upload_one(local_path)
                        mapping[local_path] = remote_url
                        self._set_image_status(local_path, f"✅ {Path(local_path).name}")
                        self.log(f"  ✅ {Path(local_path).name} → {remote_url}")
                    except Exception as e:
                        self._set_image_status(local_path, f"❌ {Path(local_path).name}")
                        self.log(f"  ❌ {Path(local_path).name}: {e}")
                for local_path, remote_url in mapping.items():
                    rewrite_content = rewrite_content.replace(
                        f"({local_path})", f"({remote_url})"
                    )
                self.log(f"🖼️ 图片上传完成 ({len(mapping)}/{len(local_images)} 张)")
            else:
                self.log("🖼️ 无本地图片需上传，跳过")
            self.image_status_list.setVisible(False)

        system_prompt = self._build_system_prompt(mode, self.tone_combo.currentText())
        self.ai_rewriter.config.system_prompt = system_prompt

        self.log("🤖 开始 AI 改写...")
        self.status_label.setText("AI 改写中...")
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 0)
        self.btn_ai.setText("取消改写")
        self.btn_ai.setEnabled(True)
        self.btn_export.setEnabled(False)
        self.btn_copy.setEnabled(False)

        self._rewrite_gen += 1
        gen = self._rewrite_gen
        self.rewrite_worker = RewriteWorker(self.ai_rewriter, rewrite_content)
        self.rewrite_worker.finished.connect(
            lambda result, g=gen: self._on_rewrite_finished(result, g)
        )
        self.rewrite_worker.error.connect(
            lambda msg, g=gen: self._on_rewrite_error(msg, g)
        )
        self.rewrite_worker.cancelled.connect(
            lambda g=gen: self._on_rewrite_cancelled(g)
        )
        self.rewrite_worker.start()

    def _rewrite_selection(self, cursor):
        start = cursor.selectionStart()
        end = cursor.selectionEnd()
        full_text = self.original_view.toPlainText()
        selected = full_text[start:end]
        if not selected.strip():
            QMessageBox.information(self, "提示", "选中内容为空")
            return

        mode = self._get_image_mode()
        rewrite_content = selected

        if mode == "upload" and self.current_result:
            local_images = [p for p in self.current_result.images if Path(p).exists()]
            local_in_sel = [p for p in local_images if p in selected]
            if local_in_sel:
                self.image_status_list.clear()
                self.image_status_list.setVisible(True)
                for local_path in local_in_sel:
                    item = QListWidgetItem(f"⏳ {Path(local_path).name}")
                    item.setData(Qt.UserRole, local_path)
                    self.image_status_list.addItem(item)
                self.log(f"🖼️ 上传选中区域内的图片 ({len(local_in_sel)} 张)...")
                self.status_label.setText("正在上传图片...")
                QApplication.processEvents()
                from image_uploader import upload_image as _upload_one
                mapping = {}
                for local_path in local_in_sel:
                    try:
                        self._set_image_status(local_path, "⏳ 上传中...")
                        QApplication.processEvents()
                        remote_url = _upload_one(local_path)
                        mapping[local_path] = remote_url
                        self._set_image_status(local_path, f"✅ {Path(local_path).name}")
                        self.log(f"  ✅ {Path(local_path).name} → {remote_url}")
                    except Exception as e:
                        self._set_image_status(local_path, f"❌ {Path(local_path).name}")
                        self.log(f"  ❌ {Path(local_path).name}: {e}")
                for local_path, remote_url in mapping.items():
                    rewrite_content = rewrite_content.replace(
                        f"({local_path})", f"({remote_url})"
                    )
                self.image_status_list.setVisible(False)

        system_prompt = self._build_system_prompt(mode, self.tone_combo.currentText())
        self.ai_rewriter.config.system_prompt = system_prompt

        self.log("🤖 开始改写选中区域...")
        self.status_label.setText("改写选中区域...")
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 0)
        self.btn_ai.setText("取消改写")
        self.btn_ai.setEnabled(True)
        self.btn_export.setEnabled(False)
        self.btn_copy.setEnabled(False)

        self._rewrite_gen += 1
        gen = self._rewrite_gen
        self.rewrite_worker = RewriteWorker(self.ai_rewriter, rewrite_content)
        self.rewrite_worker.finished.connect(
            lambda result, g=gen: self._on_selection_rewritten(result, full_text, start, end, g)
        )
        self.rewrite_worker.error.connect(
            lambda msg, g=gen: self._on_rewrite_error(msg, g)
        )
        self.rewrite_worker.cancelled.connect(
            lambda g=gen: self._on_rewrite_cancelled(g)
        )
        self.rewrite_worker.start()

    def _on_selection_rewritten(self, rewritten, full_text, start, end, gen):
        if gen != self._rewrite_gen:
            return
        if self.rewrite_worker.isInterruptionRequested():
            self._on_rewrite_cancelled()
            return
        new_full = full_text[:start] + rewritten + full_text[end:]
        self.current_content = new_full
        self.original_view.setText(new_full)
        self.rewritten_content = new_full
        self.rewritten_view.setText(rewritten)
        self.content_tabs.setTabEnabled(2, True)
        self.preview_stats.setText("📝 改写后预览")
        self.preview_render.setHtml(mistune.html(new_full))
        self.content_tabs.setCurrentIndex(1)
        self._reset_rewrite_ui()
        self.btn_export.setEnabled(True)
        self.btn_copy.setEnabled(True)
        self.btn_multi_publish.setEnabled(True)
        self._save_draft(new_full)
        self.log("✅ 选中区域改写完成，已替换回原文")

    def _is_rewriting(self):
        return hasattr(self, "rewrite_worker") and self.rewrite_worker.isRunning()

    def _cancel_rewrite(self):
        self.rewrite_worker.cancel()
        self.rewrite_worker.wait(5000)
        self.log("⏹️ AI 改写已取消")

    def _on_rewrite_finished(self, result, gen):
        if gen != self._rewrite_gen:
            return
        self.rewritten_content = result
        self.rewritten_view.setText(result)
        self.content_tabs.setTabEnabled(2, True)

        self.preview_stats.setText("📝 改写后预览")
        self.preview_render.setHtml(mistune.html(result))
        self.content_tabs.setCurrentIndex(1)

        self._reset_rewrite_ui()
        self.btn_export.setEnabled(True)
        self.btn_copy.setEnabled(True)
        self.btn_multi_publish.setEnabled(True)

        self._save_draft(result)
        self.log("✅ AI 改写完成")

    def _on_rewrite_error(self, error_msg, gen):
        if gen != self._rewrite_gen:
            return
        self._reset_rewrite_ui()

        QMessageBox.critical(self, "AI 改写失败", f"改写出错:\n{error_msg}")
        self.log(f"❌ AI 改写失败: {error_msg}")

    def _on_rewrite_cancelled(self, gen):
        if gen != self._rewrite_gen:
            return
        self._reset_rewrite_ui()
        self.log("⏹️ AI 改写已取消")

    def _reset_rewrite_ui(self):
        self.progress_bar.setVisible(False)
        self.progress_bar.setRange(0, 100)
        self.status_label.setText("就绪")
        self.btn_ai.setText("AI 改写")

    def _save_draft(self, content=None):
        from datetime import datetime
        content = content or self.rewritten_content or self.current_content
        if not content:
            return
        ts = datetime.now().strftime("%H:%M")
        v = len(self.drafts) + 1
        self.drafts.append({"v": v, "content": content, "ts": ts})
        self._update_draft_combo()
        self.draft_combo.setCurrentIndex(len(self.drafts) - 1)
        self.log(f"📝 草稿 v{v}已保存 ({ts})")

    def _update_draft_combo(self):
        self.draft_combo.clear()
        if not self.drafts:
            self.draft_combo.setEnabled(False)
            self.btn_restore_draft.setEnabled(False)
            return
        self.draft_combo.setEnabled(True)
        self.btn_restore_draft.setEnabled(True)
        for d in self.drafts:
            preview = d["content"][:40].replace("\n", " ").strip()
            self.draft_combo.addItem(f"v{d['v']} ({d['ts']}) — {preview}...", d["v"])

    def _switch_draft(self):
        idx = self.draft_combo.currentIndex()
        if idx < 0 or idx >= len(self.drafts):
            return
        draft = self.drafts[idx]
        self.rewritten_content = draft["content"]
        self.rewritten_view.setText(draft["content"])
        self.content_tabs.setTabEnabled(2, True)
        self.content_tabs.setCurrentIndex(2)
        self.btn_export.setEnabled(True)
        self.btn_copy.setEnabled(True)
        self.btn_multi_publish.setEnabled(True)
        self.log(f"📂 已恢复草稿 v{draft['v']} ({draft['ts']})")

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

    def _set_image_status(self, img_path: str, text: str):
        for i in range(self.image_status_list.count()):
            item = self.image_status_list.item(i)
            if item and item.data(Qt.UserRole) == img_path:
                item.setText(text)
                break

    def _build_system_prompt(self, mode: str, tone: str = "技术博主风") -> str:
        custom_prompt = self.settings.get("ai_custom_prompt", "").strip()
        use_custom = self.settings.get("ai_use_custom_prompt", False)
        if use_custom and custom_prompt:
            img_rules = {
                "alt": (
                    "\n\n图片处理：\n"
                    "- 对于笔记中的图片 ![](path)：\n"
                    "  - 根据上下文生成有意义的 alt 描述文本\n"
                    "  - **删除括号中的路径**，只保留 ![]()\n"
                    "  - 如果无法推断内容，标注为 ![相关截图]"
                ),
                "upload": (
                    "\n\n图片处理：\n"
                    "- 对于笔记中的图片 ![](url)：\n"
                    "  - **保留 URL 不变**，不要删除或修改括号中的地址\n"
                    "  - 根据上下文优化 alt 描述文本"
                ),
                "keep": (
                    "\n\n图片处理：\n"
                    "- **不要修改任何图片标记**，保持原样不变"
                ),
            }
            return custom_prompt + img_rules.get(mode, img_rules["alt"])
        tone_prompts = {
            "技术博主风": (
                "你是一位CSDN技术博主，请将下面的笔记内容改写成CSDN博客风格：\n\n"
                "要求：\n"
                "1. 保持技术准确性，不要编造不存在的功能\n"
                "2. 语气专业但不枯燥，可以加入个人经验分享\n"
                "3. 为长段落添加小标题分隔，提升可读性\n"
                "4. **代码块、表格保持原样，不要修改其中的内容**\n"
                "5. 输出格式为 Markdown"
            ),
            "学生笔记风": (
                "你是一名计算机专业的大学生。请将下面的笔记内容改写成一篇个人博客风格的技术文章。\n\n"
                "要求：\n"
                "1. 保持技术准确性\n"
                "2. 语气像学生在学习和实践中写的记录分享，可以使用'我最近在学…'、'踩了个坑…'、'终于搞懂了…'这类真实个人表达\n"
                "3. 语气亲切自然，不需要太过正式\n"
                "4. 为长段落添加小标题分隔\n"
                "5. **代码块、表格保持原样，不要修改其中的内容**\n"
                "6. 输出格式为 Markdown"
            ),
            "教程风": (
                "你是一位技术教程作者。请将下面的笔记内容改写成一篇手把手教学风格的技术教程。\n\n"
                "要求：\n"
                "1. 保持技术准确性\n"
                "2. 步骤清晰、循序渐进，适合初学者跟着操作\n"
                "3. 可以在步骤中加入'接下来我们…'、'运行这个命令后你会看到…'这类引导语\n"
                "4. 为长段落添加小标题分隔\n"
                "5. **代码块、表格保持原样，不要修改其中的内容**\n"
                "6. 输出格式为 Markdown"
            ),
            "轻松口语化": (
                "请将下面的笔记内容改写成一篇轻松的技术分享，风格像在跟朋友聊天。\n\n"
                "要求：\n"
                "1. 保持技术准确性\n"
                "2. 语气轻松随意，可以用'我跟你说'、'真的绝了'、'懂的都懂'这类口语化表达\n"
                "3. 不需要太正式的结构\n"
                "4. **代码块、表格保持原样，不要修改其中的内容**\n"
                "5. 输出格式为 Markdown"
            ),
        }

        if tone == "自定义..." and self._custom_tone_text:
            base = self._custom_tone_text
        else:
            base = tone_prompts.get(tone, tone_prompts["技术博主风"])

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

    def _update_all_publisher_status(self):
        for p in get_publishers():
            label = self._pub_status_labels.get(p.name)
            btn = self._pub_login_btns.get(p.name)
            if label:
                label.setText("✅ 已登录" if p.is_logged_in() else "❌ 未登录")
            if btn:
                btn.setText("切换账号" if p.is_logged_in() else "登录")

    def _publisher_login(self, name: str):
        p = get_publisher(name)
        if not p:
            return
        if p.is_logged_in():
            reply = QMessageBox.question(
                self, f"{name} 登录",
                f"已登录 {name}，是否退出并重新登录？",
                QMessageBox.Yes | QMessageBox.No
            )
            if reply != QMessageBox.Yes:
                return
            p.logout()
        success = p.login(self)
        self._update_all_publisher_status()
        if success:
            self.log(f"🔑 {name} 登录成功")

    def _open_publish_dialog(self):
        content = self.rewritten_view.toPlainText() or self.current_content
        if not content:
            QMessageBox.information(self, "提示", "没有可发布的内容")
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

        dlg = PublishDialog(self, content, default_title)
        dlg.exec()

    def _embed_images_base64(self, markdown: str) -> str:
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


class PublishDialog(QDialog):
    def __init__(self, parent, content: str, default_title: str):
        super().__init__(parent)
        self.parent = parent
        self.content = content
        self.setWindowTitle("多平台发布管理器")
        self.resize(680, 560)

        layout = QVBoxLayout(self)

        top_layout = QHBoxLayout()
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)

        left_layout.addWidget(QLabel("选择发布平台:"))
        self._platform_checks = {}
        for p in get_publishers():
            cb = QCheckBox(f"{p.name}")
            cb.setChecked(p.is_logged_in())
            cb.setEnabled(p.is_logged_in())
            left_layout.addWidget(cb)
            self._platform_checks[p.name] = cb

        self._login_hint = QLabel("")
        self._login_hint.setWordWrap(True)
        left_layout.addWidget(self._login_hint)
        left_layout.addStretch()

        right_widget = QWidget()
        right_layout = QFormLayout(right_widget)

        self.title_edit = QLineEdit(default_title)
        right_layout.addRow("标题:", self.title_edit)

        self.tags_edit = QLineEdit("技术")
        self.tags_edit.setPlaceholderText("多个标签用逗号分隔")
        right_layout.addRow("标签:", self.tags_edit)

        self.categories_edit = QLineEdit()
        self.categories_edit.setPlaceholderText("可选")
        right_layout.addRow("分类:", self.categories_edit)

        self.type_combo = QComboBox()
        self.type_combo.addItems(["原创", "转载", "翻译"])
        right_layout.addRow("类型:", self.type_combo)

        self.base64_check = QCheckBox("将图片转为 base64 嵌入（体积大但 100% 可靠）")
        right_layout.addRow(self.base64_check)

        self.draft_check = QCheckBox("保存为草稿（不发布）")
        right_layout.addRow(self.draft_check)

        self.parallel_check = QCheckBox("并行发布（串行默认）")
        right_layout.addRow(self.parallel_check)

        top_layout.addWidget(left_widget, 1)
        top_layout.addWidget(right_widget, 2)
        layout.addLayout(top_layout)

        self.log_view = QTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setMaximumHeight(150)
        layout.addWidget(QLabel("发布日志:"))
        layout.addWidget(self.log_view)

        btn_layout = QHBoxLayout()
        self.publish_btn = QPushButton("发布")
        self.publish_btn.setObjectName("primaryBtn")
        self.publish_btn.clicked.connect(self._do_publish)
        self.close_btn = QPushButton("关闭")
        self.close_btn.clicked.connect(self.close)
        btn_layout.addStretch()
        btn_layout.addWidget(self.publish_btn)
        btn_layout.addWidget(self.close_btn)
        layout.addLayout(btn_layout)

    def _log(self, msg: str):
        from datetime import datetime
        ts = datetime.now().strftime("%H:%M:%S")
        self.log_view.append(f"[{ts}] {msg}")
        QApplication.processEvents()

    def _do_publish(self):
        title = self.title_edit.text().strip()
        if not title:
            QMessageBox.warning(self, "提示", "请输入标题")
            return

        content = self.content
        tags = self.tags_edit.text().strip()
        categories = self.categories_edit.text().strip()
        type_map = {"原创": "original", "转载": "reprint", "翻译": "translate"}
        article_type = type_map.get(self.type_combo.currentText(), "original")
        is_draft = self.draft_check.isChecked()
        use_base64 = self.base64_check.isChecked()

        if use_base64:
            self._log("🖼️ 正在将图片转为 base64...")
            QApplication.processEvents()
            content = self.parent._embed_images_base64(content)

        checked_platforms = [
            name for name, cb in self._platform_checks.items()
            if cb.isChecked()
        ]
        if not checked_platforms:
            QMessageBox.warning(self, "提示", "请至少选择一个已登录的平台")
            return

        parallel = self.parallel_check.isChecked()
        success_count = 0
        fail_count = 0

        self.publish_btn.setEnabled(False)

        if parallel:
            from concurrent.futures import ThreadPoolExecutor, as_completed
            futures = {}
            with ThreadPoolExecutor(max_workers=len(checked_platforms)) as executor:
                for name in checked_platforms:
                    p = get_publisher(name)
                    adapted = Exporter.adapt_for(name, content)
                    self._log(f"📤 正在发布到 {name}...")
                    future = executor.submit(
                        p.publish, title=title, content=adapted,
                        tags=tags, categories=categories,
                        article_type=article_type, draft=is_draft,
                    )
                    futures[future] = name

                for future in as_completed(futures):
                    name = futures[future]
                    try:
                        result = future.result()
                        if result.success:
                            success_count += 1
                            self._log(f"✅ {name} 发布成功: {result.url}")
                        else:
                            fail_count += 1
                            self._log(f"❌ {name} 发布失败: {result.error}")
                    except Exception as e:
                        fail_count += 1
                        self._log(f"❌ {name} 异常: {e}")
        else:
            for name in checked_platforms:
                p = get_publisher(name)
                adapted = Exporter.adapt_for(name, content)
                self._log(f"📤 正在发布到 {name}...")
                QApplication.processEvents()
                try:
                    result = p.publish(
                        title=title, content=adapted,
                        tags=tags, categories=categories,
                        article_type=article_type, draft=is_draft,
                    )
                    if result.success:
                        success_count += 1
                        self._log(f"✅ {name} 发布成功: {result.url}")
                    else:
                        fail_count += 1
                        self._log(f"❌ {name} 发布失败: {result.error}")
                except Exception as e:
                    fail_count += 1
                    self._log(f"❌ {name} 异常: {e}")
                QApplication.processEvents()

        self.publish_btn.setEnabled(True)
        summary = f"✅ {success_count} 成功，❌ {fail_count} 失败"
        QMessageBox.information(self, "发布完成", summary)
        self._log(f"📊 发布完成: {summary}")
        if success_count > 0:
            self.parent.status_label.setText("就绪")
