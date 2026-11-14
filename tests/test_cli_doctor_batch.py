from __future__ import annotations

import json
import stat
from pathlib import Path

import pytest
from click.testing import CliRunner

from bunker.cli import main


@pytest.fixture
def continuity_tree(project_tree: Path) -> Path:
    (project_tree / "config" / "continuity.yaml").write_text(
        """
continuity:
  data_root: data/continuity
  require_encryption: false
  watch:
    probe_hosts:
      - name: outlook
        url: https://example.com
""",
        encoding="utf-8",
    )
    priv = project_tree / "data" / "keys" / "signing.pem"
    priv.chmod(stat.S_IRUSR | stat.S_IWUSR)
    return project_tree


def test_cli_doctor_exit_code(continuity_tree: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(continuity_tree)
    monkeypatch.delenv("BUNKER_GRAPH_ACCESS_TOKEN", raising=False)
    runner = CliRunner()
    result = runner.invoke(main, ["doctor"])
    assert result.exit_code == 1
    assert "FAIL:" in result.output


def test_cli_continuity_status(
    continuity_tree: Path, bunker_data_key: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(continuity_tree)
    runner = CliRunner()
    result = runner.invoke(main, ["continuity", "status"])
    assert result.exit_code == 0
    json.loads(result.output)  # may be [] when nothing synced yet


def test_cli_watch(continuity_tree: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(continuity_tree)

    class Resp:
        status_code = 200

    class Client:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return None

        def get(self, url):
            return Resp()

    import httpx

    monkeypatch.setattr(httpx, "Client", lambda **k: Client())
    runner = CliRunner()
    result = runner.invoke(main, ["watch"])
    assert result.exit_code == 0
    body = json.loads(result.output)
    assert "state" in body


def test_cli_query_no_rows(project_tree: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from bunker.ingest.parquet_writer import write_rows_parquet_duckdb

    monkeypatch.chdir(project_tree)
    part = project_tree / "data" / "parquet" / "ingest_date=2026-11-14" / "part-0.parquet"
    part.parent.mkdir(parents=True, exist_ok=True)
    write_rows_parquet_duckdb([{"id": 99}], part)
    runner = CliRunner()
    result = runner.invoke(main, ["query", "SELECT id FROM bunker_data"])
    assert result.exit_code == 0
    assert "99" in result.output