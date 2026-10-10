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
    QCheckBox, QPlainTextEdit, QStackedWidget, QSizePolicy,
)


def _panel_header(
    title: str, role: str = "plain", on_expand=None
) -> tuple[QFrame, QHBoxLayout, object]:
    """并排面板的标题条：左边名称，中间状态，右边「展开/还原」。

    返回 (标题条, 布局, 展开按钮)，展开按钮可能为 None。
    """
    bar = QFrame()
    # 让每个标题条带上自己的角色名，样式表据此给不同的强调色边
    bar.setObjectName("panelHeader" if role == "plain" else f"header_{role}")
    lay = QHBoxLayout(bar)
    lay.setContentsMargins(12, 6, 8, 6)
    lay.setSpacing(8)
    label = QLabel(title)
    label.setObjectName("panelTitle" if role == "plain" else f"panelTitle_{role}")
    lay.addWidget(label)
    lay.addStretch()

    expand_btn = None
    if on_expand is not None:
        expand_btn = QPushButton()
        expand_btn.setObjectName("panelBtn")
        expand_btn.setIcon(get_icon("expand", size=14))
        expand_btn.setToolTip(f"展开「{title}」占满中间区域")
        expand_btn.setFixedSize(24, 24)
        expand_btn.setCursor(Qt.PointingHandCursor)
        expand_btn.clicked.connect(on_expand)
        lay.addWidget(expand_btn)
    return bar, lay, expand_btn

from PySide6.QtSvg import QSvgRenderer

import mistune

from parser import parse_markdown
from settings import Settings
from ai_rewriter import (
    AIRewriter, RewriteConfig, DEFAULT_API_BASE, DEFAULT_MODEL, resolve_model_name,
)
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
        with self.settings.batch():
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


STEP_TITLES = [
    ("读取笔记", "导入 .md 文件"),
    ("AI 改写", "选择语气和模型"),
    ("图片处理", "上传或内嵌"),
    ("发布", "选平台填标签"),
]


