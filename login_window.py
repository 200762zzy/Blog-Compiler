"""
CSDN QR-code login window.

Opens passport.csdn.net/login in a QWebEngineView, collects session cookies
after successful QR scan, and emits them via login_successful signal.
"""

from PySide6.QtCore import QUrl, Signal, QTimer
from PySide6.QtWidgets import QDialog, QVBoxLayout, QLabel, QPushButton, QMessageBox
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWebEngineCore import QWebEngineProfile


class CsdnLoginWindow(QDialog):
    login_successful = Signal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("登录 CSDN")
        self.resize(500, 700)
        self.cookies = {}
        self._login_detected = False

        layout = QVBoxLayout(self)

        hint = QLabel("请使用 CSDN App 或 微信 扫描二维码登录\n登录后将自动关闭本窗口")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        self._progress_label = QLabel("正在加载登录页面...")
        layout.addWidget(self._progress_label)

        self.browser = QWebEngineView()
        layout.addWidget(self.browser)

        self.btn_cancel = QPushButton("取消")
        self.btn_cancel.clicked.connect(self.reject)
        layout.addWidget(self.btn_cancel)

        profile = QWebEngineProfile.defaultProfile()
        cookie_store = profile.cookieStore()
        cookie_store.cookieAdded.connect(self._on_cookie_added)

        self.browser.urlChanged.connect(self._on_url_changed)
        self.browser.load(QUrl("https://passport.csdn.net/login"))

        QTimer.singleShot(120000, lambda: self._check_stuck())

    def _on_cookie_added(self, cookie):
        name = cookie.name().data().decode(errors="replace")
        value = cookie.value().data().decode(errors="replace")
        domain = cookie.domain()
        self.cookies[name] = {"value": value, "domain": domain}

    def _on_url_changed(self, url):
        url_str = url.toString()
        if self._login_detected:
            return
        if (
            "passport.csdn.net" not in url_str
            and "login" not in url_str
            and url_str.startswith("https://www.csdn.net/")
        ):
            self._login_detected = True
            self._progress_label.setText("登录成功，正在获取 Cookie...")
            QTimer.singleShot(2000, self._finalize_login)

    def _finalize_login(self):
        user_cookies = {
            k: v["value"]
            for k, v in self.cookies.items()
            if "csdn.net" in v.get("domain", "")
        }
        if user_cookies:
            self.login_successful.emit(user_cookies)
            QMessageBox.information(self, "登录成功", "CSDN 登录成功！")
            self.accept()
        else:
            self._progress_label.setText("等待 Cookie 完成...")
            QTimer.singleShot(2000, self._finalize_login)

    def _check_stuck(self):
        if not self._login_detected:
            current_url = self.browser.url().toString()
            if "login" in current_url:
                self._progress_label.setText("请扫描二维码完成登录...")
