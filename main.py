import sys
import traceback
from datetime import datetime
from pathlib import Path

from PySide6.QtWidgets import QApplication, QMessageBox

from app import MainWindow


VERSION = "1.3.0"
CRASH_LOG = Path.home() / ".blog-compiler" / "crash.log"


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
    _setup_crash_handler()

    app = QApplication(sys.argv)
    app.setApplicationName("Blog Compiler")
    app.setOrganizationName("BlogCompiler")

    window = MainWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
