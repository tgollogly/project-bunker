from pathlib import Path

import pytest
from conftest import continuity_paths as _paths
from cryptography.fernet import Fernet

from bunker.continuity.encryption import (
    RekeyAbortError,
    decrypt_at_rest,
    decrypt_with_fernet,
    encrypt_at_rest,
    fernet_from_raw,
    rekey_tree,
)
from bunker.continuity.serve.auth import (
    ServeAuthConfig,
    login_attempts_path,
)


def _write_three_blobs(paths, key: str, monkeypatch) -> tuple[Path, Path, Path]:
    monkeypatch.setenv("BUNKER_DATA_KEY", key)
    a = paths.continuity_root / "meta/a.json"
    b = paths.continuity_root / "meta/b.json"
    c = paths.continuity_root / "meta/c.json"
    for p, label in ((a, b"a"), (b, b"b"), (c, b"c")):
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(encrypt_at_rest(label, continuity_root=paths.continuity_root))
    return a, b, c


def test_rekey_atomic_survives_midway_abort(tmp_path: Path, monkeypatch) -> None:
    paths = _paths(tmp_path)
    old = Fernet.generate_key().decode()
    new = Fernet.generate_key().decode()
    a, b, c = _write_three_blobs(paths, old, monkeypatch)
    old_fernet = fernet_from_raw(old, continuity_root=paths.continuity_root)

    monkeypatch.setenv("BUNKER_DATA_KEY_NEW", new)

    def bail_after_two(path: Path, index: int, total: int) -> None:
        if index >= 2:
            raise RekeyAbortError("simulated crash")

    with pytest.raises(RekeyAbortError):
        rekey_tree(paths.continuity_root, on_file_rekeyed=bail_after_two)

    new_fernet = fernet_from_raw(new, continuity_root=paths.continuity_root)
    decrypt_with_fernet(a.read_bytes(), new_fernet)
    decrypt_with_fernet(b.read_bytes(), new_fernet)
    decrypt_with_fernet(c.read_bytes(), old_fernet)
    for p in (a, b, c):
        assert not (p.with_suffix(p.suffix + ".tmp")).exists()


def test_login_rate_limit_persists_across_config_reload(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    rate_path = login_attempts_path(paths.continuity_root)
    auth_path = paths.continuity_root / "serve_auth.json"
    auth_path.parent.mkdir(parents=True, exist_ok=True)
    auth_path.write_text("{}", encoding="utf-8")

    auth1 = ServeAuthConfig(auth_path=auth_path, rate_limit_path=rate_path)
    for _ in range(10):
        auth1.record_failed_login("198.51.100.7")
    assert not auth1.check_login_allowed("198.51.100.7")

    auth2 = ServeAuthConfig(auth_path=auth_path, rate_limit_path=rate_path)
    assert not auth2.check_login_allowed("198.51.100.7")
    assert rate_path.is_file()
    import sys

    if sys.platform != "win32":
        assert oct(rate_path.stat().st_mode & 0o777) == oct(0o600)


def test_rekey_completes_and_reads_with_new_key(tmp_path: Path, monkeypatch) -> None:
    paths = _paths(tmp_path)
    old = Fernet.generate_key().decode()
    new = Fernet.generate_key().decode()
    blob_path = paths.continuity_root / "meta/one.json"
    blob_path.parent.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("BUNKER_DATA_KEY", old)
    blob_path.write_bytes(encrypt_at_rest(b"data", continuity_root=paths.continuity_root))
    monkeypatch.setenv("BUNKER_DATA_KEY_NEW", new)
    count = rekey_tree(paths.continuity_root)
    assert count == 1
    monkeypatch.setenv("BUNKER_DATA_KEY", new)
    assert decrypt_at_rest(blob_path.read_bytes(), continuity_root=paths.continuity_root) == b"data"