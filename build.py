"""
Blog Compiler build script.

Usage:
  py build.py            # full build (with QtWebEngine scan-login, ~236 MB)
  py build.py --lite     # lite build (no QtWebEngine, cookie import, much smaller)
"""
import argparse
import io
import subprocess
import sys
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

SEP = ":" if sys.platform != "win32" else ";"

COMMON_EXCLUDES = [
    "PySide6.QtDesigner", "PySide6.QtPdf", "PySide6.QtPdfWidgets",
    "PySide6.QtCharts", "PySide6.QtDataVisualization", "PySide6.QtTest",
    "PySide6.QtSql", "PySide6.QtSensors", "PySide6.QtSerialPort",
    "PySide6.QtWebSockets", "PySide6.QtBluetooth", "PySide6.QtNfc",
    "PySide6.QtPositioning", "PySide6.QtLocation", "PySide6.QtRemoteObjects",
    "PySide6.QtScxml", "PySide6.QtStateMachine", "PySide6.QtTextToSpeech",
    "PySide6.QtHelp", "PySide6.QtUiTools",
    "tkinter", "unittest", "pydoc", "doctest", "pdb",
]

LITE_EXCLUDES = [
    "PySide6.QtWebEngineWidgets",
    "PySide6.QtWebEngineCore",
    "PySide6.QtWebEngineQuick",
    "PySide6.QtWebChannel",
]


def main():
    parser = argparse.ArgumentParser(description="Build Blog Compiler")
    parser.add_argument(
        "--lite", action="store_true",
        help="构建精简版（不含 QtWebEngine，登录改用系统浏览器 + Cookie 导入）",
    )
    args = parser.parse_args()

    repo_root = Path(__file__).parent
    name = "BlogCompiler-lite" if args.lite else "BlogCompiler"

    print("=" * 50)
    print(f"  Blog Compiler - Build Script ({'LITE' if args.lite else 'FULL'})")
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
    ]

    for mod in COMMON_EXCLUDES:
        pyinstaller_args += ["--exclude-module", mod]

    if args.lite:
        for mod in LITE_EXCLUDES:
            pyinstaller_args += ["--exclude-module", mod]
    else:
        pyinstaller_args += [
            "--hidden-import", "PySide6.QtWebEngineWidgets",
            "--hidden-import", "PySide6.QtWebEngineCore",
            "--hidden-import", "PySide6.QtWebChannel",
        ]

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
