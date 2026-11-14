from __future__ import annotations

import stat
from pathlib import Path

import pytest

from bunker.doctor import run_doctor


def test_doctor_passes_on_healthy_tree(
    project_tree: Path, bunker_data_key: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    (project_tree / "config" / "continuity.yaml").write_text(
        """
continuity:
  data_root: data/continuity
  probe_hosts:
    - name: outlook
      url: https://outlook.office365.com
""",
        encoding="utf-8",
    )
    priv = project_tree / "data" / "keys" / "signing.pem"
    priv.chmod(stat.S_IRUSR | stat.S_IWUSR)
    monkeypatch.chdir(project_tree)
    monkeypatch.setenv("BUNKER_GRAPH_ACCESS_TOKEN", "test-token")
    results = run_doctor()
    failed = [r for r in results if not r.passed and r.name != "graph reachability"]
    assert not failed, [f"{r.name}: {r.detail}" for r in failed]


def test_doctor_fails_without_signing_key(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = tmp_path / "p"
    root.mkdir()
    (root / "config").mkdir()
    (root / "config" / "sources.yaml").write_text(
        "bunker:\n  data_root: data\nsources: []\n", encoding="utf-8"
    )
    (root / "config" / "continuity.yaml").write_text(
        "continuity:\n  data_root: data/continuity\n  watch:\n    probe_hosts: []\n",
        encoding="utf-8",
    )
    (root / "data").mkdir()
    monkeypatch.chdir(root)
    names = {r.name: r.passed for r in run_doctor()}
    assert names["signing key"] is False


def test_doctor_warns_loose_key_permissions(
    project_tree: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pytest.importorskip("posix")
    priv = project_tree / "data" / "keys" / "signing.pem"
    priv.chmod(stat.S_IRUSR | stat.S_IRGRP)
    (project_tree / "config" / "continuity.yaml").write_text(
        """
continuity:
  data_root: data/continuity
  watch:
    probe_hosts:
      - name: outlook
        url: https://example.com
""",
        encoding="utf-8",
    )
    monkeypatch.chdir(project_tree)
    signing = next(r for r in run_doctor() if r.name == "signing key")
    assert signing.passed is False


def test_cli_doctor_invocation(project_tree: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (project_tree / "config" / "continuity.yaml").write_text(
        """
continuity:
  data_root: data/continuity
  watch:
    probe_hosts:
      - name: outlook
        url: https://example.com
""",
        encoding="utf-8",
    )
    monkeypatch.chdir(project_tree)
    monkeypatch.setenv("BUNKER_GRAPH_ACCESS_TOKEN", "tok")
    from click.testing import CliRunner

    from bunker.cli import main

    runner = CliRunner()
    result = runner.invoke(main, ["doctor"])
    assert "PASS:" in result.output or "FAIL:" in result.output