from pathlib import Path

from bunker.sync.manifest import ManifestBuilder, sha256_file


def test_sha256_file(tmp_path: Path) -> None:
    f = tmp_path / "x.bin"
    f.write_bytes(b"bunker")
    assert len(sha256_file(f)) == 64


def test_manifest_builder(tmp_path: Path) -> None:
    sync = tmp_path / "bunker_sync_2099-01-01"
    sync.mkdir()
    shard = sync / "shards"
    shard.mkdir()
    f = shard / "demo.parquet"
    f.write_bytes(b"PAR1")
    m = ManifestBuilder(sync).build([f])
    assert m["algorithm"] == "sha256"
    assert m["files"][0]["sha256"] == sha256_file(f)
    assert (sync / "manifest.json").is_file()