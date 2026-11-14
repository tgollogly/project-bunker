from pathlib import Path

from click.testing import CliRunner
from conftest import continuity_paths as _paths
from fastapi.testclient import TestClient

from bunker import cli as bunker_cli
from bunker.continuity.encryption import encrypt_at_rest, rekey_tree
from bunker.continuity.serve.app import create_app
from bunker.continuity.serve.auth import ServeAuthConfig, save_password_hash


def test_serve_login_sets_session(tmp_path: Path, bunker_data_key: str) -> None:
    paths = _paths(tmp_path)
    auth_path = paths.continuity_root / "serve_auth.json"
    save_password_hash(auth_path, "secret")
    auth = ServeAuthConfig(auth_path=auth_path)
    app = create_app(paths, {"continuity": {}}, bind_host="10.0.0.1", auth=auth)
    client = TestClient(app)
    assert client.get("/").status_code == 401
    resp = client.post("/login", data={"password": "secret"}, follow_redirects=False)
    assert resp.status_code == 303
    assert client.cookies.get("bunker_session")
    client.cookies.update(resp.cookies)
    assert client.get("/").status_code == 200


def test_cli_serve_set_password(tmp_path: Path, bunker_data_key: str, monkeypatch) -> None:
    root = tmp_path / "proj"
    root.mkdir()
    (root / "config").mkdir()
    cfg = root / "config" / "continuity.yaml"
    cfg.write_text("continuity:\n  data_root: data/continuity\n  require_encryption: false\n")
    (root / "data").mkdir()
    monkeypatch.chdir(root)
    runner = CliRunner()
    result = runner.invoke(bunker_cli.serve, ["set-password"], input="pw\npw\n")
    assert result.exit_code == 0


def test_rekey_rotates_blob(tmp_path: Path, monkeypatch) -> None:
    from cryptography.fernet import Fernet

    paths = _paths(tmp_path)
    old = Fernet.generate_key().decode()
    new = Fernet.generate_key().decode()
    monkeypatch.setenv("BUNKER_DATA_KEY", old)
    blob_path = paths.meta_root / "sample.json"
    blob_path.parent.mkdir(parents=True, exist_ok=True)
    blob_path.write_bytes(encrypt_at_rest(b"data", continuity_root=paths.continuity_root))
    monkeypatch.setenv("BUNKER_DATA_KEY_NEW", new)
    count = rekey_tree(paths.continuity_root)
    assert count >= 1
    monkeypatch.setenv("BUNKER_DATA_KEY", new)
    from bunker.continuity.encryption import decrypt_at_rest

    assert decrypt_at_rest(blob_path.read_bytes(), continuity_root=paths.continuity_root) == b"data"