import time
from pathlib import Path

from PySide6.QtCore import Qt, QThread, Signal, QUrl, QByteArray, QTimer
from PySide6.QtGui import QAction, QDragEnterEvent, QDropEvent, QFont, QDesktopServices, QPixmap, QPainter, QIcon, QShortcut, QKeySequence
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout,
    QSplitter, QListWidget, QListWidgetItem, QAbstractItemView,
    QTabWidget, QTextEdit, QTextBrowser, QToolBar, QStatusBar,
    QLabel, QPushButton, QFileDialog, QMessageBox, QProgressBar,
    QDialog, QLineEdit, QComboBox, QFormLayout, QDialogButtonBox,
    QGroupBox, QSpinBox, QDoubleSpinBox, QHBoxLayout, QFrame,
    QCheckBox, QPlainTextEdit, QStackedWidget,
)

from PySide6.QtSvg import QSvgRenderer

import mistune

from parser import parse_markdown
from settings import Settings
from ai_rewriter import AIRewriter, RewriteConfig
from exporter import Exporter
from image_uploader import upload_images
from icons import get as get_icon, set_color as set_icon_color
from theme import build_stylesheet, get_tokens
from version import VERSION
from publishers import init_publishers, get_publishers, get_publisher
from publishers.base import PublishResult


