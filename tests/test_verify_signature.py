from bunker.crypto.signing import KeyPair, load_private_key, load_public_key
from bunker.sync.manifest import ManifestBuilder
from bunker.sync.verify import verify_sync_folder


def test_verify_rejects_wrong_public_key(tmp_path) -> None:
    pair_a = KeyPair.generate()
    pair_b = KeyPair.generate()
    priv_a = tmp_path / "a.pem"
    pub_b = tmp_path / "b.pub.pem"
    pair_a.save(priv_a, tmp_path / "a.pub.pem")
    pair_b.save(tmp_path / "b.pem", pub_b)

    sync = tmp_path / "bundle"
    sync.mkdir()
    f = sync / "x.parquet"
    f.write_bytes(b"p")
    ManifestBuilder(sync).build([f], private_key=load_private_key(priv_a))

    ok, errs = verify_sync_folder(
        sync,
        public_key=load_public_key(pub_b),
        require_signature=True,
    )
    assert not ok
    assert any("invalid manifest signature" in e for e in errs)