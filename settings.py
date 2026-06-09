import json
from pathlib import Path

from cryptography.fernet import Fernet


CONFIG_DIR = Path.home() / ".blog-compiler"
CONFIG_FILE = CONFIG_DIR / "config.json"
KEY_FILE = CONFIG_DIR / ".key"


def _get_cipher() -> Fernet:
    if not KEY_FILE.exists():
        KEY_FILE.parent.mkdir(parents=True, exist_ok=True)
        key = Fernet.generate_key()
        KEY_FILE.write_bytes(key)
    else:
        key = KEY_FILE.read_bytes()
    return Fernet(key)


class Settings:
    def __init__(self):
        self.data = {}
        self.load()

    def load(self):
        if CONFIG_FILE.exists():
            try:
                self.data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                self.data = {}

    def save(self):
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        CONFIG_FILE.write_text(
            json.dumps(self.data, indent=2, ensure_ascii=False),
            encoding="utf-8"
        )

    def get(self, key: str, default=None):
        return self.data.get(key, default)

    def set(self, key: str, value):
        self.data[key] = value
        self.save()

    def get_encrypted(self, key: str) -> str | None:
        encrypted = self.get(key)
        if not encrypted:
            return None
        try:
            cipher = _get_cipher()
            return cipher.decrypt(encrypted.encode()).decode()
        except Exception:
            return None

    def set_encrypted(self, key: str, value: str):
        cipher = _get_cipher()
        encrypted = cipher.encrypt(value.encode()).decode()
        self.set(key, encrypted)
