from bunker.sync.manifest import ManifestBuilder, sha256_file
from bunker.sync.verify import verify_sync_folder


def test_verify_sync_folder_passes(tmp_path) -> None:
    sync = tmp_path / "bundle"
    sync.mkdir()
    f = sync / "data.parquet"
    f.write_bytes(b"PAR1-demo")
    ManifestBuilder(sync).build([f])
    ok, errs = verify_sync_folder(sync)
    assert ok, errs


def test_verify_detects_tamper(tmp_path) -> None:
    sync = tmp_path / "bundle"
    sync.mkdir()
    f = sync / "data.parquet"
    f.write_bytes(b"original")
    ManifestBuilder(sync).build([f])
    f.write_bytes(b"tampered")
    ok, errs = verify_sync_folder(sync)
    assert not ok
    assert any("hash mismatch" in e for e in errs)