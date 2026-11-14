from bunker.paths import BunkerPaths
from bunker.sync.package import package_airgap_sync


def test_package_raises_without_signing_key(tmp_path) -> None:
    cfg = {"bunker": {"data_root": "data", "cache_root": "cache", "sync_root": "."}}
    paths = BunkerPaths.from_config(tmp_path, cfg)
    paths.ensure()
    try:
        package_airgap_sync(paths)
        raise AssertionError("expected FileNotFoundError")
    except FileNotFoundError as exc:
        assert "keygen" in str(exc)