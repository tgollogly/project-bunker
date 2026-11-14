import io

import pyarrow as pa
import pyarrow.parquet as pq
from conftest import continuity_paths as _paths
from fastapi.testclient import TestClient

from bunker.continuity.encryption import encrypt_at_rest
from bunker.continuity.meta import write_sync_meta
from bunker.continuity.parquet_io import ENCRYPTED_PARQUET_SUFFIX
from bunker.continuity.serve.app import create_app
from bunker.continuity.watch.health import HealthState, WatchState, save_watch_state
from bunker.ingest.parquet_writer import hive_part_path


def _write_malicious_calendar(paths, subject: str, contact_name: str, continuity_root) -> None:
    part_dir = paths.parquet_root / "m365" / "calendar"
    part_dir.mkdir(parents=True, exist_ok=True)
    cal_part = hive_part_path(part_dir)
    cal_part = cal_part.with_suffix(ENCRYPTED_PARQUET_SUFFIX)
    buf = io.BytesIO()
    pq.write_table(
        pa.Table.from_pylist([{"subject": subject, "start": "t1", "end": "t2", "location": ""}]),
        buf,
        compression="zstd",
    )
    cal_part.parent.mkdir(parents=True, exist_ok=True)
    cal_part.write_bytes(encrypt_at_rest(buf.getvalue(), continuity_root=continuity_root))

    contacts_part = hive_part_path(paths.parquet_root / "m365" / "contacts")
    contacts_part = contacts_part.with_suffix(ENCRYPTED_PARQUET_SUFFIX)
    buf2 = io.BytesIO()
    pq.write_table(
        pa.Table.from_pylist([{"display_name": contact_name, "email": "e@x.com", "mobile": ""}]),
        buf2,
        compression="zstd",
    )
    contacts_part.write_bytes(encrypt_at_rest(buf2.getvalue(), continuity_root=continuity_root))


def test_xss_payloads_render_as_text_not_markup(tmp_path, bunker_data_key) -> None:
    paths = _paths(tmp_path)
    xss = '<script>alert(1)</script>'
    xss2 = '"><img src=x onerror=alert(1)>'
    _write_malicious_calendar(paths, xss, xss2, paths.continuity_root)
    write_sync_meta(paths.meta_root, "m365_calendar", continuity_root=paths.continuity_root)
    save_watch_state(
        paths.state_file,
        WatchState(state=HealthState.DOWN, probes={"outlook": False}),
    )
    bad_url = 'javascript:alert(1)'
    app = create_app(paths, {"continuity": {"element_url": bad_url}}, bind_host="127.0.0.1")
    client = TestClient(app)
    home = client.get("/")
    assert home.status_code == 200
    cal = client.get("/calendar")
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in cal.text
    assert "<script>" not in cal.text
    contacts = client.get("/contacts")
    assert "&quot;&gt;&lt;img" in contacts.text or "&gt;&lt;img" in contacts.text
    assert '<img src=x onerror' not in contacts.text
    assert home.headers.get("content-security-policy") == "default-src 'self'"
    assert home.headers.get("x-content-type-options") == "nosniff"
    assert home.headers.get("referrer-policy") == "no-referrer"


def test_element_url_only_http_https(tmp_path, bunker_data_key) -> None:
    paths = _paths(tmp_path)
    cfg = {"continuity": {"element_url": "file:///etc/passwd"}}
    app = create_app(paths, cfg, bind_host="127.0.0.1")
    client = TestClient(app)
    html = client.get("/").text
    assert "file://" not in html
    assert "file://" not in html
    assert "Open backup chat" not in html