class Stepper(QFrame):
    """顶部四步导航：点某一步就切换左侧的任务面板。"""

    step_clicked = Signal(int)

    def __init__(self, titles=None, parent=None):
        super().__init__(parent)
        self.setObjectName("stepper")
        self._buttons = []
        self._badges = []
        self._current = 0
        self._done: set[int] = set()

        lay = QHBoxLayout(self)
        lay.setContentsMargins(14, 10, 14, 10)
        lay.setSpacing(6)

        titles = titles or STEP_TITLES
        for index, (title, hint) in enumerate(titles):
            if index:
                arrow = QLabel("›")
                arrow.setObjectName("stepArrow")
                lay.addWidget(arrow)

            card = QPushButton()
            card.setObjectName("stepCard")
            card.setCheckable(True)
            card.setCursor(Qt.PointingHandCursor)
            card.clicked.connect(lambda _=False, i=index: self.step_clicked.emit(i))
            # QPushButton 自己的 sizeHint 只有一行高，装不下里面的两行文字，
            # 不写死高度的话内层标签会被压成 0 高度（文字被裁掉）。
            card.setFixedHeight(58)
            card.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)

            card_lay = QHBoxLayout(card)
            card_lay.setContentsMargins(10, 8, 12, 8)
            card_lay.setSpacing(10)

            badge = QLabel(str(index + 1))
            badge.setObjectName("stepBadge")
            badge.setFixedSize(24, 24)
            badge.setAlignment(Qt.AlignCenter)
            card_lay.addWidget(badge, 0, Qt.AlignVCenter)

            text_col = QVBoxLayout()
            text_col.setSpacing(1)
            name = QLabel(title)
            name.setObjectName("stepName")
            name.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
            desc = QLabel(hint)
            desc.setObjectName("stepHint")
            desc.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
            text_col.addWidget(name)
            text_col.addWidget(desc)
            card_lay.addLayout(text_col)
            card_lay.addStretch()

            lay.addWidget(card, 1)
            self._buttons.append(card)
            self._badges.append(badge)

        self.set_current(0)

    def current(self) -> int:
        return self._current

    def set_current(self, index: int):
        self._current = index
        for i, card in enumerate(self._buttons):
            card.setChecked(i == index)

    def set_done(self, index: int, done: bool = True):
        if done:
            self._done.add(index)
        else:
            self._done.discard(index)
        self._refresh_badges()

    def _refresh_badges(self):
        for i, badge in enumerate(self._badges):
            badge.setText("✓" if i in self._done else str(i + 1))
            badge.setProperty("state", "done" if i in self._done else "todo")
            badge.style().unpolish(badge)
            badge.style().polish(badge)


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
        self._custom_tone_text = ""
        self._tone_before_custom = "技术博主风"
        self._refine_mode = False
        init_publishers(self.settings)
        self._setup_ui()
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

    # ------------------------------------------------------------------ UI
    def _setup_ui(self):
        self.setWindowTitle("Blog Compiler")
        self.resize(1420, 900)

        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        self._build_command_bar()
        main_layout.addWidget(self._command_bar)

        # 四步导航：切步骤 = 换左侧任务面板
        self.stepper = Stepper()
        self.stepper.step_clicked.connect(self._go_to_step)
        main_layout.addWidget(self.stepper)

        body = QWidget()
        body_layout = QHBoxLayout(body)
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(0)
        body_layout.addWidget(self._build_file_panel())
        body_layout.addWidget(self._build_work_area(), 1)
        body_layout.addWidget(self._build_task_panel())
        main_layout.addWidget(body, 1)

        main_layout.addWidget(self._build_action_bar())

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
        self._go_to_step(0)

    def _build_file_panel(self) -> QWidget:
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

        panel = QWidget()
        panel.setObjectName("filePanel")
        lay = QVBoxLayout(panel)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        bar, bar_lay, _ = _panel_header("文档")
        self.file_counter = QLabel("")
        self.file_counter.setObjectName("panelCounter")
        bar_lay.addWidget(self.file_counter)
        lay.addWidget(bar)
        lay.addWidget(self.file_stack)

        self.file_panel = panel
        self.file_panel.setMinimumWidth(200)
        self.file_panel.setMaximumWidth(320)
        return panel

    def _build_work_area(self) -> QWidget:
        """中心区：原文 / 改写后并排，预览作为可折叠的第三栏。"""

        def _source_panel(title: str, role: str, read_only: bool):
            panel = QWidget()
            panel.setObjectName(f"panel_{role}")
            lay = QVBoxLayout(panel)
            lay.setContentsMargins(0, 0, 0, 0)
            lay.setSpacing(0)

            bar, bar_lay, expand_btn = _panel_header(
                title, role, on_expand=lambda _=False, r=role: self._toggle_panel_max(r)
            )
            counter = QLabel("")
            counter.setObjectName("panelCounter")
            bar_lay.addWidget(counter)
            lay.addWidget(bar)

            view = QTextEdit()
            view.setObjectName("editor")
            view.setReadOnly(read_only)
            view.setFont(QFont("Consolas", 10))
            lay.addWidget(view, 1)
            return panel, view, counter, expand_btn

        self.compare = QSplitter(Qt.Horizontal)
        self.compare.setObjectName("compare")
        self.compare.setHandleWidth(1)
        self.compare.setChildrenCollapsible(False)

        self.original_panel, self.original_view, self.original_counter, self.original_expand = _source_panel(
            "原文", "original", read_only=True
        )
        self.rewritten_panel, self.rewritten_view, self.rewritten_counter, self.rewritten_expand = _source_panel(
            "改写后", "rewritten", read_only=False
        )
        self.compare.addWidget(self.original_panel)
        self.compare.addWidget(self.rewritten_panel)
        self.compare.setStretchFactor(0, 1)
        self.compare.setStretchFactor(1, 1)

        self.preview_panel = QWidget()
        self.preview_panel.setObjectName("panel_preview")
        preview_layout = QVBoxLayout(self.preview_panel)
        preview_layout.setContentsMargins(0, 0, 0, 0)
        preview_layout.setSpacing(0)
        pv_bar, pv_lay, self.preview_expand = _panel_header(
            "预览", "preview", on_expand=lambda _=False: self._toggle_panel_max("preview")
        )
        self.preview_stats = QLabel("选择文件后自动生成预览")
        self.preview_stats.setObjectName("panelCounter")
        pv_lay.addWidget(self.preview_stats)
        preview_layout.addWidget(pv_bar)

        self.image_status_list = QListWidget()
        self.image_status_list.setObjectName("imageStatus")
        self.image_status_list.setMaximumHeight(100)
        self.image_status_list.setVisible(False)
        preview_layout.addWidget(self.image_status_list)

        self.preview_render = QTextBrowser()
        self.preview_render.setObjectName("previewRender")
        self.preview_render.setOpenExternalLinks(False)
        preview_layout.addWidget(self.preview_render, 1)

        self.preview_panel.setVisible(False)
        self._preview_visible = False
        self._maximized_panel = None
        self._syncing_scroll = False
        self._scroll_sync_enabled = True

        # 原文与改写后互相同步滚动，方便逐段对照
        self.original_view.verticalScrollBar().valueChanged.connect(
            lambda _=0: self._sync_scroll(self.original_view, self.rewritten_view)
        )
        self.rewritten_view.verticalScrollBar().valueChanged.connect(
            lambda _=0: self._sync_scroll(self.rewritten_view, self.original_view)
        )
        # 双击标题条也能展开/还原
        for role, panel in (("original", self.original_panel),
                            ("rewritten", self.rewritten_panel),
                            ("preview", self.preview_panel)):
            header = panel.findChild(QFrame, "panelHeader")
            if header is not None:
                header.mouseDoubleClickEvent = (
                    lambda event, r=role: self._toggle_panel_max(r)
                )
        self.compare.addWidget(self.preview_panel)
        self.compare.setStretchFactor(2, 1)
        self.compare.setSizes([1, 1, 0])
        self.content_tabs = self.compare
        return self.compare

    def _build_task_panel(self) -> QWidget:
        """左侧任务面板：四步各一页，避免把十几组控件挤在一列里。"""
        self.task_stack = QStackedWidget()
        self.task_stack.setObjectName("taskPanel")
        for builder in (
            self._build_step_read,
            self._build_step_rewrite,
            self._build_step_image,
            self._build_step_publish,
        ):
            page = QWidget()
            page.setObjectName("taskPage")
            inner = QVBoxLayout(page)
            inner.setContentsMargins(16, 14, 16, 14)
            inner.setSpacing(12)
            builder(inner)
            inner.addStretch()
            self.task_stack.addWidget(page)

        self.task_stack.setMinimumWidth(300)
        self.task_stack.setMaximumWidth(420)
        return self.task_stack

    def _build_step_read(self, lay: QVBoxLayout):
        title = QLabel("导入你的笔记")
        title.setObjectName("taskTitle")
        lay.addWidget(title)
        desc = QLabel("拖入或选择 .md 文件，程序会解析段落、代码块、表格和图片，"
                      "并按所选方式处理图片。")
        desc.setObjectName("taskDesc")
        desc.setWordWrap(True)
        lay.addWidget(desc)

        self.stats_label = QLabel("尚未选择文件")
        self.stats_label.setObjectName("statBlock")
        self.stats_label.setWordWrap(True)
        lay.addWidget(self.stats_label)

        self.stats_detail = QLabel("")
        self.stats_detail.setObjectName("statDetail")
        self.stats_detail.setWordWrap(True)
        lay.addWidget(self.stats_detail)

    def _build_step_rewrite(self, lay: QVBoxLayout):
        from PySide6.QtWidgets import QButtonGroup, QRadioButton

        title = QLabel("要改成什么风格？")
        title.setObjectName("taskTitle")
        lay.addWidget(title)
        desc = QLabel("只改文字表达，代码块、表格、图片标记都原样保留。")
        desc.setObjectName("taskDesc")
        desc.setWordWrap(True)
        lay.addWidget(desc)

        # 两种工作方式：从原文重写，或在已有结果上继续调整
        self.rewrite_mode_group = QButtonGroup(self)
        self.rb_mode_refine = QRadioButton("调整当前结果（保留已改的内容）")
        self.rb_mode_rewrite = QRadioButton("改写原文（从头生成一版）")
        self.rb_mode_refine.setChecked(True)
        self.rewrite_mode_group.addButton(self.rb_mode_refine, 1)
        self.rewrite_mode_group.addButton(self.rb_mode_rewrite, 2)
        lay.addWidget(self.rb_mode_refine)
        lay.addWidget(self.rb_mode_rewrite)

        self.refine_label = QLabel("修改意见")
        self.refine_label.setObjectName("taskLabel")
        lay.addWidget(self.refine_label)
        self.refine_input = QPlainTextEdit()
        self.refine_input.setObjectName("refineInput")
        self.refine_input.setPlaceholderText(
            "例如：第二段压短一半；补一句踩坑经验；标题再直接一点\n"
            "留空则按当前语气整篇重来"
        )
        self.refine_input.setFixedHeight(74)
        lay.addWidget(self.refine_input)

        tone_label = QLabel("语气")
        tone_label.setObjectName("taskLabel")
        lay.addWidget(tone_label)
        self.tone_combo = QComboBox()
        self.tone_combo.addItems(["技术博主风", "学生笔记风", "教程风", "轻松口语化", "自定义..."])
        # 用 activated：重复选「自定义...」也要能触发（见 _on_tone_changed 的说明）
        self.tone_combo.activated.connect(self._on_tone_changed)
        lay.addWidget(self.tone_combo)

        model_label = QLabel("使用模型")
        model_label.setObjectName("taskLabel")
        lay.addWidget(model_label)
        self.model_hint = QLabel("")
        self.model_hint.setObjectName("statDetail")
        self.model_hint.setWordWrap(True)
        lay.addWidget(self.model_hint)

        draft_label = QLabel("草稿历史")
        draft_label.setObjectName("taskLabel")
        lay.addWidget(draft_label)
        draft_row = QHBoxLayout()
        draft_row.setSpacing(6)
        self.draft_combo = QComboBox()
        self.draft_combo.setObjectName("draftCombo")
        self.draft_combo.setPlaceholderText("尚未生成草稿")
        self.draft_combo.setEnabled(False)
        draft_row.addWidget(self.draft_combo, 1)
        self.btn_restore_draft = QPushButton("恢复")
        self.btn_restore_draft.setObjectName("draftBtn")
        self.btn_restore_draft.setEnabled(False)
        self.btn_restore_draft.clicked.connect(self._switch_draft)
        draft_row.addWidget(self.btn_restore_draft)
        lay.addLayout(draft_row)

    # ---- 改写模式 --------------------------------------------------------
    def _get_rewrite_mode(self) -> str:
        return "refine" if self.rb_mode_refine.isChecked() else "rewrite"

    @staticmethod
    def _build_refine_prompt(base_prompt: str, instruction: str) -> str:
        """把「改写」指令改写成「在现有结果上继续调整」的指令。

        必须明确要求「不要重写全文」——否则模型会把整篇重新生成一遍，
        用户前几轮的调整就白做了。
        """
        instruction = (instruction or "").strip()
        if instruction:
            task = (
                f"用户对当前版本的修改意见是：\n{instruction}\n\n"
                "请只针对这个意见做修改，其余内容、段落顺序、代码块和图片标记保持完全一致。"
            )
        else:
            task = "用户没有提出具体意见，请保持内容与结构不变，仅按上述风格要求微调表达。"

        return (
            "你正在修改一篇已经成稿的文章。**不要重写全文**，"
            "只做用户要求的改动，其余部分逐字保留。\n\n"
            f"{task}\n\n"
            f"风格要求（供参考，不要因此大改内容）：\n{base_prompt}\n\n"
            "**重要**：\n"
            "1. 输出修改后的完整文章，不要只输出改动片段\n"
            "2. 代码块、表格、图片标记必须原样保留\n"
            "3. 不要添加「以下是修改后的版本」这类前后缀说明\n"
        )


    def _build_step_image(self, lay: QVBoxLayout):
        from PySide6.QtWidgets import QButtonGroup, QRadioButton

        title = QLabel("图片怎么处理？")
        title.setObjectName("taskTitle")
        lay.addWidget(title)
        desc = QLabel("CSDN 与掘金发布时还会各自上传一份到自家图床，"
                      "这里选的是改写阶段怎么对待正文里的图片。")
        desc.setObjectName("taskDesc")
        desc.setWordWrap(True)
        lay.addWidget(desc)

        self.img_mode_group = QButtonGroup(self)
        self.rb_img_alt = QRadioButton("生成 alt 文本（删掉路径）")
        self.rb_img_upload = QRadioButton("上传到 scdn.io 图床")
        self.rb_img_keep = QRadioButton("保留原路径不动")
        self.rb_img_alt.setChecked(True)
        self.img_mode_group.addButton(self.rb_img_alt, 1)
        self.img_mode_group.addButton(self.rb_img_upload, 2)
        self.img_mode_group.addButton(self.rb_img_keep, 3)
        lay.addWidget(self.rb_img_alt)
        lay.addWidget(self.rb_img_upload)
        lay.addWidget(self.rb_img_keep)

        self.image_summary = QLabel("尚未解析图片")
        self.image_summary.setObjectName("statBlock")
        self.image_summary.setWordWrap(True)
        lay.addWidget(self.image_summary)

    def _build_step_publish(self, lay: QVBoxLayout):
        title = QLabel("发到哪些平台？")
        title.setObjectName("taskTitle")
        lay.addWidget(title)
        desc = QLabel("先在下面登录，再点底部的「多平台发布」选择标签与分类。")
        desc.setObjectName("taskDesc")
        desc.setWordWrap(True)
        lay.addWidget(desc)

        self._pub_status_labels = {}
        self._pub_login_btns = {}
        self._pub_account_btns = {}
        for p in get_publishers():
            row = QHBoxLayout()
            row.setSpacing(6)
            name_label = QLabel(p.name)
            name_label.setObjectName("pubName")
            name_label.setMinimumWidth(52)
            row.addWidget(name_label)

            status = QLabel("❌ 未登录")
            status.setObjectName(f"{p.name}Status")
            self._pub_status_labels[p.name] = status
            row.addWidget(status, 1)

            login_btn = QPushButton("登录")
            login_btn.setObjectName("secondaryBtn")
            login_btn.clicked.connect(lambda _=False, name=p.name: self._publisher_login(name))
            self._pub_login_btns[p.name] = login_btn
            row.addWidget(login_btn)

            acct_btn = QPushButton("账号")
            acct_btn.setObjectName("draftBtn")
            acct_btn.setToolTip("多账号管理")
            acct_btn.clicked.connect(
                lambda _=False, name=p.name: self._show_account_manager(name)
            )
            self._pub_account_btns[p.name] = acct_btn
            row.addWidget(acct_btn)
            lay.addLayout(row)

        self.precheck_label = QLabel("")
        self.precheck_label.setObjectName("statBlock")
        self.precheck_label.setWordWrap(True)
        lay.addWidget(self.precheck_label)

    def _filter_files(self, text):
        text = text.strip().lower()
        for i in range(self.file_list.count()):
            item = self.file_list.item(i)
            item.setHidden(bool(text) and text not in item.text().lower())

    def _setup_shortcuts(self):
        QShortcut(QKeySequence("Ctrl+O"), self, self._add_files)
        QShortcut(QKeySequence("Ctrl+Return"), self, self._ai_rewrite)
        QShortcut(QKeySequence("Ctrl+K"), self, self._show_command_palette)
        QShortcut(QKeySequence("Ctrl+,"), self, self._show_settings)
        QShortcut(QKeySequence("Ctrl+P"), self, self._open_publish_dialog)
        # 展开/还原面板：Ctrl+1/2/3 对应原文/改写后/预览，Esc 退出展开
        QShortcut(QKeySequence("Ctrl+1"), self, lambda: self._toggle_panel_max("original"))
        QShortcut(QKeySequence("Ctrl+2"), self, lambda: self._toggle_panel_max("rewritten"))
        QShortcut(QKeySequence("Ctrl+3"), self, lambda: self._toggle_panel_max("preview"))
        QShortcut(QKeySequence("Ctrl+0"), self, self._restore_panels)
        QShortcut(QKeySequence("Esc"), self, self._toggle_maximized_panel)

    def _build_action_bar(self) -> QWidget:
        """常驻底栏：只放最常用的动作，不随步骤切换。"""
        bar = QFrame()
        bar.setObjectName("actionBar")
        lay = QVBoxLayout(bar)
        lay.setContentsMargins(14, 9, 14, 9)
        lay.setSpacing(8)

        self.progress_bar = QProgressBar()
        self.progress_bar.setObjectName("progressBar")
        self.progress_bar.setVisible(False)
        lay.addWidget(self.progress_bar)

        row = QHBoxLayout()
        row.setSpacing(8)

        self.btn_ai = QPushButton(" AI 改写")
        self.btn_ai.setIcon(get_icon("ai"))
        self.btn_ai.setObjectName("primaryBtn")
        self.btn_ai.setMinimumHeight(36)
        self.btn_ai.clicked.connect(self._ai_rewrite)
        self.btn_ai.setEnabled(False)
        row.addWidget(self.btn_ai, 2)

        self.btn_copy = QPushButton("复制")
        self.btn_copy.setIcon(get_icon("copy"))
        self.btn_copy.setObjectName("secondaryBtn")
        self.btn_copy.clicked.connect(self._export_clipboard)
        self.btn_copy.setEnabled(False)
        row.addWidget(self.btn_copy, 1)

        self.btn_export = QPushButton("导出")
        self.btn_export.setIcon(get_icon("export"))
        self.btn_export.setObjectName("secondaryBtn")
        self.btn_export.clicked.connect(self._export_file)
        self.btn_export.setEnabled(False)
        row.addWidget(self.btn_export, 1)

        self.btn_multi_publish = QPushButton(" 多平台发布")
        self.btn_multi_publish.setIcon(get_icon("publish"))
        self.btn_multi_publish.setObjectName("primaryBtn")
        self.btn_multi_publish.setMinimumHeight(36)
        self.btn_multi_publish.clicked.connect(self._open_publish_dialog)
        self.btn_multi_publish.setEnabled(False)
        row.addWidget(self.btn_multi_publish, 2)

        self.scroll_sync_check = QCheckBox("滚动同步")
        self.scroll_sync_check.setObjectName("syncCheck")
        self.scroll_sync_check.setToolTip(
            "左右两栏按比例同步滚动，方便逐段对照；行数不同时也能大致对上"
        )
        self.scroll_sync_check.setChecked(
            self.settings.get("scroll_sync", True)
        )
        self._scroll_sync_enabled = self.scroll_sync_check.isChecked()
        self.scroll_sync_check.toggled.connect(self._on_scroll_sync_toggled)
        row.addWidget(self.scroll_sync_check)

        lay.addLayout(row)

        self.log_view = QTextEdit()
        self.log_view.setObjectName("logView")
        self.log_view.setReadOnly(True)
        self.log_view.setFont(QFont("Consolas", 9))
        self.log_view.setFixedHeight(64)
        self.log_view.setPlaceholderText("运行日志将显示在这里")
        lay.addWidget(self.log_view)
        return bar

    def _go_to_step(self, index: int):
        """切换左侧任务面板，并让对应按钮拿到焦点。"""
        self.stepper.set_current(index)
        self.task_stack.setCurrentIndex(index)
        for i in (0, 1, 2, 3):
            if i == index:
                self.stepper.set_done(i, self._step_finished(i))
        if index == 3:
            self._update_precheck()

    def _step_finished(self, index: int) -> bool:
        if index == 0:
            return bool(self.current_content)
        if index == 1:
            return bool(self.rewritten_content)
        if index == 2:
            return bool(self.current_result and self.current_result.images)
        return bool(self.rewritten_content)

    def _update_step_states(self):
        for i in (0, 1, 2, 3):
            self.stepper.set_done(i, self._step_finished(i))

    def _update_precheck(self):
        """发布前把能本地判断的问题先摆出来，省得发出去才发现。"""
        lines = []
        title = ""
        content = self.rewritten_content or self.current_content
        for line in (content or "").splitlines():
            if line.startswith("# "):
                title = line[2:].strip()
                break

        if not title:
            lines.append("⚠ 没有找到一级标题，发布时需手动填写标题")
        elif len(title) > 30:
            lines.append(f"⚠ 标题 {len(title)} 字，部分平台建议 30 字以内")
        else:
            lines.append(f"✓ 标题 {len(title)} 字，长度合适")

        if self.current_result and self.current_result.images:
            exists = sum(1 for p in self.current_result.images if Path(p).exists())
            total = len(self.current_result.images)
            if exists == total:
                lines.append(f"✓ {total} 张图片路径均存在")
            else:
                lines.append(f"⚠ {total - exists}/{total} 张图片找不到文件")
        else:
            lines.append("· 这篇文章没有图片")

        fences = (content or "").count("```")
        if fences and fences % 2:
            lines.append("⚠ 代码块围栏数量是奇数，可能有一处没闭合")

        self.precheck_label.setText("\n".join(lines))


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
        self._update_panel_counters()
        self._update_task_panels(None)
        self._update_step_states()
        self.file_counter.setText("")
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
            self.btn_ai.setEnabled(self.ai_rewriter is not None)
            # 换文件时右侧必须清空，否则会显示上一篇的改写结果
            self.rewritten_content = ""
            self.rewritten_view.clear()
            self.btn_export.setEnabled(False)
            self.btn_copy.setEnabled(False)
            self._update_panel_counters()
            self._update_task_panels(result, Path(filepath).name)
            self._update_step_states()

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
            "rail_preview": ("preview", secondary),
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

    def _update_model_hint(self):
        """在「AI 改写」步骤里显示当前用的是哪个模型。"""
        if not hasattr(self, "model_hint"):
            return
        rewriter = getattr(self, "ai_rewriter", None)
        if rewriter is None or not rewriter.config.api_key:
            self.model_hint.setText("⚠ 尚未配置 API Key，点右上角 ⚙ 去设置")
            return
        base = (rewriter.config.api_base or "").replace("https://", "").replace("http://", "")
        base = base.rstrip("/")
        self.model_hint.setText(f"当前：{rewriter.config.model}\n接口：{base}")

    def _update_status(self):
        count = len(self.file_paths)
        self.file_count_label.setText(f"文件: {count}")
        self.file_stack.setCurrentIndex(1 if count else 0)
        if hasattr(self, "file_counter"):
            self.file_counter.setText(f"{count} 篇" if count else "")

    def _update_panel_counters(self):
        """两块并排面板各自显示字数，便于判断改写幅度。"""
        original = self.original_view.toPlainText()
        rewritten = self.rewritten_view.toPlainText()
        self.original_counter.setText(f"{len(original)} 字" if original else "")
        if rewritten:
            self.rewritten_counter.setText(f"{len(rewritten)} 字")
        else:
            self.rewritten_counter.setText("尚未改写")
        # 内容变了，步骤完成状态也跟着变
        if hasattr(self, "stepper"):
            self._update_step_states()

    def _update_task_panels(self, result, filename: str = ""):
        """把解析结果填进「读取笔记」和「图片处理」两步的面板。"""
        if result is None:
            self.stats_label.setText("尚未选择文件")
            self.stats_detail.setText("")
            self.image_summary.setText("尚未解析图片")
            return

        if not result.is_valid:
            self.stats_label.setText(f"⚠ {result.error}")
            self.stats_detail.setText("")
            self.image_summary.setText("尚未解析图片")
            return

        head = f"📄 {filename}" if filename else "📄 当前文件"
        self.stats_label.setText(
            f"{head}\n"
            f"段落 {result.paragraph_count} · 代码块 {result.code_block_count}\n"
            f"图片 {len(result.images)} · 表格 {result.table_count}"
        )

        if result.headings:
            lines = ["标题结构:"]
            for level, text in result.headings[:8]:
                lines.append(f"{'  ' * (level - 1)}H{level} {text}")
            if len(result.headings) > 8:
                lines.append(f"…及其他 {len(result.headings) - 8} 个标题")
            self.stats_detail.setText("\n".join(lines))
        else:
            self.stats_detail.setText("没有检测到标题，发布时标题需手动填写")

        if not result.images:
            self.image_summary.setText("这篇文章没有图片")
            return

        local = [p for p in result.images if Path(p).exists()]
        missing = len(result.images) - len(local)
        summary = f"共 {len(result.images)} 张图片，其中本地文件 {len(local)} 张"
        if missing:
            summary += f"\n⚠ {missing} 张路径找不到对应文件"
        self.image_summary.setText(summary)

    # ---- 面板展开 / 折叠 -------------------------------------------------
    def _panel_widgets(self) -> dict:
        return {
            "original": self.original_panel,
            "rewritten": self.rewritten_panel,
            "preview": self.preview_panel,
        }

    def _panel_buttons(self) -> dict:
        return {
            "original": self.original_expand,
            "rewritten": self.rewritten_expand,
            "preview": self.preview_expand,
        }

    def _toggle_panel_max(self, role: str):
        """把某个面板撑满中间区域；再点一次还原。"""
        if getattr(self, "_maximized_panel", None) == role:
            self._restore_panels()
        else:
            self._maximize_panel(role)

    def _maximize_panel(self, role: str):
        widgets = self._panel_widgets()
        if role not in widgets:
            return

        self._maximized_panel = role
        for name, panel in widgets.items():
            # 其它面板收成 0 宽而不是隐藏，这样分隔条还在，可以拖回来
            if name == role:
                panel.setMinimumWidth(0)
                panel.setMaximumWidth(16777215)
            else:
                panel.setMinimumWidth(0)
                panel.setMaximumWidth(0)

        total = max(self.compare.width(), 1)
        order = ["original", "rewritten", "preview"]
        sizes = [total if name == role else 0 for name in order]
        self.compare.setSizes(sizes)
        self._refresh_panel_buttons()

    def _restore_panels(self):
        self._maximized_panel = None
        for panel in self._panel_widgets().values():
            panel.setMinimumWidth(0)
            panel.setMaximumWidth(16777215)
        self.preview_panel.setVisible(self._preview_visible)
        self._relayout_compare()
        self._refresh_panel_buttons()

    def _relayout_compare(self):
        """按当前可见面板数量均分中间区域。"""
        visible = [p for p in self._panel_widgets().values() if p.isVisible()]
        if not visible:
            return
        total = max(self.compare.width(), len(visible))
        share = total // len(visible)
        order = ["original", "rewritten", "preview"]
        widgets = self._panel_widgets()
        self.compare.setSizes([
            share if widgets[name].isVisible() else 0 for name in order
        ])

    def _refresh_panel_buttons(self):
        current = getattr(self, "_maximized_panel", None)
        for role, button in self._panel_buttons().items():
            if button is None:
                continue
            expanded = current == role
            button.setIcon(get_icon("collapse" if expanded else "expand", size=14))
            title = {"original": "原文", "rewritten": "改写后", "preview": "预览"}[role]
            button.setToolTip(
                f"还原「{title}」" if expanded else f"展开「{title}」占满中间区域"
            )

    def _toggle_maximized_panel(self):
        """Esc / 快捷键：从展开状态还原。"""
        if getattr(self, "_maximized_panel", None):
            self._restore_panels()

    # ---- 双栏滚动同步 ---------------------------------------------------
    def _sync_scroll(self, source, target):
        """把 source 的滚动位置按比例同步给 target。

        按比例而不是绝对位置：原文和改写后的行数往往不同，
        绝对同步会在后面越错越远。
        """
        if getattr(self, "_syncing_scroll", False):
            return
        if not getattr(self, "_scroll_sync_enabled", True):
            return
        src_bar = source.verticalScrollBar()
        dst_bar = target.verticalScrollBar()
        src_max = src_bar.maximum()
        dst_max = dst_bar.maximum()
        if src_max <= 0 or dst_max <= 0:
            return

        self._syncing_scroll = True
        try:
            dst_bar.setValue(int(src_bar.value() / src_max * dst_max))
        finally:
            self._syncing_scroll = False

    def _on_scroll_sync_toggled(self, checked: bool):
        self._scroll_sync_enabled = checked
        self.settings.set("scroll_sync", checked)
        self.log("🔗 已开启双栏滚动同步" if checked else "🔗 已关闭双栏滚动同步")

    def _set_preview_visible(self, visible: bool):
        self._preview_visible = visible
        # 展开别的面板时，预览的显隐要等还原后再恢复
        self.preview_panel.setVisible(visible)
        if not getattr(self, "_maximized_panel", None):
            self._relayout_compare()
        self._refresh_panel_buttons()

    def toggle_preview(self):
        self._set_preview_visible(not self._preview_visible)

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
        """语气下拉框的选择处理。

        用 activated 而不是 currentTextChanged：combo 停在「自定义...」时，
        再选一次同一个条目不会发 currentTextChanged，用户就得先切走再切回来。
        activated 每次点击都会发，所以这里能稳定弹出窗口。
        处理完把当前项切回预设，避免 combo 停在「自定义...」造成状态歧义。
        """
        if text != "自定义...":
            self._tone_before_custom = text
            self.settings.set("ai_tone", text)
            return

        from PySide6.QtWidgets import QInputDialog

        prev = self.settings.get("ai_tone_custom", "")
        new_text, ok = QInputDialog.getMultiLineText(
            self, "自定义语气", "请输入 persona 描述（例如：像一位耐心的师兄在讲解）：", prev
        )

        if ok and new_text.strip():
            self._custom_tone_text = new_text.strip()
            self.settings.set("ai_tone_custom", self._custom_tone_text)
            self.settings.set("ai_tone", "自定义...")
        else:
            # 取消：回到上次选中的预设
            self.settings.set("ai_tone", self._tone_before_custom)

        self._reset_tone_combo_to(self.settings.get("ai_tone", "技术博主风"))

    def _reset_tone_combo_to(self, tone: str):
        """把下拉框复位到指定语气，期间不触发信号。"""
        target = tone if tone != "自定义..." else self._tone_before_custom
        idx = self.tone_combo.findText(target)
        if idx < 0:
            idx = self.tone_combo.findText("技术博主风")
        self.tone_combo.blockSignals(True)
        self.tone_combo.setCurrentIndex(idx)
        self.tone_combo.blockSignals(False)

    def _restore_ai_settings(self):
        api_key = self.settings.get_encrypted("ai_api_key")
        api_base = self.settings.get("ai_api_base", DEFAULT_API_BASE)
        model = self.settings.get("ai_model", DEFAULT_MODEL)
        temperature = self.settings.get("ai_temperature", 0.7)
        max_tokens = self.settings.get("ai_max_tokens", 32768)
        saved_tone = self.settings.get("ai_tone", "技术博主风")
        self._custom_tone_text = self.settings.get("ai_tone_custom", "")
        # 记住「自定义」之前用的是哪个预设，取消时要退回去
        self._tone_before_custom = (
            saved_tone if saved_tone in ("技术博主风", "学生笔记风", "教程风", "轻松口语化")
            else "技术博主风"
        )
        self._reset_tone_combo_to(saved_tone)
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
        self._update_model_hint()

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
        saved_model = self.settings.get("ai_model", DEFAULT_MODEL)
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
        model_data = self.settings_model.currentData()

        if model_data and model_data.get("value") not in ("custom", ""):
            model = model_data["value"]
            preset_base = model_data["base"]
        else:
            # 下拉框可编辑：用户可能选中预设（拿到 label）也可能手输模型名，
            # 统一交给 resolve_model_name 还原，避免把 label 当模型名发出去。
            model = resolve_model_name(self.settings_model.currentText())
            preset_base = next(
                (m["base"] for m in AIRewriter.supported_models() if m["value"] == model),
                "",
            )
        api_base = self.settings_api_base.text().strip() or preset_base or DEFAULT_API_BASE

        with self.settings.batch():
            if api_key:
                self.settings.set_encrypted("ai_api_key", api_key)
            self.settings.set("ai_model", model)
            self.settings.set("ai_api_base", api_base)

            self.settings.set("ai_temperature", self.settings_temperature.value())
            self.settings.set("ai_max_tokens", self.settings_max_tokens.value())
            self.settings.set("ai_tone", self.tone_combo.currentText())
            self.settings.set("ai_tone_custom", self._custom_tone_text)
            self.settings.set("ai_custom_prompt", self.settings_custom_prompt.toPlainText())
            self.settings.set("ai_use_custom_prompt", self.settings_use_custom.isChecked())

            self.settings.set("http_proxy", self.settings_proxy.text().strip())
            self.settings.set("image_compress", self.settings_compress.isChecked())
            self.settings.set("image_max_width", self.settings_max_width.value())

        temperature = self.settings_temperature.value()
        max_tokens = self.settings_max_tokens.value()

        proxy = self.settings_proxy.text().strip()
        import http_client
        http_client.set_proxy(proxy)

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
        self._update_model_hint()

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

        # 「调整当前结果」：拿右边已改好的版本继续改，不回到原文重来
        if self._get_rewrite_mode() == "refine":
            current = self.rewritten_view.toPlainText().strip()
            if not current:
                self.log("ℹ️ 还没有可调整的结果，改为从原文改写一版")
            else:
                self._start_ai_rewrite(current, self._get_image_mode(), refine=True)
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

    def _start_ai_rewrite(self, content, mode, refine: bool = False):
        base_prompt = self._build_system_prompt(mode, self.tone_combo.currentText())
        if refine:
            system_prompt = self._build_refine_prompt(
                base_prompt, self.refine_input.toPlainText()
            )
        else:
            system_prompt = base_prompt
        self.ai_rewriter.config.system_prompt = system_prompt

        if refine:
            instruction = self.refine_input.toPlainText().strip()
            self.log(
                "✏️ 基于当前结果调整：" + (instruction[:40] if instruction else "按语气整篇重来")
            )
        else:
            self.log("🤖 开始 AI 改写...")
        self.status_label.setText("AI 处理中...")
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 0)
        self.btn_ai.setText("取消改写")
        self.btn_ai.setEnabled(True)
        self.btn_export.setEnabled(False)
        self.btn_copy.setEnabled(False)

        self._rewrite_gen += 1
        gen = self._rewrite_gen
        # 先抓下待处理内容再清面板：_begin_stream 会清空「改写后」，
        # 而「调整当前结果」要读的正是它 —— 顺序反了就会把自己的输入清掉。
        payload = content
        self._begin_stream()
        self.rewrite_worker = RewriteWorker(self.ai_rewriter, payload)
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
        self.preview_stats.setText("📝 改写后预览")
        self.preview_render.setHtml(mistune.html(new_full))
        self._update_panel_counters()
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
        self.rewritten_counter.setText("生成中…")

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

        self.preview_stats.setText("📝 改写后预览")
        self.preview_render.setHtml(mistune.html(result))
        self._update_panel_counters()
        self._set_preview_visible(True)

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
        self._update_panel_counters()
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

    @staticmethod
    def _embed_images_base64(markdown: str) -> str:
        from image_base64 import embed_images
        return embed_images(markdown)


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
