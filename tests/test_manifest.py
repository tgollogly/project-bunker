from pathlib import Path

from bunker.crypto.signing import (
    load_private_key,
    load_public_key,
    verify_manifest_signature,
)
from bunker.sync.bundle_format import BUNDLE_FORMAT_VERSION
from bunker.sync.manifest import ManifestBuilder, sha256_file


def test_sha256_file(tmp_path: Path) -> None:
    f = tmp_path / "x.bin"
    f.write_bytes(b"bunker")
    assert len(sha256_file(f)) == 64


def test_signed_manifest_v2(tmp_path: Path, signing_keys: tuple[Path, Path]) -> None:
    private_path, public_path = signing_keys
    sync = tmp_path / "bunker_sync_2099-01-01"
    sync.mkdir()
    shard = sync / "shards"
    shard.mkdir()
    f = shard / "demo.parquet"
    f.write_bytes(b"PAR1")
    m = ManifestBuilder(sync).build([f], private_key=load_private_key(private_path))
    assert m["bundle_format_version"] == BUNDLE_FORMAT_VERSION
    assert m["signature"]
    pub = load_public_key(public_path)
    assert verify_manifest_signature(m, m["signature"], pub)
    assert (sync / "manifest.json").is_file()