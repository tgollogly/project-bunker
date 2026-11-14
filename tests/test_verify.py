from bunker.crypto.signing import load_private_key, load_public_key
from bunker.sync.manifest import ManifestBuilder
from bunker.sync.verify import verify_sync_folder


def test_verify_sync_folder_passes(tmp_path, signing_keys) -> None:
    private_path, public_path = signing_keys
    sync = tmp_path / "bundle"
    sync.mkdir()
    f = sync / "data.parquet"
    f.write_bytes(b"PAR1-demo")
    ManifestBuilder(sync).build([f], private_key=load_private_key(private_path))
    ok, errs = verify_sync_folder(
        sync,
        public_key=load_public_key(public_path),
        require_signature=True,
    )
    assert ok, errs


def test_verify_detects_tamper(tmp_path, signing_keys) -> None:
    private_path, public_path = signing_keys
    sync = tmp_path / "bundle"
    sync.mkdir()
    f = sync / "data.parquet"
    f.write_bytes(b"original")
    ManifestBuilder(sync).build([f], private_key=load_private_key(private_path))
    f.write_bytes(b"tampered")
    ok, errs = verify_sync_folder(
        sync,
        public_key=load_public_key(public_path),
        require_signature=True,
    )
    assert not ok
    assert any("hash mismatch" in e for e in errs)


def test_verify_extra_file_in_bundle(tmp_path, signing_keys) -> None:
    private_path, public_path = signing_keys
    sync = tmp_path / "bundle"
    sync.mkdir()
    f = sync / "data.parquet"
    f.write_bytes(b"PAR1")
    ManifestBuilder(sync).build([f], private_key=load_private_key(private_path))
    (sync / "evil.bin").write_bytes(b"x")
    ok, errs = verify_sync_folder(
        sync,
        public_key=load_public_key(public_path),
        require_signature=True,
    )
    assert not ok
    assert any("unlisted files" in e for e in errs)


def test_verify_unsigned_bundle(tmp_path) -> None:
    sync = tmp_path / "bundle"
    sync.mkdir()
    f = sync / "data.parquet"
    f.write_bytes(b"PAR1")
    ManifestBuilder(sync).build([f])
    ok, errs = verify_sync_folder(sync, require_signature=True)
    assert not ok
    assert any("missing manifest signature" in e for e in errs)