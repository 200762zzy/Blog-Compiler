import json

import pytest

import settings as settings_module
from settings import Settings


@pytest.fixture
def isolated(monkeypatch, work_dir):
    """Redirect the config location so tests never touch ~/.blog-compiler."""
    config_dir = work_dir / "config"
    monkeypatch.setattr(settings_module, "CONFIG_DIR", config_dir)
    monkeypatch.setattr(settings_module, "CONFIG_FILE", config_dir / "config.json")
    monkeypatch.setattr(settings_module, "KEY_FILE", config_dir / ".key")
    # 密钥是带缓存的，换目录后必须作废，否则会拿到上一个用例的密钥
    settings_module._reset_cipher_cache()
    yield config_dir
    settings_module._reset_cipher_cache()


def test_defaults_are_written_on_first_run(isolated):
    s = Settings()
    assert s.get("ca_key") == settings_module.DEFAULT_CA_KEY
    assert s.get("ca_secret") == settings_module.DEFAULT_CA_SECRET
    assert s.get("http_proxy") == ""
    assert s.get("image_compress") is True
    assert s.get("image_max_width") == 1600
    assert s.get("accounts") == {}
    assert s.get("publish_presets") == {}
    assert s.get("publish_history") == []
    assert (isolated / "config.json").exists()


def test_platform_credential_keys_default_to_empty(isolated):
    s = Settings()
    for key in ("juejin_cookies", "cnblogs_username", "cnblogs_api_key", "cnblogs_blog_id"):
        assert s.get(key) == ""


def test_values_persist_across_instances(isolated):
    Settings().set("ai_model", "deepseek-v4-pro")
    assert Settings().get("ai_model") == "deepseek-v4-pro"


def test_get_returns_default_for_unknown_key(isolated):
    assert Settings().get("nope", "fallback") == "fallback"


def test_encrypted_round_trip(isolated):
    s = Settings()
    s.set_encrypted("ai_api_key", "sk-secret-value")

    assert s.get_encrypted("ai_api_key") == "sk-secret-value"
    assert "sk-secret-value" not in json.dumps(s.data)
    assert Settings().get_encrypted("ai_api_key") == "sk-secret-value"


def test_get_encrypted_missing_key_returns_none(isolated):
    assert Settings().get_encrypted("ai_api_key") is None


def test_get_encrypted_undecryptable_returns_none(isolated):
    s = Settings()
    s.set("ai_api_key", "not-a-fernet-token")
    assert s.get_encrypted("ai_api_key") is None


class TestCnblogsApiKey:
    """博客园 API Key 必须加密存储。"""

    def test_set_stores_ciphertext(self, isolated):
        s = Settings()
        s.set_cnblogs_api_key("plain-secret")

        assert s.get_cnblogs_api_key() == "plain-secret"
        assert "plain-secret" not in json.dumps(s.data)
        assert s.data["cnblogs_api_key"] != "plain-secret"

    def test_survives_reload(self, isolated):
        Settings().set_cnblogs_api_key("plain-secret")
        assert Settings().get_cnblogs_api_key() == "plain-secret"

    def test_missing_key_is_empty(self, isolated):
        assert Settings().get_cnblogs_api_key() == ""

    def test_whitespace_is_trimmed(self, isolated):
        s = Settings()
        s.set_cnblogs_api_key("  spaced  ")
        assert s.get_cnblogs_api_key() == "spaced"

    def test_legacy_plaintext_still_readable(self, isolated):
        """老配置里是明文，不能因为改成密文就让用户掉登录。"""
        s = Settings()
        s.set("cnblogs_api_key", "legacy-plaintext")
        assert s.get_cnblogs_api_key() == "legacy-plaintext"

    def test_legacy_plaintext_is_migrated_on_load(self, isolated):
        isolated.mkdir(parents=True, exist_ok=True)
        (isolated / "config.json").write_text(
            json.dumps({"cnblogs_api_key": "legacy-plaintext"}), encoding="utf-8"
        )

        s = Settings()

        assert s.get_cnblogs_api_key() == "legacy-plaintext"
        assert "legacy-plaintext" not in json.dumps(s.data)
        # 迁移结果要落盘，下次启动就是密文了
        assert "legacy-plaintext" not in (isolated / "config.json").read_text(encoding="utf-8")

    def test_migration_is_idempotent(self, isolated):
        isolated.mkdir(parents=True, exist_ok=True)
        (isolated / "config.json").write_text(
            json.dumps({"cnblogs_api_key": "legacy"}), encoding="utf-8"
        )

        first = Settings()
        stored = first.data["cnblogs_api_key"]
        second = Settings()

        assert second.data["cnblogs_api_key"] == stored
        assert second.get_cnblogs_api_key() == "legacy"

    def test_migration_reports_whether_it_changed_anything(self, isolated):
        s = Settings()
        assert s.migrate_cnblogs_api_key() is False

        s.set("cnblogs_api_key", "plain")
        assert s.migrate_cnblogs_api_key() is True
        assert s.migrate_cnblogs_api_key() is False


class TestCnblogsPublisherUsesEncryptedKey:
    def test_publisher_reads_the_decrypted_key(self, isolated):
        from publishers.cnblogs import CnblogsPublisher

        settings = Settings()
        settings.set("cnblogs_username", "me")
        settings.set_cnblogs_api_key("my-key")

        publisher = CnblogsPublisher(settings)

        assert publisher._api_key == "my-key"
        assert publisher.is_logged_in() is True

    def test_publisher_writes_ciphertext(self, isolated):
        from publishers.cnblogs import CnblogsPublisher

        settings = Settings()
        publisher = CnblogsPublisher(settings)
        publisher._username = "me"
        publisher._api_key = "my-key"
        publisher._blog_id = "myblog"
        publisher._save()

        assert "my-key" not in json.dumps(settings.data)
        assert settings.get_cnblogs_api_key() == "my-key"


