"""
Blog Compiler 打包脚本
运行: python build.py
"""

import subprocess
import sys
from pathlib import Path


def main():
    repo_root = Path(__file__).parent

    print("=" * 50)
    print("  Blog Compiler - Build Script")
    print("=" * 50)

    pip_cmd = [sys.executable, "-m", "pip", "install", "-r"]
    subprocess.run(pip_cmd + [str(repo_root / "requirements.txt")], check=True)

    pyinstaller_args = [
        sys.executable, "-m", "PyInstaller",
        "--name", "BlogCompiler",
        "--windowed",
        "--onefile",
        "--clean",
        "--add-data", f"requirements.txt{Path(':' if sys.platform != 'win32' else ';')}.",
        "--hidden-import", "PySide6.QtWebEngineWidgets",
        "--hidden-import", "PySide6.QtWebEngineCore",
        "--hidden-import", "PySide6.QtWebChannel",
        str(repo_root / "main.py"),
    ]

    print("\n🚀 开始打包...")
    subprocess.run(pyinstaller_args, check=True)

    dist_dir = repo_root / "dist"
    print("\n" + "=" * 50)
    print(f"  ✅ 打包完成!")
    print(f"  输出目录: {dist_dir}")
    print("=" * 50)

    if sys.platform == "win32":
        exe_path = dist_dir / "BlogCompiler.exe"
        if exe_path.exists():
            print(f"  📦 可执行文件: {exe_path}")
            size_mb = exe_path.stat().st_size / (1024 * 1024)
            print(f"  大小: {size_mb:.1f} MB")


if __name__ == "__main__":
    main()
