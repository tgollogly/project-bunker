from __future__ import annotations

from pathlib import Path

from conftest import FakeGraph

from bunker.continuity.config import load_continuity_config
from bunker.continuity.graph.sync_calendars import sync_calendars
from bunker.continuity.graph.sync_contacts import sync_contacts
from bunker.continuity.parquet_io import iter_encrypted_parquet_files, query_rows_from_root
from bunker.continuity.paths import ContinuityPaths
from bunker.continuity.seed_sample import seed_sample_data


def test_seed_sample_three_times_no_duplicates(tmp_path: Path, bunker_data_key: str) -> None:
    (tmp_path / "config").mkdir(parents=True, exist_ok=True)
    (tmp_path / "config" / "continuity.yaml").write_text(
        "continuity:\n  data_root: data/continuity\n  require_encryption: true\n",
        encoding="utf-8",
    )
    cfg = load_continuity_config(tmp_path / "config" / "continuity.yaml")
    paths = ContinuityPaths.from_config(tmp_path, cfg)
    for _ in range(3):
        out = seed_sample_data(paths)
        assert out["calendar_events"] == 2
        assert out["contacts"] == 2
    cal_files = iter_encrypted_parquet_files(paths.parquet_root / "m365" / "calendar")
    assert len(cal_files) == 1
    rows = query_rows_from_root(
        paths.parquet_root / "m365" / "calendar",
        ["id", "subject"],
        order_by="start",
        limit=50,
        continuity_root=paths.continuity_root,
    )
    assert len(rows) == 2


def test_graph_sync_twice_no_duplicate_rows(tmp_path: Path, bunker_data_key: str) -> None:
    paths = ContinuityPaths.from_config(
        tmp_path,
        {"continuity": {"data_root": "data/continuity"}},
    )
    client = FakeGraph()
    sync_calendars(paths, client, horizon_days=7)
    sync_calendars(paths, client, horizon_days=7)
    sync_contacts(paths, client)
    sync_contacts(paths, client)
    cal = query_rows_from_root(
        paths.parquet_root / "m365" / "calendar",
        ["id"],
        order_by="start",
        limit=50,
        continuity_root=paths.continuity_root,
    )
    contacts = query_rows_from_root(
        paths.parquet_root / "m365" / "contacts",
        ["id"],
        order_by="display_name",
        limit=50,
        continuity_root=paths.continuity_root,
    )
    assert len(cal) == 1
    assert len(contacts) == 1