class UpdateChecker(QThread):
    update_available = Signal(str, str)

    def run(self):
        try:
            import http_client
            resp = http_client.get(
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
    chunk = Signal(str)

    def __init__(self, rewriter, content, stream: bool = True):
        super().__init__()
        self.rewriter = rewriter
        self.content = content
        self.stream = stream

    def cancel(self):
        self.rewriter.cancel()
        self.requestInterruption()

    def run(self):
        try:
            if self.stream:
                result = self.rewriter.rewrite_stream(
                    self.content, on_chunk=self.chunk.emit
                )
            else:
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


class ImageUploadWorker(QThread):
    image_status = Signal(str, str)
    finished = Signal(dict)

    def __init__(self, local_images):
        super().__init__()
        self.local_images = local_images

    def run(self):
        from image_uploader import upload_image as _upload_one
        from pathlib import Path
        mapping = {}
        for path in self.local_images:
            if self.isInterruptionRequested():
                break
            try:
                self.image_status.emit(path, "⏳ 上传中...")
                url = _upload_one(path)
                mapping[path] = url
                self.image_status.emit(path, f"✅ {Path(path).name}")
            except Exception as e:
                self.image_status.emit(path, f"❌ {Path(path).name}: {e}")
        self.finished.emit(mapping)  # incomplete mapping is fine


class PublishHistoryDialog(QDialog):
    def __init__(self, parent, history):
        super().__init__(parent)
        self.setWindowTitle("发布历史")
        self.resize(560, 420)
        layout = QVBoxLayout(self)

        self.list = QListWidget()
        layout.addWidget(self.list, 1)

        btn_row = QHBoxLayout()
        open_btn = QPushButton("打开链接")
        open_btn.setObjectName("secondaryBtn")
        open_btn.clicked.connect(self._open)
        clear_btn = QPushButton("清空历史")
        clear_btn.setObjectName("secondaryBtn")
        clear_btn.clicked.connect(self._clear)
        close_btn = QPushButton("关闭")
        close_btn.clicked.connect(self.accept)
        btn_row.addWidget(open_btn)
        btn_row.addWidget(clear_btn)
        btn_row.addStretch()
        btn_row.addWidget(close_btn)
        layout.addLayout(btn_row)

        self._populate(history)

    def _populate(self, history):
        self.list.clear()
        if not history:
            self.list.addItem("（暂无发布历史）")
            return
        for rec in history:
            item = QListWidgetItem(
                f"{rec.get('time','')}  ·  {rec.get('platform','')}  ·  {rec.get('title','')}"
            )
            item.setData(Qt.UserRole, rec.get("url", ""))
            self.list.addItem(item)

    def _open(self):
        item = self.list.currentItem()
        if not item:
            return
        url = item.data(Qt.UserRole)
        if url:
            QDesktopServices.openUrl(QUrl(url))

    def _clear(self):
        self.parent().settings.set("publish_history", [])
        self._populate([])


ACCOUNT_KEYS = {
    "CSDN": ["csdn_cookies"],
    "掘金": ["juejin_cookies"],
    "博客园": ["cnblogs_username", "cnblogs_api_key", "cnblogs_blog_id"],
}


class AccountManagerDialog(QDialog):
    def __init__(self, parent, focus_platform=None):
        super().__init__(parent)
        self.parent = parent
        self.settings = parent.settings
        self.setWindowTitle("账号管理")
        self.resize(660, 470)

        layout = QVBoxLayout(self)
        tip = QLabel("为每个平台保存多个账号，一键切换（登录状态会随账号切换）。")
        tip.setWordWrap(True)
        layout.addWidget(tip)

        self._combos = {}
        for platform in ACCOUNT_KEYS:
            group = QGroupBox(platform)
            gl = QHBoxLayout(group)
            combo = QComboBox()
            combo.setMinimumWidth(240)
            combo.setSizeAdjustPolicy(QComboBox.AdjustToContents)
            self._combos[platform] = combo
            gl.addWidget(combo, 1)

            save_btn = QPushButton("保存当前")
            save_btn.setObjectName("secondaryBtn")
            save_btn.clicked.connect(lambda _=False, p=platform: self._save_current(p))
            gl.addWidget(save_btn)

            switch_btn = QPushButton("切换")
            switch_btn.setObjectName("secondaryBtn")
            switch_btn.clicked.connect(lambda _=False, p=platform: self._switch(p))
            gl.addWidget(switch_btn)

            del_btn = QPushButton("删除")
            del_btn.setObjectName("draftBtn")
            del_btn.clicked.connect(lambda _=False, p=platform: self._delete(p))
            gl.addWidget(del_btn)

            layout.addWidget(group)
            self._reload(platform)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        close_btn = QPushButton("关闭")
        close_btn.clicked.connect(self.accept)
        btn_row.addWidget(close_btn)
        layout.addLayout(btn_row)

    def _accounts(self, platform):
        return list((self.settings.get("accounts") or {}).get(platform, []))

    def _set_accounts(self, platform, items):
        accounts = dict(self.settings.get("accounts") or {})
        accounts[platform] = items
        self.settings.set("accounts", accounts)

    def _reload(self, platform):
        combo = self._combos[platform]
        combo.clear()
        combo.addItem(f"当前登录：{self._active_label(platform)}", -1)
        for i, acc in enumerate(self._accounts(platform)):
            combo.addItem(f"已保存：{acc.get('label', f'账号{i + 1}')}", i)

    def _active_label(self, platform):
        if platform == "博客园":
            return self.settings.get("cnblogs_username") or "(未配置)"
        raw = self.settings.get(ACCOUNT_KEYS[platform][0]) or ""
        if not raw:
            return "(未登录)"
        try:
            import json as _json
            cookies = _json.loads(raw)
            for key in ("UserName", "UN", "UserNick"):
                if cookies.get(key):
                    return str(cookies[key])
        except Exception:
            pass
        return "(已登录)"

    def _save_current(self, platform):
        from PySide6.QtWidgets import QInputDialog, QLineEdit
        data = {k: self.settings.get(k) for k in ACCOUNT_KEYS[platform]}
        if not any(data.values()):
            QMessageBox.information(self, "提示", f"{platform} 当前未登录，无法保存")
            return
        label, ok = QInputDialog.getText(
            self, "保存账号", "账号备注名:", QLineEdit.Normal, self._active_label(platform)
        )
        if not ok or not label.strip():
            return
        items = self._accounts(platform)
        items.append({"label": label.strip(), "data": data})
        self._set_accounts(platform, items)
        self._reload(platform)
        QMessageBox.information(self, "已保存", f"已保存账号：{label.strip()}")

    def _switch(self, platform):
        idx = self._combos[platform].currentData()
        items = self._accounts(platform)
        if idx is None or idx < 0 or idx >= len(items):
            QMessageBox.information(self, "提示", "请在下拉框中选择一个已保存账号")
            return
        data = items[idx].get("data", {})
        for k in ACCOUNT_KEYS[platform]:
            self.settings.set(k, data.get(k, ""))
        init_publishers(self.settings)
        self.parent._update_all_publisher_status()
        self.parent.log(f"🔁 已切换 {platform} 账号：{items[idx].get('label')}")
        self._reload(platform)
        QMessageBox.information(self, "已切换", f"{platform} 已切换到：{items[idx].get('label')}")

    def _delete(self, platform):
        idx = self._combos[platform].currentData()
        items = self._accounts(platform)
        if idx is None or idx < 0 or idx >= len(items):
            QMessageBox.information(self, "提示", "请在下拉框中选择一个已保存账号")
            return
        label = items[idx].get("label")
        if QMessageBox.question(self, "确认删除", f"删除账号「{label}」？") != QMessageBox.Yes:
            return
        items.pop(idx)
        self._set_accounts(platform, items)
        self._reload(platform)


class OnboardingDialog(QDialog):
    def __init__(self, parent):
        super().__init__(parent)
        self.setWindowTitle("欢迎使用 Blog Compiler")
        self.resize(560, 420)

        layout = QVBoxLayout(self)
        self.stack = QStackedWidget()
        layout.addWidget(self.stack, 1)

        self.stack.addWidget(self._page(
            "👋 欢迎使用 Blog Compiler",
            "把 Typora / Markdown 笔记，一步变成 CSDN / 掘金 / 博客园的博客。\n\n"
            "读 → AI 改写 → 图片上传 → 一键发布。",
        ))
        self.stack.addWidget(self._page(
            "第一步：配置 AI",
            "在「设置」中填入 API Key 和模型（支持 OpenAI / DeepSeek / 通义 / 智谱等）。\n"
            "没有 API Key 也可以只用图片上传与发布功能。",
            button=("打开设置", self._open_settings),
        ))
        self.stack.addWidget(self._page(
            "第二步：登录发布平台",
            "在主界面右侧「多平台发布」卡片中，点击各平台的「登录」按钮扫码登录。\n\n"
            "登录状态会自动保存，下次启动免登录。",
        ))
        self.stack.addWidget(self._page(
            "准备就绪 🚀",
            "把 .md 文件拖入左侧列表即可开始。\n\n小技巧：按 Ctrl+K 打开命令面板。",
        ))

        nav = QHBoxLayout()
        self.skip_btn = QPushButton("跳过")
        self.skip_btn.setObjectName("secondaryBtn")
        self.skip_btn.clicked.connect(self.accept)
        self.back_btn = QPushButton("上一步")
        self.back_btn.setObjectName("secondaryBtn")
        self.back_btn.clicked.connect(self._back)
        self.next_btn = QPushButton("下一步")
        self.next_btn.setObjectName("primaryBtn")
        self.next_btn.clicked.connect(self._next)
        nav.addWidget(self.skip_btn)
        nav.addStretch()
        nav.addWidget(self.back_btn)
        nav.addWidget(self.next_btn)
        layout.addLayout(nav)

        self._update_nav()

    def _page(self, title, desc, button=None):
        page = QWidget()
        lay = QVBoxLayout(page)
        t = QLabel(title)
        t.setObjectName("onboardTitle")
        lay.addWidget(t)
        d = QLabel(desc)
        d.setWordWrap(True)
        lay.addWidget(d)
        if button:
            btn = QPushButton(button[0])
            btn.setObjectName("secondaryBtn")
            btn.clicked.connect(button[1])
            lay.addWidget(btn)
        lay.addStretch()
        return page

    def _open_settings(self):
        parent = self.parent()
        if parent is not None:
            parent._show_settings()

    def _update_nav(self):
        idx = self.stack.currentIndex()
        self.back_btn.setEnabled(idx > 0)
        self.next_btn.setText("完成" if idx == self.stack.count() - 1 else "下一步")

    def _back(self):
        self.stack.setCurrentIndex(max(0, self.stack.currentIndex() - 1))
        self._update_nav()

    def _next(self):
        idx = self.stack.currentIndex()
        if idx >= self.stack.count() - 1:
            self.accept()
            return
        self.stack.setCurrentIndex(idx + 1)
        self._update_nav()


class CommandPalette(QDialog):
    def __init__(self, parent, commands):
        super().__init__(parent)
        self._commands = commands
        self.setWindowTitle("命令面板")
        self.resize(460, 340)

        layout = QVBoxLayout(self)
        self.input = QLineEdit()
        self.input.setPlaceholderText("输入命令...（Enter 执行）")
        layout.addWidget(self.input)

        self.list = QListWidget()
        layout.addWidget(self.list, 1)

        self.input.textChanged.connect(self._filter)
        self.input.returnPressed.connect(self._run_current)
        self.list.itemActivated.connect(lambda _: self._run_current())
        self.list.itemClicked.connect(lambda _: self._run_current())

        self._filter("")
        self.input.setFocus()

    def _filter(self, text):
        text = text.strip().lower()
        self.list.clear()
        for title, _ in self._commands:
            if not text or text in title.lower():
                self.list.addItem(title)
        if self.list.count():
            self.list.setCurrentRow(0)

    def _run_current(self):
        item = self.list.currentItem()
        if not item:
            return
        title = item.text()
        for t, fn in self._commands:
            if t == title:
                self.close()
                fn()
                return


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
        init_publishers(self.settings)
        self._setup_ui()
        self._custom_tone_text = ""
        self._restore_ai_settings()
        self._apply_settings()
        self._update_all_publisher_status()
        self._check_for_updates()

        if not self.settings.get("onboarding_done", False):
            QTimer.singleShot(400, self._show_onboarding)

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

    def _show_onboarding(self):
        dlg = OnboardingDialog(self)
        dlg.exec()
        self.settings.set("onboarding_done", True)

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
        self.file_list.itemClicked.connect(self._on_file_selected)

        self.file_empty = QLabel("拖入 .md 文件\n或点击上方「添加文件」")
        self.file_empty.setObjectName("emptyState")
        self.file_empty.setAlignment(Qt.AlignCenter)
        self.file_empty.setWordWrap(True)

        self.file_stack = QStackedWidget()
        self.file_stack.setObjectName("fileStack")
        self.file_stack.addWidget(self.file_empty)
        self.file_stack.addWidget(self.file_list)
        self.file_stack.setCurrentIndex(0)

        self.file_panel = QWidget()
        self.file_panel.setObjectName("filePanel")
        fp_layout = QVBoxLayout(self.file_panel)
        fp_layout.setContentsMargins(0, 0, 0, 0)
        fp_layout.setSpacing(0)
        fp_layout.addWidget(self.file_stack)
        self.file_panel.setMinimumWidth(200)
        self.file_panel.setMaximumWidth(350)

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
            status = QLabel("❌ 未登录")
            status.setObjectName(f"{p.name}Status")
            self._pub_status_labels[p.name] = status

            head = QHBoxLayout()
            head.setSpacing(6)
            name_label = QLabel(f"{p.name}")
            name_label.setObjectName("pubName")
            head.addWidget(name_label)
            head.addWidget(status)
            head.addStretch()
            cl_pub.addLayout(head)

            btns = QHBoxLayout()
            btns.setSpacing(6)
            login_btn = QPushButton("登录")
            login_btn.setObjectName("secondaryBtn")
            login_btn.clicked.connect(lambda checked, name=p.name: self._publisher_login(name))
            self._pub_login_btns[p.name] = login_btn
            btns.addWidget(login_btn, 1)

            acct_btn = QPushButton("账号管理")
            acct_btn.setObjectName("draftBtn")
            acct_btn.setToolTip("多账号管理")
            acct_btn.clicked.connect(
                lambda checked, name=p.name: self._show_account_manager(name)
            )
            btns.addWidget(acct_btn, 1)
            cl_pub.addLayout(btns)

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

        self.inspector = right_panel
        self.inspector.setMinimumWidth(240)
        self.inspector.setMaximumWidth(420)

        splitter.addWidget(self.file_panel)
        splitter.addWidget(self.content_tabs)
        splitter.addWidget(self.inspector)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 4)
        splitter.setStretchFactor(2, 1)
        self.splitter = splitter

        self._build_nav_rail()

        body = QWidget()
        body_layout = QHBoxLayout(body)
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(0)
        body_layout.addWidget(self.nav_rail)
        body_layout.addWidget(splitter, 1)

        main_layout.addWidget(body, 1)

        self.inspector.setVisible(False)

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
        self._setup_shortcuts()

    def _setup_shortcuts(self):
        QShortcut(QKeySequence("Ctrl+O"), self, self._add_files)
        QShortcut(QKeySequence("Ctrl+Return"), self, self._ai_rewrite)
        QShortcut(QKeySequence("Ctrl+K"), self, self._show_command_palette)
        QShortcut(QKeySequence("Ctrl+,"), self, self._show_settings)
        QShortcut(QKeySequence("Ctrl+P"), self, self._open_publish_dialog)

    def _build_nav_rail(self):
        self.nav_rail = QFrame()
        self.nav_rail.setObjectName("navRail")
        self.nav_rail.setFixedWidth(52)
        rl = QVBoxLayout(self.nav_rail)
        rl.setContentsMargins(6, 10, 6, 10)
        rl.setSpacing(6)

        def _rail(icon_name, tooltip, slot, checkable=False, checked=False):
            b = QPushButton()
            b.setIcon(get_icon(icon_name))
            b.setObjectName("railBtn")
            b.setToolTip(tooltip)
            b.setCheckable(checkable)
            if checkable:
                b.setChecked(checked)
            b.clicked.connect(slot)
            rl.addWidget(b)
            return b

        self.rail_file = _rail(
            "file", "文件列表", self._toggle_file_panel, checkable=True, checked=True
        )
        self.rail_rewrite = _rail(
            "ai", "改写检查器", self._toggle_inspector, checkable=True
        )
        self.rail_image = _rail(
            "image", "图片处理", self._toggle_inspector, checkable=True
        )
        self.rail_history = _rail("history", "发布历史", self._show_publish_history)
        self.rail_publish = _rail("publish", "多平台发布", self._open_publish_dialog)
        rl.addStretch()
        self.rail_settings = _rail("settings", "设置", self._show_settings)

    def _toggle_file_panel(self):
        self.file_panel.setVisible(self.rail_file.isChecked())

    def _toggle_inspector(self):
        sender = self.sender()
        if sender is self.rail_image:
            visible = self.rail_image.isChecked()
        else:
            visible = self.rail_rewrite.isChecked()
        self.inspector.setVisible(visible)
        self.rail_rewrite.setChecked(visible)
        self.rail_image.setChecked(visible)

    def _filter_files(self, text):
        text = text.strip().lower()
        for i in range(self.file_list.count()):
            item = self.file_list.item(i)
            item.setHidden(bool(text) and text not in item.text().lower())

    def _show_command_palette(self):
        commands = [
            ("添加文件", self._add_files),
            ("清空文件列表", self._clear_files),
            ("AI 改写", self._ai_rewrite),
            ("导出文件", self._export_file),
            ("复制到剪贴板", self._export_clipboard),
            ("多平台发布", self._open_publish_dialog),
            ("发布历史", self._show_publish_history),
            ("账号管理", self._show_account_manager),
            ("切换暗色/亮色模式", lambda: self.action_dark.toggle()),
            ("设置", self._show_settings),
        ]
        dlg = CommandPalette(self, commands)
        dlg.exec()

    def _show_account_manager(self, platform=None):
        AccountManagerDialog(self, platform).exec()

    def _show_publish_history(self):
        history = self.settings.get("publish_history", []) or []
        PublishHistoryDialog(self, history).exec()

    def _build_command_bar(self):
        bar = QFrame()
        bar.setObjectName("commandBar")
        bar.setFixedHeight(48)
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(12, 0, 12, 0)
        layout.setSpacing(4)

        logo_svg = (
            '<svg viewBox="0 0 32 32" fill="none">'
            '<defs><linearGradient id="blogc" x1="0" y1="0" x2="32" y2="32" '
            'gradientUnits="userSpaceOnUse">'
            '<stop stop-color="#4F46E5"/><stop offset="1" stop-color="#06B6D4"/>'
            '</linearGradient></defs>'
            '<rect width="32" height="32" rx="8" fill="url(#blogc)"/>'
            '<text x="16" y="22" text-anchor="middle" fill="white" font-size="18" '
            'font-weight="bold" font-family="sans-serif">B</text></svg>'
        )
        logo_data = QByteArray(logo_svg.encode("utf-8"))
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
        layout.addSpacing(12)

        self.breadcrumb = QLabel("未选择文件")
        self.breadcrumb.setObjectName("breadcrumb")
        layout.addWidget(self.breadcrumb)
        layout.addSpacing(12)

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

        self.file_search = QLineEdit()
        self.file_search.setObjectName("fileSearch")
        self.file_search.setPlaceholderText("搜索文件...")
        self.file_search.setFixedWidth(150)
        self.file_search.textChanged.connect(self._filter_files)
        layout.addWidget(self.file_search)

        self.action_palette = QPushButton("Ctrl+K")
        self.action_palette.setObjectName("cmdBtn")
        self.action_palette.setToolTip("命令面板")
        self.action_palette.clicked.connect(self._show_command_palette)
        layout.addWidget(self.action_palette)

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
        self.breadcrumb.setText("未选择文件")
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
        self.breadcrumb.setText(f"文件 / {Path(filepath).name}")
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
        self._apply_theme("dark" if checked else "light")
        self.action_dark.setToolTip("切换亮色模式" if checked else "切换暗色模式")
        self.settings.set("dark_mode", checked)
        self.log("已切换暗色模式" if checked else "已切换亮色模式")

    def _apply_theme(self, theme: str):
        self._theme = theme
        tokens = get_tokens(theme)
        set_icon_color(tokens["text_secondary"])
        self.setStyleSheet(build_stylesheet(theme))
        self._refresh_icons()

    def _refresh_icons(self):
        tokens = get_tokens(getattr(self, "_theme", "dark"))
        primary = "#FFFFFF"
        secondary = tokens["text_secondary"]
        mapping = {
            "btn_ai": ("ai", primary),
            "btn_multi_publish": ("publish", primary),
            "btn_export": ("export", secondary),
            "btn_copy": ("copy", secondary),
            "action_add": ("add", secondary),
            "action_clear": ("clear", secondary),
            "action_settings": ("settings", secondary),
            "rail_file": ("file", secondary),
            "rail_rewrite": ("ai", secondary),
            "rail_image": ("image", secondary),
            "rail_history": ("history", secondary),
            "rail_publish": ("publish", secondary),
            "rail_settings": ("settings", secondary),
        }
        for attr, (name, color) in mapping.items():
            btn = getattr(self, attr, None)
            if btn is not None:
                btn.setIcon(get_icon(name, color=color))
        if hasattr(self, "action_dark"):
            dark_on = getattr(self, "_theme", "dark") == "dark"
            self.action_dark.setIcon(
                get_icon("light" if dark_on else "dark", color=secondary)
            )

    def _apply_settings(self):
        dark = self.settings.get("dark_mode", False)
        self.action_dark.setChecked(dark)
        self._apply_theme("dark" if dark else "light")

        import http_client
        http_client.set_proxy(self.settings.get("http_proxy", ""))

        import image_processor
        image_processor.configure(
            enabled=self.settings.get("image_compress", True),
            max_width=self.settings.get("image_max_width", 1600),
        )

    def _update_status(self):
        count = len(self.file_paths)
        self.file_count_label.setText(f"文件: {count}")
        self.file_stack.setCurrentIndex(1 if count else 0)

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

        model_row = QHBoxLayout()
        model_row.addWidget(self.settings_model, 1)
        self.refresh_models_btn = QPushButton("刷新模型列表")
        self.refresh_models_btn.setObjectName("secondaryBtn")
        self.refresh_models_btn.clicked.connect(self._refresh_models)
        model_row.addWidget(self.refresh_models_btn)
        ai_layout.addRow("模型:", model_row)

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

        net_group = QGroupBox("网络与图片")
        net_layout = QFormLayout(net_group)

        self.settings_proxy = QLineEdit()
        self.settings_proxy.setPlaceholderText("例如 http://127.0.0.1:7890（留空不使用代理）")
        self.settings_proxy.setText(self.settings.get("http_proxy", ""))
        net_layout.addRow("HTTP 代理:", self.settings_proxy)

        self.settings_compress = QCheckBox("上传前压缩图片（转 WebP，减小体积）")
        self.settings_compress.setChecked(self.settings.get("image_compress", True))
        net_layout.addRow(self.settings_compress)

        width_row = QHBoxLayout()
        self.settings_max_width = QSpinBox()
        self.settings_max_width.setRange(320, 4096)
        self.settings_max_width.setSingleStep(160)
        self.settings_max_width.setValue(self.settings.get("image_max_width", 1600))
        width_row.addWidget(self.settings_max_width)
        width_row.addWidget(QLabel("(超过则等比缩小)"))
        net_layout.addRow("图片最大宽度:", width_row)

        layout.addWidget(net_group)

        backup_group = QGroupBox("备份与还原")
        backup_layout = QHBoxLayout(backup_group)
        export_btn = QPushButton("导出配置")
        export_btn.setObjectName("secondaryBtn")
        export_btn.clicked.connect(self._export_config)
        import_btn = QPushButton("导入配置")
        import_btn.setObjectName("secondaryBtn")
        import_btn.clicked.connect(self._import_config)
        backup_layout.addWidget(export_btn)
        backup_layout.addWidget(import_btn)
        backup_layout.addStretch()
        layout.addWidget(backup_group)

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
        if not data:
            return
        if data.get("base"):
            self.settings_api_base.setText(data["base"])
        if data.get("value") == "custom" and data.get("base"):
            self.settings_model.setEditText("")

    def _refresh_models(self):
        api_base = self.settings_api_base.text().strip() or "https://api.openai.com/v1"
        api_key = (
            self.settings_api_key.text().strip()
            or self.settings.get_encrypted("ai_api_key")
            or ""
        )
        if not api_key:
            QMessageBox.warning(self, "提示", "请先填写 API Key")
            return

        self.refresh_models_btn.setEnabled(False)
        self.refresh_models_btn.setText("获取中...")
        QApplication.processEvents()

        err = ""
        ids = []
        try:
            ids = AIRewriter.list_models(api_base, api_key)
        except Exception as e:
            err = str(e)
        finally:
            self.refresh_models_btn.setEnabled(True)
            self.refresh_models_btn.setText("刷新模型列表")

        if not ids:
            QMessageBox.warning(
                self, "刷新失败",
                f"未能获取模型列表\nAPI 地址: {api_base}\n\n{err}",
            )
            return

        current = self.settings_model.currentText().strip()
        self.settings_model.clear()
        for mid in ids:
            self.settings_model.addItem(mid, {"label": mid, "value": mid, "base": api_base})
        if current:
            self.settings_model.setEditText(current)
        self.log(f"🔄 已获取 {len(ids)} 个模型")
        QMessageBox.information(self, "刷新成功", f"已获取 {len(ids)} 个模型")

    def _save_settings(self, dialog):
        api_key = self.settings_api_key.text().strip()
        model_text = self.settings_model.currentText().strip()
        model_data = self.settings_model.currentData()
        known_labels = {m["label"] for m in AIRewriter.supported_models()}

        if model_data and model_data.get("value") not in ("custom", ""):
            model = model_data["value"]
            api_base = self.settings_api_base.text().strip() or model_data["base"]
        else:
            if model_text and model_text not in known_labels:
                model = model_text
            else:
                model = self.settings.get("ai_model", "deepseek-v4-pro") or "deepseek-v4-pro"
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

        proxy = self.settings_proxy.text().strip()
        self.settings.set("http_proxy", proxy)
        import http_client
        http_client.set_proxy(proxy)

        self.settings.set("image_compress", self.settings_compress.isChecked())
        self.settings.set("image_max_width", self.settings_max_width.value())
        import image_processor
        image_processor.configure(
            enabled=self.settings_compress.isChecked(),
            max_width=self.settings_max_width.value(),
        )

        config = RewriteConfig(
            api_key=api_key, api_base=api_base, model=model,
            temperature=temperature, max_tokens=max_tokens,
        )
        self.ai_rewriter = AIRewriter(config)
        if self.current_content:
            self.btn_ai.setEnabled(True)

        self.log("✅ AI 设置已保存")
        dialog.accept()

    def _export_config(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "导出配置", "blog-compiler-backup.json", "JSON (*.json)"
        )
        if not path:
            return
        try:
            self.settings.export_config(path)
            QMessageBox.information(self, "导出成功", f"配置已导出到:\n{path}")
            self.log("💾 配置已导出")
        except Exception as e:
            QMessageBox.warning(self, "导出失败", str(e))

    def _import_config(self):
        path, _ = QFileDialog.getOpenFileName(self, "导入配置", "", "JSON (*.json)")
        if not path:
            return
        reply = QMessageBox.question(
            self, "确认导入", "导入将覆盖当前配置，是否继续？"
        )
        if reply != QMessageBox.Yes:
            return
        try:
            self.settings.import_config(path)
            init_publishers(self.settings)
            self._apply_settings()
            self._update_all_publisher_status()
            QMessageBox.information(
                self, "导入成功", "配置已导入，部分设置重启后生效"
            )
            self.log("📥 配置已导入")
        except Exception as e:
            QMessageBox.warning(self, "导入失败", str(e))

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
            self.btn_ai.setText("取消上传")
            self.btn_ai.setEnabled(True)
            QApplication.processEvents()
            local_images = [p for p in self.current_result.images if Path(p).exists()]
            if local_images:
                self.image_status_list.clear()
                self.image_status_list.setVisible(True)
                for local_path in local_images:
                    item = QListWidgetItem(f"⏳ {Path(local_path).name}")
                    item.setData(Qt.UserRole, local_path)
                    self.image_status_list.addItem(item)
                self._upload_worker = ImageUploadWorker(local_images)
                self._upload_worker.image_status.connect(self._set_image_status)
                self._upload_worker.finished.connect(
                    lambda m: self._on_upload_done(m, mode)
                )
                self._upload_worker.start()
                return
            else:
                self.log("🖼️ 无本地图片需上传，跳过")
            self.image_status_list.setVisible(False)

        self._start_ai_rewrite(rewrite_content, mode)

    def _on_upload_done(self, mapping, mode):
        if getattr(self, "_cancel_pending", False):
            self._cancel_pending = False
            return
        self.image_status_list.setVisible(False)
        rewrite_content = self.current_content
        for local_path, remote_url in mapping.items():
            rewrite_content = rewrite_content.replace(
                f"({local_path})", f"({remote_url})"
            )
        self.log(f"🖼️ 图片上传完成 ({len(mapping)} 张)")
        self._start_ai_rewrite(rewrite_content, mode)

    def _start_ai_rewrite(self, content, mode):
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
        self._begin_stream()
        self.rewrite_worker = RewriteWorker(self.ai_rewriter, content)
        self.rewrite_worker.chunk.connect(
            lambda t, g=gen: self._on_rewrite_chunk(t, g)
        )
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
                self.btn_ai.setText("取消上传")
                self.btn_ai.setEnabled(True)
                QApplication.processEvents()
                self._upload_worker = ImageUploadWorker(local_in_sel)
                self._upload_worker.image_status.connect(self._set_image_status)
                self._upload_worker.finished.connect(
                    lambda m: self._on_selection_upload_done(m, mode, full_text, start, end)
                )
                self._upload_worker.start()
                return
            self.image_status_list.setVisible(False)

        self._start_selection_rewrite(rewrite_content, mode, full_text, start, end)

    def _on_selection_upload_done(self, mapping, mode, full_text, start, end):
        if getattr(self, "_cancel_pending", False):
            self._cancel_pending = False
            return
        self.image_status_list.setVisible(False)
        rewrite_content = self.current_content
        for local_path, remote_url in mapping.items():
            rewrite_content = rewrite_content.replace(
                f"({local_path})", f"({remote_url})"
            )
        self.log(f"🖼️ 选中区域图片上传完成 ({len(mapping)} 张)")
        self._start_selection_rewrite(rewrite_content, mode, full_text, start, end)

    def _start_selection_rewrite(self, content, mode, full_text, start, end):
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
        self._begin_stream()
        self.rewrite_worker = RewriteWorker(self.ai_rewriter, content)
        self.rewrite_worker.chunk.connect(
            lambda t, g=gen: self._on_rewrite_chunk(t, g)
        )
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
        upload_running = hasattr(self, "_upload_worker") and self._upload_worker.isRunning()
        rewrite_running = hasattr(self, "rewrite_worker") and self.rewrite_worker.isRunning()
        return upload_running or rewrite_running

    def _cancel_rewrite(self):
        if hasattr(self, "_upload_worker") and self._upload_worker.isRunning():
            self._upload_worker.requestInterruption()
            self._upload_worker.wait(5000)
            self._cancel_pending = True
            self._reset_rewrite_ui()
            self.log("⏹️ 图片上传已取消")
            return
        self.rewrite_worker.cancel()
        self.rewrite_worker.wait(5000)
        self.log("⏹️ AI 改写已取消")

    def _begin_stream(self):
        self._stream_buffer = ""
        self._last_stream_paint = 0.0
        self.rewritten_view.clear()
        self.content_tabs.setTabEnabled(2, True)
        self.content_tabs.setCurrentIndex(2)

    def _on_rewrite_chunk(self, text, gen):
        if gen != self._rewrite_gen:
            return
        self._stream_buffer += text
        now = time.monotonic()
        if now - self._last_stream_paint >= 0.08:
            self._last_stream_paint = now
            self._flush_stream()

    def _flush_stream(self):
        self.rewritten_view.setPlainText(self._stream_buffer)
        sb = self.rewritten_view.verticalScrollBar()
        sb.setValue(sb.maximum())

    def _on_rewrite_finished(self, result, gen):
        if gen != self._rewrite_gen:
            return
        self.rewritten_content = result
        self._stream_buffer = result
        self._flush_stream()
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
            return custom_prompt
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
        img_re = _re.compile(r'!\[(.*?)\]\((.+?)(?:\s+"[^"]*")?\)')

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


