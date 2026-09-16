from PySide6.QtCore import QUrl, Signal, QTimer
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QMessageBox,
    QPlainTextEdit,
)

try:
    from PySide6.QtWebEngineWidgets import QWebEngineView
    from PySide6.QtWebEngineCore import QWebEngineProfile
    WEBENGINE_AVAILABLE = True
except Exception:
    QWebEngineView = None
    QWebEngineProfile = None
    WEBENGINE_AVAILABLE = False


def parse_cookie_text(text: str) -> dict:
    """Parse pasted cookies: 'k=v; k2=v2' or a JSON object."""
    text = (text or "").strip()
    if not text:
        return {}

    if text.startswith("{"):
        try:
            import json
            data = json.loads(text)
            if isinstance(data, dict):
                out = {}
                for k, v in data.items():
                    out[k] = v.get("value", "") if isinstance(v, dict) else str(v)
                if out:
                    return out
        except Exception:
            pass

    out = {}
    for part in text.replace("\n", ";").split(";"):
        part = part.strip()
        if not part or "=" not in part:
            continue
        k, v = part.split("=", 1)
        k = k.strip()
        if k:
            out[k] = v.strip()
    return out


class PlatformLoginWindow(QDialog):
    login_successful = Signal(dict)

    def __init__(self, parent, login_url: str, domain_filter: str, window_title: str = "登录", success_check=None):
        super().__init__(parent)
        self.setWindowTitle(window_title)
        self.resize(500, 700)
        self.cookies = {}
        self._login_detected = False
        self._domain_filter = domain_filter
        self._login_url = login_url
        self._success_check = success_check

        if not WEBENGINE_AVAILABLE:
            self._setup_cookie_import()
            return

        layout = QVBoxLayout(self)

        hint = QLabel("请使用 App 或 微信 扫描二维码登录\n登录后将自动关闭本窗口")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        self._progress_label = QLabel("正在加载登录页面...")
        layout.addWidget(self._progress_label)

        self.browser = QWebEngineView()
        layout.addWidget(self.browser)

        self.btn_confirm = QPushButton("已完成扫码，确认登录")
        self.btn_confirm.setEnabled(False)
        self.btn_confirm.clicked.connect(self._on_manual_confirm)
        layout.addWidget(self.btn_confirm)

        self.btn_cancel = QPushButton("取消")
        self.btn_cancel.clicked.connect(self.reject)
        layout.addWidget(self.btn_cancel)

        profile = QWebEngineProfile.defaultProfile()
        cookie_store = profile.cookieStore()
        cookie_store.cookieAdded.connect(self._on_cookie_added)

        self.browser.urlChanged.connect(self._on_url_changed)
        self.browser.load(QUrl(self._login_url))

        QTimer.singleShot(3000, lambda: self._enable_confirm())
        QTimer.singleShot(120000, lambda: self._check_stuck())

    def _setup_cookie_import(self):
        """Fallback for the lite build (no QtWebEngine): paste cookies manually."""
        self.resize(560, 500)
        layout = QVBoxLayout(self)

        hint = QLabel(
            "当前为「精简版」，未内置浏览器。\n\n"
            "1. 点击下方按钮，在系统浏览器中打开登录页并完成登录\n"
            "2. 登录后按 F12 → Application/应用 → Cookies，复制相关 Cookie\n"
            "3. 粘贴到下方（支持 k=v; k2=v2 或 JSON），点击确定"
        )
        hint.setWordWrap(True)
        layout.addWidget(hint)

        open_btn = QPushButton("打开登录页面")
        open_btn.setObjectName("secondaryBtn")
        open_btn.clicked.connect(
            lambda: QDesktopServices.openUrl(QUrl(self._login_url))
        )
        layout.addWidget(open_btn)

        layout.addWidget(QLabel("Cookie："))
        self.cookie_edit = QPlainTextEdit()
        self.cookie_edit.setPlaceholderText("name1=value1; name2=value2")
        layout.addWidget(self.cookie_edit, 1)

        row = QHBoxLayout()
        row.addStretch()
        ok_btn = QPushButton("确定")
        ok_btn.setObjectName("primaryBtn")
        ok_btn.clicked.connect(self._on_cookie_ok)
        cancel_btn = QPushButton("取消")
        cancel_btn.clicked.connect(self.reject)
        row.addWidget(ok_btn)
        row.addWidget(cancel_btn)
        layout.addLayout(row)

    def _on_cookie_ok(self):
        cookies = parse_cookie_text(self.cookie_edit.toPlainText())
        if not cookies:
            QMessageBox.warning(self, "提示", "请粘贴有效的 Cookie")
            return
        self.login_successful.emit(cookies)
        QMessageBox.information(self, "已保存", "Cookie 已保存")
        self.accept()

    def _enable_confirm(self):
        if not self._login_detected:
            self.btn_confirm.setEnabled(True)
            self._progress_label.setText("请扫描二维码完成登录")

    def _on_cookie_added(self, cookie):
        name = cookie.name().data().decode(errors="replace")
        value = cookie.value().data().decode(errors="replace")
        domain = cookie.domain()
        self.cookies[name] = {"value": value, "domain": domain}

    def _on_url_changed(self, url):
        url_str = url.toString()
        if self._login_detected:
            return
        if self._is_login_successful(url_str):
            self._login_detected = True
            self._progress_label.setText("登录成功，正在获取 Cookie...")
            QTimer.singleShot(2000, self._finalize_login)

    def _is_login_successful(self, url_str: str) -> bool:
        if self._success_check:
            return self._success_check(url_str)
        return (
            "login" not in url_str.lower()
            and self._domain_filter in url_str
        )

    def _finalize_login(self):
        domain = self._domain_filter
        user_cookies = {
            k: v["value"]
            for k, v in self.cookies.items()
            if domain in v.get("domain", "")
        }
        if user_cookies:
            self.login_successful.emit(user_cookies)
            QMessageBox.information(self, "登录成功", f"{self.windowTitle()} 成功！")
            self.accept()
        else:
            self._progress_label.setText("等待 Cookie 完成...")
            QTimer.singleShot(2000, self._finalize_login)

    def _check_stuck(self):
        if not self._login_detected:
            current_url = self.browser.url().toString()
            if "login" in current_url:
                self._progress_label.setText("请扫描二维码完成登录...")

    def _on_manual_confirm(self):
        if self._login_detected:
            return
        self._login_detected = True
        self._progress_label.setText("登录确认，正在获取 Cookie...")
        QTimer.singleShot(2000, self._finalize_login)


class CsdnLoginWindow(PlatformLoginWindow):
    def __init__(self, parent=None):
        super().__init__(
            parent,
            login_url="https://passport.csdn.net/login",
            domain_filter="csdn.net",
            window_title="登录 CSDN",
            success_check=lambda url: (
                "passport.csdn.net" not in url
                and "login" not in url
                and url.startswith("https://www.csdn.net/")
            ),
        )
