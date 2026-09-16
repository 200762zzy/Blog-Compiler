"""
Blog Compiler build script.

Usage:
  py build.py

Single unified build: UI uses PySide6, login uses the system WebView2 runtime
via pywebview (no bundled QtWebEngine).
"""
import io
import subprocess
import sys
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

SEP = ":" if sys.platform != "win32" else ";"

EXCLUDES = [
    "PySide6.QtDesigner", "PySide6.QtPdf", "PySide6.QtPdfWidgets",
    "PySide6.QtCharts", "PySide6.QtDataVisualization", "PySide6.QtTest",
    "PySide6.QtSql", "PySide6.QtSensors", "PySide6.QtSerialPort",
    "PySide6.QtWebSockets", "PySide6.QtBluetooth", "PySide6.QtNfc",
    "PySide6.QtPositioning", "PySide6.QtLocation", "PySide6.QtRemoteObjects",
    "PySide6.QtScxml", "PySide6.QtStateMachine", "PySide6.QtTextToSpeech",
    "PySide6.QtHelp", "PySide6.QtUiTools",
    "PySide6.QtWebEngineWidgets", "PySide6.QtWebEngineCore",
    "PySide6.QtWebEngineQuick", "PySide6.QtWebChannel",
    # pywebview ships Qt/GTK/CEF backends we don't use on Windows
    "PyQt5", "PyQt6",
    "webview.platforms.qt", "webview.platforms.gtk",
    "webview.platforms.cef", "webview.platforms.android",
    "webview.platforms.mshtml",
    "tkinter", "unittest", "pydoc", "doctest", "pdb",
]


def main():
    repo_root = Path(__file__).parent
    name = "BlogCompiler"

    print("=" * 50)
    print("  Blog Compiler - Build Script")
    print("=" * 50)

    pyinstaller_args = [
        sys.executable, "-m", "PyInstaller",
        "--name", name,
        "--windowed",
        "--onefile",
        "--clean",
        "--noconfirm",
        "--icon", str(repo_root / "icon.ico"),
        "--add-data", f"requirements.txt{SEP}.",
        "--add-data", f"icon.ico{SEP}.",
        "--hidden-import", "publishers",
        "--collect-submodules", "publishers",
        "--hidden-import", "webview",
        "--hidden-import", "webview.platforms.edgechromium",
        "--hidden-import", "webview.platforms.winforms",
        "--collect-data", "webview",
        "--hidden-import", "clr",
    ]

    for mod in EXCLUDES:
        pyinstaller_args += ["--exclude-module", mod]

    pyinstaller_args.append(str(repo_root / "main.py"))

    print("\nStarting build...")
    subprocess.run(pyinstaller_args, check=True)

    dist_dir = repo_root / "dist"
    print("\n" + "=" * 50)
    print("  Build complete!")
    print(f"  Output: {dist_dir}")
    print("=" * 50)

    exe_name = f"{name}.exe" if sys.platform == "win32" else name
    exe_path = dist_dir / exe_name
    if exe_path.exists():
        print(f"  Executable: {exe_path}")
        size_mb = exe_path.stat().st_size / (1024 * 1024)
        print(f"  Size: {size_mb:.1f} MB")


if __name__ == "__main__":
    main()
