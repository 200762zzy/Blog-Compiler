import itertools
import os
import shutil
from pathlib import Path

import pytest

_counter = itertools.count()


def scratch_root() -> Path:
    """Scratch space for tests that need real files on disk.

    Defaults to `.pytest_tmp` beside the repo rather than the OS temp directory,
    which is not always writable (e.g. the Windows sandbox this project is often
    developed in). Override with BLOGC_TEST_TMP when running elsewhere.
    """
    root = Path(
        os.environ.get("BLOGC_TEST_TMP")
        or Path(__file__).resolve().parent.parent / ".pytest_tmp"
    )
    root.mkdir(parents=True, exist_ok=True)
    return root


@pytest.fixture
def work_dir():
    """A fresh, uniquely named directory under scratch_root().

    Deliberately built with mkdir() instead of tempfile.mkdtemp(): mkdtemp()
    requests mode 0o700, which yields a locked-down directory that a restricted
    sandbox token cannot write into.
    """
    path = scratch_root() / f"case_{os.getpid()}_{next(_counter)}"
    path.mkdir(parents=True, exist_ok=True)
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)


@pytest.fixture
def qapp():
    """离屏 QApplication —— 需要构造真实控件的界面测试用。

    用 offscreen 平台，所以在没有显示器的环境（CI、沙箱）里也能跑。
    """
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    return app


@pytest.fixture
def isolated_settings(monkeypatch, work_dir):
    """把配置目录指到临时位置，避免界面测试读写 ~/.blog-compiler。"""
    import settings as settings_module

    config_dir = work_dir / "config"
    monkeypatch.setattr(settings_module, "CONFIG_DIR", config_dir)
    monkeypatch.setattr(settings_module, "CONFIG_FILE", config_dir / "config.json")
    monkeypatch.setattr(settings_module, "KEY_FILE", config_dir / ".key")
    settings_module._reset_cipher_cache()
    yield config_dir
    settings_module._reset_cipher_cache()


@pytest.fixture
def main_window(qapp, isolated_settings):
    """一个真实的主窗口。

    界面测试的价值就在这里：能验证**信号接线**，而不只是方法本身。
    前端 Bug 常常出在连线上（例如 activated 是重载信号，直连会收到索引）。
    """
    import app as app_module

    app_module.init_publishers(app_module.Settings())
    window = app_module.MainWindow()
    window._apply_theme("dark")
    yield window

    # 更新检查是个后台线程，不等它结束就销毁窗口会打印 QThread 警告
    updater = getattr(window, "_updater", None)
    if updater is not None and updater.isRunning():
        updater.wait(3000)
    window.close()
    window.deleteLater()

