import json

from PySide6.QtCore import QUrl, Signal, QTimer
from PySide6.QtWidgets import QDialog, QVBoxLayout, QLabel, QPushButton, QMessageBox
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWebEngineCore import QWebEngineProfile, QWebEngineCookieStore


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

        self.browser = QWebEngineView()
        layout.addWidget(self.browser)

        self.btn_cancel = QPushButton("取消")
        self.btn_cancel.clicked.connect(self.reject)
        layout.addWidget(self.btn_cancel)

        profile = QWebEngineProfile.defaultProfile()
        self.cookie_store = profile.cookieStore()
        self.cookie_store.cookieAdded.connect(self._on_cookie_added)

        self.browser.urlChanged.connect(self._on_url_changed)
        self.browser.load(QUrl("https://passport.csdn.net/login"))

        self._progress_label = QLabel("正在加载登录页面...")
        layout.insertWidget(1, self._progress_label)

        QTimer.singleShot(30000, self._check_stuck)

    def _on_cookie_added(self, cookie):
        name = cookie.name().data().decode()
        value = cookie.value().data().decode()
        domain = cookie.domain()
        self.cookies[name] = {"value": value, "domain": domain}

    def _on_url_changed(self, url):
        url_str = url.toString()
        if "passport.csdn.net" not in url_str and "login" not in url_str.lower():
            if not self._login_detected:
                self._login_detected = True
                QTimer.singleShot(1500, self._finalize_login)

    def _finalize_login(self):
        self.browser.page().runJavaScript(
            "document.body.innerHTML",
            self._check_logged_in
        )

    def _check_logged_in(self, html):
        if not html:
            return
        user_cookies = {
            k: v["value"]
            for k, v in self.cookies.items()
            if "csdn" in v.get("domain", "")
        }
        if user_cookies:
            self.login_successful.emit(user_cookies)
            QMessageBox.information(self, "登录成功", "CSDN 登录成功！")
            self.accept()
        else:
            self._progress_label.setText("等待登录完成...")

    def _check_stuck(self):
        if not self._login_detected:
            current_url = self.browser.url().toString()
            if "login" in current_url.lower():
                self._progress_label.setText("请扫描二维码完成登录...")
