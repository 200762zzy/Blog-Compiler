from PySide6.QtCore import QUrl, Signal, QTimer
from PySide6.QtWidgets import QDialog, QVBoxLayout, QLabel, QPushButton, QMessageBox


class PlatformLoginWindow(QDialog):
    login_successful = Signal(dict)

    def __init__(self, parent, login_url: str, domain_filter: str, window_title: str = "登录"):
        super().__init__(parent)
        self.setWindowTitle(window_title)
        self.resize(500, 700)
        self.cookies = {}
        self._login_detected = False
        self._domain_filter = domain_filter
        self._login_url = login_url

        layout = QVBoxLayout(self)

        hint = QLabel("请使用 App 或 微信 扫描二维码登录\n登录后将自动关闭本窗口")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        self._progress_label = QLabel("正在加载登录页面...")
        layout.addWidget(self._progress_label)

        try:
            from PySide6.QtWebEngineWidgets import QWebEngineView
        except ImportError:
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.critical(self, "错误", "缺少 QtWebEngine 模块，无法使用扫码登录。\n请安装: pip install PySide6-QtWebEngine")
            self.reject()
            return
        self.browser = QWebEngineView()
        layout.addWidget(self.browser)

        self.btn_cancel = QPushButton("取消")
        self.btn_cancel.clicked.connect(self.reject)
        layout.addWidget(self.btn_cancel)

        try:
            from PySide6.QtWebEngineCore import QWebEngineProfile
        except ImportError:
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.critical(self, "错误", "缺少 QtWebEngineCore 模块")
            self.reject()
            return
        profile = QWebEngineProfile.defaultProfile()
        cookie_store = profile.cookieStore()
        cookie_store.cookieAdded.connect(self._on_cookie_added)

        self.browser.urlChanged.connect(self._on_url_changed)
        self.browser.load(QUrl(self._login_url))

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
        if self._is_login_successful(url_str):
            self._login_detected = True
            self._progress_label.setText("登录成功，正在获取 Cookie...")
            QTimer.singleShot(2000, self._finalize_login)

    def _is_login_successful(self, url_str: str) -> bool:
        return False

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


class CsdnLoginWindow(PlatformLoginWindow):
    def __init__(self, parent=None):
        super().__init__(
            parent,
            login_url="https://passport.csdn.net/login",
            domain_filter="csdn.net",
            window_title="登录 CSDN",
        )

    def _is_login_successful(self, url_str: str) -> bool:
        return (
            "passport.csdn.net" not in url_str
            and "login" not in url_str
            and url_str.startswith("https://www.csdn.net/")
        )
