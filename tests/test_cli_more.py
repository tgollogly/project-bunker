import json

import pytest
from click.testing import CliRunner

from bunker.cli import main


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