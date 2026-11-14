import json

import pytest
from click.testing import CliRunner

from bunker.cli import main
from bunker.crypto.signing import load_private_key
from bunker.sync.manifest import ManifestBuilder


def test_cli_status(project_tree, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(project_tree)
    runner = CliRunner()
    result = runner.invoke(main, ["status"])
    assert result.exit_code == 0
    body = json.loads(result.output)
    assert body["total_rows"] == 0


def test_cli_verify_sync(project_tree, signing_keys, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(project_tree)
    bundle = project_tree / "bundle"
    bundle.mkdir()
    shard = bundle / "shards"
    shard.mkdir()
    f = shard / "x.parquet"
    f.write_bytes(b"PAR1")
    ManifestBuilder(bundle).build([f], private_key=load_private_key(signing_keys[0]))

    runner = CliRunner()
    result = runner.invoke(
        main,
        ["verify-sync", str(bundle), "--public-key", "data/keys/signing.pub.pem"],
    )
    assert result.exit_code == 0, result.output


def test_cli_keygen_force(project_tree, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(project_tree)
    runner = CliRunner()
    result = runner.invoke(main, ["keygen", "--force"])
    assert result.exit_code == 0