"""
Blog Compiler build script.
Usage: python build.py
"""
import io
import subprocess
import sys
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")


def main():
    repo_root = Path(__file__).parent

    print("=" * 50)
    print("  Blog Compiler - Build Script")
    print("=" * 50)

    pyinstaller_args = [
        sys.executable, "-m", "PyInstaller",
        "--name", "BlogCompiler",
        "--windowed",
        "--onefile",
        "--clean",
        "--noconfirm",
        "--add-data", f"requirements.txt{Path(':' if sys.platform != 'win32' else ';')}.",
        "--hidden-import", "PySide6.QtWebEngineWidgets",
        "--hidden-import", "PySide6.QtWebEngineCore",
        "--hidden-import", "PySide6.QtWebChannel",
        str(repo_root / "main.py"),
    ]

    print("\nStarting build...")
    subprocess.run(pyinstaller_args, check=True)

    dist_dir = repo_root / "dist"
    print("\n" + "=" * 50)
    print("  Build complete!")
    print(f"  Output: {dist_dir}")
    print("=" * 50)

    if sys.platform == "win32":
        exe_path = dist_dir / "BlogCompiler.exe"
        if exe_path.exists():
            print(f"  Executable: {exe_path}")
            size_mb = exe_path.stat().st_size / (1024 * 1024)
            print(f"  Size: {size_mb:.1f} MB")


if __name__ == "__main__":
    main()
