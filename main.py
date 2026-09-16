import sys
import traceback
from datetime import datetime
from pathlib import Path


CRASH_LOG = Path.home() / ".blog-compiler" / "crash.log"


def _run_webview_login(argv) -> int:
    import json

    import webview_login

    if len(argv) < 2:
        print("usage: --login-webview <json>")
        return 2
    try:
        config = json.loads(argv[1])
    except Exception as e:
        print(f"invalid config: {e}")
        return 2
    return webview_login.run(config)


def _setup_crash_handler():
    def excepthook(exc_type, exc_value, exc_tb):
        tb_text = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        CRASH_LOG.parent.mkdir(parents=True, exist_ok=True)
        CRASH_LOG.write_text(
            f"=== Crash at {timestamp} ===\n{tb_text}\n",
            encoding="utf-8"
        )
        print(f"❌ 发生崩溃，日志已保存到: {CRASH_LOG}", file=sys.stderr)
        print(tb_text, file=sys.stderr)

        try:
            from PySide6.QtWidgets import QMessageBox
            msg = QMessageBox()
            msg.setIcon(QMessageBox.Critical)
            msg.setWindowTitle("Blog Compiler - 崩溃")
            msg.setText("程序发生意外错误")
            msg.setInformativeText(
                f"错误信息已保存到:\n{CRASH_LOG}\n\n"
                f"请将此文件发送给开发者。"
            )
            msg.exec()
        except Exception:
            pass

    sys.excepthook = excepthook


def main():
    if len(sys.argv) >= 2 and sys.argv[1] == "--login-webview":
        sys.exit(_run_webview_login(sys.argv[1:]))

    _setup_crash_handler()

    from PySide6.QtWidgets import QApplication
    from app import MainWindow

    app = QApplication(sys.argv)
    app.setApplicationName("Blog Compiler")
    app.setOrganizationName("BlogCompiler")

    window = MainWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
