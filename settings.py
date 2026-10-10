import json
from contextlib import contextmanager
from pathlib import Path

from cryptography.fernet import Fernet

from publishers.csdn_sign import DEFAULT_CA_KEY, DEFAULT_CA_SECRET


CONFIG_DIR = Path.home() / ".blog-compiler"
CONFIG_FILE = CONFIG_DIR / "config.json"
KEY_FILE = CONFIG_DIR / ".key"

_cached_cipher: Fernet | None = None


def _reset_cipher_cache():
    """丢弃缓存（测试或导入新配置后需要）。"""
    global _cached_cipher
    _cached_cipher = None


def _get_cipher() -> Fernet:
    """读取（必要时生成）Fernet 密钥。

    结果会缓存：一次保存设置可能触发十几次加解密，每次都读盘没必要。
    测试里替换 KEY_FILE 后要调用 _reset_cipher_cache()。
    """
    global _cached_cipher
    if _cached_cipher is not None:
        return _cached_cipher

    if not KEY_FILE.exists():
        KEY_FILE.parent.mkdir(parents=True, exist_ok=True)
        key = Fernet.generate_key()
        KEY_FILE.write_bytes(key)
    else:
        key = KEY_FILE.read_bytes()
    _cached_cipher = Fernet(key)
    return _cached_cipher


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
        if not isinstance(self.data.get("accounts"), dict):
            self.data["accounts"] = {}
            changed = True
        if not isinstance(self.data.get("publish_presets"), dict):
            self.data["publish_presets"] = {}
            changed = True
        if not isinstance(self.data.get("publish_history"), list):
            self.data["publish_history"] = []
            changed = True
        if changed:
            self.save()
        self.migrate_cnblogs_api_key()

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

    @contextmanager
    def batch(self):
        """在一段代码里连续改多项配置，只在结束时落盘一次。

        `set()` 每调用一次就重写整个配置文件。保存设置界面会连改十几次，
        账号切换要改三个键，逐次落盘既慢又多出几十次写盘失败的机会。

            with settings.batch():
                settings.set("a", 1)
                settings.set("b", 2)   # 到这里只写了一次盘

        块内抛异常也会落盘：此时每一项改动都已生效，不回滚。
        """
        self._defer_save = getattr(self, "_defer_save", 0) + 1
        try:
            yield self
        finally:
            self._defer_save -= 1
            if self._defer_save == 0:
                self.save()

    def get(self, key: str, default=None):
        return self.data.get(key, default)

    def set(self, key: str, value):
        self.data[key] = value
        if not getattr(self, "_defer_save", 0):
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
            # 备份带来的密钥替换了本地密钥，缓存的 cipher 必须作废，
            # 否则接着读加密项会全部解密失败。
            _reset_cipher_cache()

        self.data = data
        self._ensure_defaults()
        self.save()
        return True

    def get_cnblogs_api_key(self) -> str:
        """博客园 API Key：优先取密文，兼容早期版本存下的明文。

        老配置里这个 Key 是明文存的，读到明文就照常使用（否则用户会莫名变成
        「未配置」），下次保存时自动写成密文。明文与密文共用同一个键名，
        这样账号管理里「原样复制该键」的逻辑也能自动走加解密。
        """
        value = self.get("cnblogs_api_key") or ""
        if not value:
            return ""
        try:
            cipher = _get_cipher()
            return cipher.decrypt(value.encode()).decode()
        except Exception:
            return value

    def set_cnblogs_api_key(self, value: str):
        self.set_encrypted("cnblogs_api_key", (value or "").strip())

    def migrate_cnblogs_api_key(self) -> bool:
        """把老配置里的明文 API Key 就地加密，返回是否发生了迁移。"""
        value = self.get("cnblogs_api_key") or ""
        if not value:
            return False
        try:
            _get_cipher().decrypt(value.encode())
            return False
        except Exception:
            self.set_cnblogs_api_key(value)
            return True