def test_corrupt_config_falls_back_to_empty(isolated):
    isolated.mkdir(parents=True, exist_ok=True)
    (isolated / "config.json").write_text("{ broken json", encoding="utf-8")
    assert Settings().get("ca_key") == settings_module.DEFAULT_CA_KEY


def test_ensure_defaults_repairs_wrong_types(isolated):
    isolated.mkdir(parents=True, exist_ok=True)
    (isolated / "config.json").write_text(
        json.dumps({"accounts": None, "publish_history": "x", "publish_presets": []}),
        encoding="utf-8",
    )
    s = Settings()
    assert s.get("accounts") == {}
    assert s.get("publish_presets") == {}
    assert s.get("publish_history") == []


def test_export_import_preserves_encrypted_secret(isolated, work_dir):
    source = Settings()
    source.set_encrypted("ai_api_key", "sk-round-trip")
    source.set("ai_model", "kimi-k3")
    backup = work_dir / "backup.json"

    source.export_config(str(backup))
    bundle = json.loads(backup.read_text(encoding="utf-8"))
    assert bundle["app"] == "blog-compiler"
    assert bundle["key"]

    target = Settings()
    target.import_config(str(backup))

    assert target.get("ai_model") == "kimi-k3"
    assert target.get_encrypted("ai_api_key") == "sk-round-trip"


def test_import_rejects_bundle_without_data(isolated, work_dir):
    bad = work_dir / "bad.json"
    bad.write_text(json.dumps({"app": "other"}), encoding="utf-8")
    with pytest.raises(ValueError):
        Settings().import_config(str(bad))


class TestBatching:
    """set() 每调用一次就重写整个配置文件，连续改多项要走 batch()。"""

    @staticmethod
    def _count_saves(settings):
        calls = []
        original = settings.save

        def counting_save():
            calls.append(1)
            original()

        settings.save = counting_save
        return calls

    def test_set_alone_writes_each_time(self, isolated):
        s = Settings()
        calls = self._count_saves(s)

        s.set("a", 1)
        s.set("b", 2)
        s.set("c", 3)

        assert len(calls) == 3

    def test_batch_defers_to_a_single_write(self, isolated):
        s = Settings()
        calls = self._count_saves(s)

        with s.batch():
            s.set("a", 1)
            s.set("b", 2)
            s.set("c", 3)
            assert calls == [], "batch 块内不应落盘"

        assert len(calls) == 1

    def test_batch_still_persists_the_values(self, isolated):
        s = Settings()
        with s.batch():
            s.set("ai_model", "batched-model")
            s.set("http_proxy", "http://proxy:1")

        assert Settings().get("ai_model") == "batched-model"
        assert Settings().get("http_proxy") == "http://proxy:1"

    def test_writes_after_batch_are_immediate_again(self, isolated):
        s = Settings()
        with s.batch():
            s.set("a", 1)
        calls = self._count_saves(s)

        s.set("b", 2)

        assert len(calls) == 1

    def test_encrypted_writes_are_batched_too(self, isolated):
        s = Settings()
        calls = self._count_saves(s)

        with s.batch():
            s.set_encrypted("ai_api_key", "sk-secret")
            s.set("ai_model", "m")

        assert len(calls) == 1
        assert s.get_encrypted("ai_api_key") == "sk-secret"

    def test_exception_inside_batch_still_saves(self, isolated):
        """块内出错时那些改动已经生效，不落盘反而会丢数据。"""
        s = Settings()
        with pytest.raises(RuntimeError):
            with s.batch():
                s.set("a", 1)
                raise RuntimeError("boom")

        assert Settings().get("a") == 1

    def test_nested_batches_write_once(self, isolated):
        s = Settings()
        calls = self._count_saves(s)

        with s.batch():
            s.set("a", 1)
            with s.batch():
                s.set("b", 2)
            assert calls == [], "内层结束不应提前落盘"
            s.set("c", 3)

        assert len(calls) == 1
        assert Settings().get("b") == 2

    def test_batch_is_reusable(self, isolated):
        s = Settings()
        for value in range(3):
            with s.batch():
                s.set("n", value)

        assert Settings().get("n") == 2
        assert getattr(s, "_defer_save", 0) == 0


class TestCipherCache:
    def test_repeated_encryption_does_not_reread_the_key_file(self, isolated, monkeypatch):
        reads = []
        original = settings_module.KEY_FILE.__class__.read_bytes

        def counting_read_bytes(self):
            reads.append(self.name)
            return original(self)

        monkeypatch.setattr(settings_module.KEY_FILE.__class__, "read_bytes", counting_read_bytes)

        s = Settings()
        with s.batch():
            for i in range(5):
                s.set_encrypted(f"k{i}", "v")

        assert len(reads) <= 1, f"密钥被反复读取: {reads}"

    def test_import_config_invalidates_the_cache(self, isolated, work_dir):
        """导入的备份带着另一把密钥，缓存不作废就会全部解密失败。"""
        source = Settings()
        source.set_encrypted("ai_api_key", "sk-original")
        backup = work_dir / "backup.json"
        source.export_config(str(backup))

        target = Settings()
        target.import_config(str(backup))

        assert target.get_encrypted("ai_api_key") == "sk-original"