class MetaWorker(QThread):
    done = Signal(dict)
    error = Signal(str)

    def __init__(self, rewriter, content):
        super().__init__()
        self.rewriter = rewriter
        self.content = content

    def run(self):
        try:
            self.done.emit(self.rewriter.generate_meta(self.content))
        except Exception as e:
            self.error.emit(str(e))


class PublishDialog(QDialog):
    def __init__(self, parent, content: str, default_title: str):
        super().__init__(parent)
        self.parent = parent
        self.content = content
        self._settings = parent.settings
        self._results = {}
        self._pub_args = None
        self.setWindowTitle("多平台发布管理器")
        self.resize(720, 660)

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
            cb.stateChanged.connect(self._on_platform_toggle)
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

        self.update_check = QCheckBox("更新已发布文章（CSDN，标题匹配时）")
        self.update_check.setToolTip(
            "勾选后，若发布历史中存在同标题的 CSDN 文章，则更新该文章而非新建"
        )
        right_layout.addRow(self.update_check)

        self.meta_btn = QPushButton("AI 生成标题/标签")
        self.meta_btn.setObjectName("secondaryBtn")
        self.meta_btn.clicked.connect(self._generate_meta)
        right_layout.addRow(self.meta_btn)

        top_layout.addWidget(left_widget, 1)
        top_layout.addWidget(right_widget, 2)
        layout.addLayout(top_layout)

        layout.addWidget(QLabel("发布结果:"))
        self.results_layout = QVBoxLayout()
        self.results_layout.setSpacing(4)
        layout.addLayout(self.results_layout)

        self.log_view = QTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setMaximumHeight(130)
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

        self._load_presets()

    # ---- presets ----
    def _apply_preset(self, preset):
        if not preset:
            return
        if preset.get("tags"):
            self.tags_edit.setText(preset["tags"])
        if preset.get("categories"):
            self.categories_edit.setText(preset["categories"])
        t = preset.get("type")
        if t:
            idx = self.type_combo.findText(t)
            if idx >= 0:
                self.type_combo.setCurrentIndex(idx)

    def _load_presets(self):
        presets = self._settings.get("publish_presets", {}) or {}
        for name, cb in self._platform_checks.items():
            if cb.isChecked():
                self._apply_preset(presets.get(name, {}))
                break

    def _save_presets(self, names):
        presets = dict(self._settings.get("publish_presets", {}) or {})
        entry = {
            "tags": self.tags_edit.text().strip(),
            "categories": self.categories_edit.text().strip(),
            "type": self.type_combo.currentText(),
        }
        for name in names:
            presets[name] = entry
        self._settings.set("publish_presets", presets)

    def _on_platform_toggle(self):
        checked = [n for n, cb in self._platform_checks.items() if cb.isChecked()]
        if len(checked) == 1:
            presets = self._settings.get("publish_presets", {}) or {}
            self._apply_preset(presets.get(checked[0], {}))

    # ---- results ----
    def _reset_results(self, names):
        while self.results_layout.count():
            item = self.results_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()
        self._results.clear()
        for name in names:
            self._add_result_row(name)

    def _add_result_row(self, name):
        row = QFrame()
        row.setObjectName("resultRow")
        rl = QHBoxLayout(row)
        rl.setContentsMargins(10, 4, 10, 4)
        status = QLabel(f"⏳ {name}: 等待发布")
        rl.addWidget(status, 1)
        link = QPushButton("打开")
        link.setObjectName("draftBtn")
        link.setEnabled(False)
        link.clicked.connect(lambda _=False, n=name: self._open_result(n))
        rl.addWidget(link)
        retry = QPushButton("重试")
        retry.setObjectName("draftBtn")
        retry.setEnabled(False)
        retry.clicked.connect(lambda _=False, n=name: self._retry(n))
        rl.addWidget(retry)
        self.results_layout.addWidget(row)
        self._results[name] = {
            "status": status, "link": link, "retry": retry, "url": ""
        }

    def _set_result(self, name, result):
        row = self._results.get(name)
        if not row:
            return
        if result.success:
            row["status"].setText(f"✅ {name}: 发布成功")
            row["url"] = result.url or ""
            row["link"].setEnabled(bool(result.url))
            row["retry"].setEnabled(True)
        else:
            row["status"].setText(f"❌ {name}: {result.error[:60]}")
            row["retry"].setEnabled(True)

    def _open_result(self, name):
        row = self._results.get(name)
        if row and row["url"]:
            QDesktopServices.openUrl(QUrl(row["url"]))

    # ---- publishing ----
    def _log(self, msg: str):
        from datetime import datetime
        ts = datetime.now().strftime("%H:%M:%S")
        self.log_view.append(f"[{ts}] {msg}")
        QApplication.processEvents()

    def _collect_args(self):
        title = self.title_edit.text().strip()
        if not title:
            QMessageBox.warning(self, "提示", "请输入标题")
            return None
        content = self.content
        if self.base64_check.isChecked():
            self._log("🖼️ 正在将图片转为 base64...")
            QApplication.processEvents()
            content = self.parent._embed_images_base64(content)
        type_map = {"原创": "original", "转载": "reprint", "翻译": "translate"}
        return {
            "title": title,
            "content": content,
            "tags": self.tags_edit.text().strip(),
            "categories": self.categories_edit.text().strip(),
            "article_type": type_map.get(self.type_combo.currentText(), "original"),
            "draft": self.draft_check.isChecked(),
        }

    def _do_publish(self):
        args = self._collect_args()
        if not args:
            return
        names = [n for n, cb in self._platform_checks.items() if cb.isChecked()]
        if not names:
            QMessageBox.warning(self, "提示", "请至少选择一个已登录的平台")
            return
        self._pub_args = args
        self._save_presets(names)
        self._reset_results(names)
        self._publish_platforms(names, self.parallel_check.isChecked())

    def _retry(self, name):
        if not self._pub_args:
            return
        if name not in self._results:
            self._add_result_row(name)
        self._results[name]["status"].setText(f"⏳ {name}: 重试中...")
        self._results[name]["retry"].setEnabled(False)
        self._publish_platforms([name], parallel=False)

    def _find_article_id(self, name, title):
        history = self._settings.get("publish_history", []) or []
        for rec in history:
            if (
                rec.get("platform") == name
                and rec.get("title") == title
                and rec.get("article_id")
            ):
                return rec["article_id"]
        return ""

    def _publish_one(self, name):
        args = self._pub_args
        p = get_publisher(name)
        adapted = Exporter.adapt_for(name, args["content"])
        article_id = ""
        if self.update_check.isChecked():
            article_id = self._find_article_id(name, args["title"])
            if article_id:
                self._log(f"♻️ {name} 将更新已发布文章 (id={article_id})")
        return p.publish(
            title=args["title"], content=adapted,
            tags=args["tags"], categories=args["categories"],
            article_type=args["article_type"], draft=args["draft"],
            article_id=article_id,
        )

    def _handle_result(self, name, result):
        if result.success:
            self._log(f"✅ {name} 发布成功: {result.url}")
            for w in getattr(result, "warnings", []) or []:
                self._log(f"⚠️ {name} 图片未转存: {w}")
            self._record_history(name, result)
        else:
            self._log(f"❌ {name} 发布失败: {result.error}")
        self._set_result(name, result)

    def _record_history(self, name, result):
        from datetime import datetime
        history = list(self._settings.get("publish_history", []) or [])
        history.insert(0, {
            "platform": name,
            "title": self._pub_args["title"] if self._pub_args else "",
            "url": result.url or "",
            "article_id": getattr(result, "article_id", "") or "",
            "time": datetime.now().strftime("%Y-%m-%d %H:%M"),
        })
        self._settings.set("publish_history", history[:50])

    def _publish_platforms(self, names, parallel):
        self.publish_btn.setEnabled(False)
        success_count = 0
        fail_count = 0

        if parallel and len(names) > 1:
            from concurrent.futures import ThreadPoolExecutor, as_completed
            futures = {}
            with ThreadPoolExecutor(max_workers=len(names)) as executor:
                for name in names:
                    self._log(f"📤 正在发布到 {name}...")
                    futures[executor.submit(self._publish_one, name)] = name
                for future in as_completed(futures):
                    name = futures[future]
                    try:
                        result = future.result()
                    except Exception as e:
                        result = PublishResult(False, name, error=str(e))
                    if result.success:
                        success_count += 1
                    else:
                        fail_count += 1
                    self._handle_result(name, result)
        else:
            for name in names:
                self._log(f"📤 正在发布到 {name}...")
                QApplication.processEvents()
                try:
                    result = self._publish_one(name)
                except Exception as e:
                    result = PublishResult(False, name, error=str(e))
                if result.success:
                    success_count += 1
                else:
                    fail_count += 1
                self._handle_result(name, result)
                QApplication.processEvents()

        self.publish_btn.setEnabled(True)
        if len(names) > 1:
            summary = f"✅ {success_count} 成功，❌ {fail_count} 失败"
            self._log(f"📊 发布完成: {summary}")
            QMessageBox.information(self, "发布完成", summary)
        if success_count > 0:
            self.parent.status_label.setText("就绪")

    # ---- AI meta ----
    def _generate_meta(self):
        rewriter = getattr(self.parent, "ai_rewriter", None)
        if not rewriter or not rewriter.config.api_key:
            QMessageBox.warning(self, "提示", "请先在设置中配置 API Key")
            return
        self.meta_btn.setEnabled(False)
        self.meta_btn.setText("生成中...")
        self._meta_worker = MetaWorker(rewriter, self.content)
        self._meta_worker.done.connect(self._on_meta_done)
        self._meta_worker.error.connect(self._on_meta_error)
        self._meta_worker.start()

    def _on_meta_done(self, meta):
        if meta.get("title"):
            self.title_edit.setText(meta["title"])
        if meta.get("tags"):
            self.tags_edit.setText(meta["tags"])
        if meta.get("summary"):
            self._log(f"📝 摘要: {meta['summary']}")
        self.meta_btn.setEnabled(True)
        self.meta_btn.setText("AI 生成标题/标签")
        self._log("✅ 已生成标题与标签")

    def _on_meta_error(self, msg):
        self.meta_btn.setEnabled(True)
        self.meta_btn.setText("AI 生成标题/标签")
        self._log(f"❌ 生成失败: {msg}")
