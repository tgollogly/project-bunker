import json
import sys
from pathlib import Path

import pytest
from click.testing import CliRunner

from bunker.cli import main
from bunker.crypto.signing import load_private_key
from bunker.ingest.parquet_writer import write_rows_parquet_duckdb
from bunker.sync.manifest import ManifestBuilder

USGS_SAMPLE = b"""{
  "features": [{
    "id": "evt1",
    "properties": {"mag": 2.1, "place": "Test"},
    "geometry": {"coordinates": [0, 0, 1]}
  }]
}"""


def test_cli_sync_requires_keys(project_tree, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(project_tree)
    (project_tree / "data" / "keys" / "signing.pem").unlink()
    runner = CliRunner()
    result = runner.invoke(main, ["sync-package"])
    assert result.exit_code == 1


def test_cli_import_sync(project_tree, signing_keys, monkeypatch: pytest.MonkeyPatch) -> None:
    from bunker.crypto.signing import load_private_key
    from bunker.ingest.parquet_writer import write_rows_parquet_duckdb
    from bunker.sync.manifest import ManifestBuilder

    monkeypatch.chdir(project_tree)
    bundle = project_tree / "b"
    shards = bundle / "shards"
    shards.mkdir(parents=True)
    part = shards / "x.parquet"
    write_rows_parquet_duckdb([{"id": 1, "_bunker_ingested_at": "t"}], part)
    ManifestBuilder(bundle).build([part], private_key=load_private_key(signing_keys[0]))

    runner = CliRunner()
    result = runner.invoke(
        main,
        ["import-sync", str(bundle), "--public-key", "data/keys/signing.pub.pem"],
    )
    assert result.exit_code == 0, result.output
    body = json.loads(result.output)
    assert body["imported_shards"] == 1


def test_cli_ingest_offline(project_tree: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cache = project_tree / "cache"
    cache.mkdir(exist_ok=True)
    (cache / "demo.bin").write_bytes(USGS_SAMPLE)
    (cache / "demo.meta.json").write_text('{"fetched_at": 1}', encoding="utf-8")
    (project_tree / "config" / "sources.yaml").write_text(
        """
bunker:
  data_root: data
  cache_root: cache
  sync_root: .
sources:
  - id: demo
    url: https://example.invalid
    parser: usgs_earthquakes_day
    primary_key: _feature_id
    parquet_partition: demo/part
""",
        encoding="utf-8",
    )
    monkeypatch.chdir(project_tree)
    runner = CliRunner()
    result = runner.invoke(main, ["ingest", "--source", "demo", "--offline"])
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["row_count"] == 1


def test_cli_ingest_all_logs_failure(project_tree: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (project_tree / "config" / "sources.yaml").write_text(
        """
bunker:
  data_root: data
  cache_root: cache
  sync_root: .
sources:
  - id: bad
    url: https://example.invalid/nope
    parser: usgs_earthquakes_day
""",
        encoding="utf-8",
    )
    monkeypatch.chdir(project_tree)
    runner = CliRunner()
    result = runner.invoke(main, ["ingest-all", "--offline"])
    assert result.exit_code == 0
    assert result.output.strip() == "[]"


def test_cli_sync_package_success(project_tree: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import os
    import stat

    os.chmod(
        project_tree / "data" / "keys" / "signing.pem",
        stat.S_IRUSR | stat.S_IWUSR,
    )
    part = project_tree / "data" / "parquet" / "x" / "ingest_date=2026-11-14" / "part-0.parquet"
    part.parent.mkdir(parents=True)
    write_rows_parquet_duckdb([{"id": 1, "_bunker_ingested_at": "t"}], part)
    monkeypatch.chdir(project_tree)
    runner = CliRunner()
    result = runner.invoke(main, ["sync-package"])
    assert result.exit_code == 0, result.output
    assert "bunker_sync_" in result.output


def test_cli_import_sync_rejects_bad_bundle(
    project_tree: Path, signing_keys: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(project_tree)
    bundle = project_tree / "b"
    bundle.mkdir()
    (bundle / "manifest.json").write_text("{}", encoding="utf-8")
    runner = CliRunner()
    result = runner.invoke(
        main,
        ["import-sync", str(bundle), "--public-key", "data/keys/signing.pub.pem"],
    )
    assert result.exit_code == 1


def test_cli_keygen_refuses_overwrite(project_tree: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(project_tree)
    runner = CliRunner()
    result = runner.invoke(main, ["keygen"])
    assert result.exit_code == 1
    assert "already exist" in result.output.lower()


def test_cli_verify_sync_failure(project_tree: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(project_tree)
    bundle = project_tree / "bundle"
    bundle.mkdir()
    (bundle / "manifest.json").write_text('{"files": []}', encoding="utf-8")
    runner = CliRunner()
    result = runner.invoke(
        main,
        ["verify-sync", str(bundle), "--public-key", "data/keys/signing.pub.pem"],
    )
    assert result.exit_code == 1
    assert "ERROR:" in result.output


def test_cli_query_empty_result(project_tree: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    part = project_tree / "data" / "parquet" / "ingest_date=2026-11-14" / "part-0.parquet"
    part.parent.mkdir(parents=True)
    write_rows_parquet_duckdb([{"id": 1, "_bunker_ingested_at": "t"}], part)
    monkeypatch.chdir(project_tree)
    runner = CliRunner()
    result = runner.invoke(main, ["query", "SELECT id FROM bunker_data WHERE id < 0"])
    assert result.exit_code == 0
    assert "(no rows)" in result.output


def test_cli_continuity_rekey_missing_env(
    project_tree: Path, bunker_data_key: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    (project_tree / "config" / "continuity.yaml").write_text(
        "continuity:\n  data_root: data/continuity\n",
        encoding="utf-8",
    )
    monkeypatch.chdir(project_tree)
    monkeypatch.delenv("BUNKER_DATA_KEY_NEW", raising=False)
    runner = CliRunner()
    result = runner.invoke(main, ["continuity", "rekey"])
    assert result.exit_code == 1
    assert "BUNKER_DATA_KEY_NEW" in result.output


def test_cli_serve_non_loopback_warnings(
    project_tree: Path, bunker_data_key: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    from bunker.continuity.serve.auth import save_password_hash

    (project_tree / "config" / "continuity.yaml").write_text(
        "continuity:\n  data_root: data/continuity\n",
        encoding="utf-8",
    )
    cont = project_tree / "data" / "continuity"
    cont.mkdir(parents=True)
    save_password_hash(cont / "serve_auth.json", "secret")
    monkeypatch.chdir(project_tree)

    def fake_run(*_a, **_k):
        return None

    monkeypatch.setattr("uvicorn.run", fake_run)
    runner = CliRunner()
    result = runner.invoke(main, ["serve", "--host", "0.0.0.0", "--port", "19999"])
    assert result.exit_code == 0
    assert "cleartext" in result.output.lower()


def test_cli_serve_tls_message(
    project_tree: Path, bunker_data_key: str, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import NameOID

    from bunker.continuity.serve.auth import save_password_hash

    (project_tree / "config" / "continuity.yaml").write_text(
        "continuity:\n  data_root: data/continuity\n",
        encoding="utf-8",
    )
    cont = project_tree / "data" / "continuity"
    cont.mkdir(parents=True)
    save_password_hash(cont / "serve_auth.json", "secret")
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    cert_path = tmp_path / "cert.pem"
    key_path = tmp_path / "key.pem"
    key_path.write_bytes(
        key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )
    subject = issuer = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "localhost")])
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(__import__("datetime").datetime.now(__import__("datetime").timezone.utc))
        .not_valid_after(
            __import__("datetime").datetime.now(__import__("datetime").timezone.utc)
            + __import__("datetime").timedelta(days=1)
        )
        .sign(key, hashes.SHA256())
    )
    cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    monkeypatch.chdir(project_tree)
    monkeypatch.setattr("uvicorn.run", lambda *_a, **_k: None)
    runner = CliRunner()
    result = runner.invoke(
        main,
        [
            "serve",
            "--host",
            "0.0.0.0",
            "--port",
            "19998",
            "--certfile",
            str(cert_path),
            "--keyfile",
            str(key_path),
        ],
    )
    assert result.exit_code == 0
    assert "TLS enabled" in result.output


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX-only private key mode check")
def test_load_private_key_rejects_world_readable(
    project_tree: Path, signing_keys: tuple[Path, Path]
) -> None:
    import os
    import stat

    priv = project_tree / "data" / "keys" / "signing.pem"
    os.chmod(priv, stat.S_IRUSR | stat.S_IWUSR | stat.S_IROTH)
    with pytest.raises(PermissionError):
        load_private_key(priv)


def test_verify_missing_manifest_file(tmp_path: Path, signing_keys: tuple[Path, Path]) -> None:
    from bunker.crypto.signing import load_private_key, load_public_key
    from bunker.sync.verify import verify_sync_folder

    sync = tmp_path / "bundle"
    sync.mkdir()
    f = sync / "listed.parquet"
    f.write_bytes(b"PAR1")
    priv, pub = signing_keys
    ManifestBuilder(sync).build([f], private_key=load_private_key(priv))
    f.unlink()
    ok, errs = verify_sync_folder(sync, public_key=load_public_key(pub), require_signature=True)
    assert not ok
    assert any("missing file" in e for e in errs)