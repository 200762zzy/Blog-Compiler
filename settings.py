import json
from pathlib import Path

from cryptography.fernet import Fernet


CONFIG_DIR = Path.home() / ".blog-compiler"
CONFIG_FILE = CONFIG_DIR / "config.json"
KEY_FILE = CONFIG_DIR / ".key"

DEFAULT_CA_KEY = "203803574"
DEFAULT_CA_SECRET = "9znpamsyl2c7cdrr9sas0le9vbc3r6ba"


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
        self._ensure_defaults()

    def _ensure_defaults(self):
        changed = False
        if "ca_key" not in self.data:
            self.data["ca_key"] = DEFAULT_CA_KEY
            changed = True
        if "ca_secret" not in self.data:
            self.data["ca_secret"] = DEFAULT_CA_SECRET
            changed = True
        for key in ("juejin_cookies", "cnblogs_username", "cnblogs_api_key", "cnblogs_blog_id"):
            if key not in self.data:
                self.data[key] = ""
                changed = True
        if "http_proxy" not in self.data:
            self.data["http_proxy"] = ""
            changed = True
        if "image_compress" not in self.data:
            self.data["image_compress"] = True
            changed = True
        if "image_max_width" not in self.data:
            self.data["image_max_width"] = 1600
            changed = True
        if changed:
            self.save()

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
            import logging
            logging.getLogger(__name__).exception(f"解密失败: key={key}")
            return None

    def set_encrypted(self, key: str, value: str):
        cipher = _get_cipher()
        encrypted = cipher.encrypt(value.encode()).decode()
        self.set(key, encrypted)

    def export_config(self, path: str) -> str:
        """Write a portable backup (config data + the Fernet key)."""
        import base64

        key_b64 = None
        if KEY_FILE.exists():
            key_b64 = base64.b64encode(KEY_FILE.read_bytes()).decode()
        bundle = {"app": "blog-compiler", "version": 1, "key": key_b64, "data": self.data}
        Path(path).write_text(
            json.dumps(bundle, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return path

    def import_config(self, path: str) -> bool:
        """Restore a backup created by export_config()."""
        import base64

        bundle = json.loads(Path(path).read_text(encoding="utf-8"))
        data = bundle.get("data")
        if not isinstance(data, dict):
            raise ValueError("配置文件格式不正确")

        key_b64 = bundle.get("key")
        if key_b64:
            CONFIG_DIR.mkdir(parents=True, exist_ok=True)
            KEY_FILE.write_bytes(base64.b64decode(key_b64))

        self.data = data
        self._ensure_defaults()
        self.save()
        return True
