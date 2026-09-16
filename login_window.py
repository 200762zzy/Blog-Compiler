import json
import subprocess
import sys
from pathlib import Path

from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QMessageBox,
    QPlainTextEdit,
)

COOKIE_MARKER = "__BLOGC_COOKIES__"


def parse_cookie_text(text: str) -> dict:
    """Parse pasted cookies: 'k=v; k2=v2' or a JSON object."""
    text = (text or "").strip()
    if not text:
        return {}

    if text.startswith("{"):
        try:
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


def spawn_webview_login(login_url, domain_filter, title, success_prefix=None, timeout=600):
    """Run the WebView2 login helper in a subprocess; return (cookies, error).

    The helper writes its result to a temp file because the frozen (windowed)
    exe has no usable stdout.
    """
    import os
    import tempfile

    fd, outfile = tempfile.mkstemp(prefix="blogc_login_", suffix=".json")
    os.close(fd)

    if getattr(sys, "frozen", False):
        cmd = [sys.executable, "--login-webview", login_url, domain_filter, title,
               success_prefix or "-", outfile]
    else:
        cmd = [
            sys.executable,
            str(Path(__file__).resolve().parent / "main.py"),
            "--login-webview", login_url, domain_filter, title,
            success_prefix or "-", outfile,
        ]

    data = None
    proc = None
    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=timeout,
        )
    except Exception as e:
        _cleanup(outfile)
        return None, str(e)

    try:
        if os.path.exists(outfile):
            content = Path(outfile).read_text(encoding="utf-8").strip()
            if content:
                data = json.loads(content)
    except Exception:
        data = None
    _cleanup(outfile)

    if data is None:
        for line in (proc.stdout or "").splitlines():
            if line.startswith(COOKIE_MARKER):
                try:
                    data = json.loads(line[len(COOKIE_MARKER):])
                except Exception:
                    data = None
                break

    if data and data.get("cookies"):
        return data["cookies"], None
    if data:
        return None, data.get("error", "未获取到 Cookie")
    return None, ((proc.stderr or "登录窗口无输出").strip()[:300])


def _cleanup(path):
    import os
    try:
        if path and os.path.exists(path):
            os.remove(path)
    except OSError:
        pass


class LoginWorker(QThread):
    done = Signal(dict)
    failed = Signal(str)

    def __init__(self, login_url, domain_filter, title, success_prefix=None):
        super().__init__()
        self.login_url = login_url
        self.domain_filter = domain_filter
        self.title = title
        self.success_prefix = success_prefix

    def run(self):
        cookies, err = spawn_webview_login(
            self.login_url, self.domain_filter, self.title, self.success_prefix
        )
        if cookies:
            self.done.emit(cookies)
        else:
            self.failed.emit(err or "登录失败")


class PlatformLoginWindow(QDialog):
    login_successful = Signal(dict)

    def __init__(self, parent, login_url: str, domain_filter: str,
                 window_title: str = "登录", success_check=None, success_prefix=None):
        super().__init__(parent)
        self.setWindowTitle(window_title)
        self.resize(560, 520)
        self._login_url = login_url
        self._domain_filter = domain_filter
        self._success_prefix = success_prefix
        self._worker = None

        layout = QVBoxLayout(self)

        hint = QLabel(
            "点击「扫码登录」后会弹出登录窗口，用 App / 微信扫码完成登录。\n"
            "（使用系统 WebView2，无需内置浏览器）"
        )
        hint.setWordWrap(True)
        layout.addWidget(hint)

        self.scan_btn = QPushButton("扫码登录（推荐）")
        self.scan_btn.setObjectName("primaryBtn")
        self.scan_btn.clicked.connect(self._start_scan)
        layout.addWidget(self.scan_btn)

        self.status = QLabel("")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)

        layout.addWidget(QLabel("———— 或手动粘贴 Cookie ————"))
        self.cookie_edit = QPlainTextEdit()
        self.cookie_edit.setPlaceholderText("name1=value1; name2=value2")
        layout.addWidget(self.cookie_edit, 1)

        row = QHBoxLayout()
        row.addStretch()
        use_btn = QPushButton("使用 Cookie 登录")
        use_btn.setObjectName("secondaryBtn")
        use_btn.clicked.connect(self._on_cookie_ok)
        cancel_btn = QPushButton("取消")
        cancel_btn.clicked.connect(self.reject)
        row.addWidget(use_btn)
        row.addWidget(cancel_btn)
        layout.addLayout(row)

    def _start_scan(self):
        if self._worker and self._worker.isRunning():
            return
        self.scan_btn.setEnabled(False)
        self.status.setText("已弹出登录窗口，请扫码完成登录…")
        self._worker = LoginWorker(
            self._login_url, self._domain_filter, self.windowTitle(), self._success_prefix
        )
        self._worker.done.connect(self._on_scan_done)
        self._worker.failed.connect(self._on_scan_failed)
        self._worker.start()

    def _on_scan_done(self, cookies):
        self.login_successful.emit(cookies)
        QMessageBox.information(self, "登录成功", f"{self.windowTitle()} 成功！")
        self.accept()

    def _on_scan_failed(self, err):
        self.scan_btn.setEnabled(True)
        self.status.setText(f"扫码登录失败：{err}\n可尝试在下方手动粘贴 Cookie。")

    def _on_cookie_ok(self):
        cookies = parse_cookie_text(self.cookie_edit.toPlainText())
        if not cookies:
            QMessageBox.warning(self, "提示", "请粘贴有效的 Cookie")
            return
        self.login_successful.emit(cookies)
        QMessageBox.information(self, "已保存", "Cookie 已保存")
        self.accept()


class CsdnLoginWindow(PlatformLoginWindow):
    def __init__(self, parent=None):
        super().__init__(
            parent,
            login_url="https://passport.csdn.net/login",
            domain_filter="csdn.net",
            window_title="登录 CSDN",
        )
