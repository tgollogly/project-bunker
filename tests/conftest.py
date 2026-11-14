from pathlib import Path

import pytest

from bunker.crypto.signing import KeyPair


@pytest.fixture
def signing_keys(tmp_path: Path) -> tuple[Path, Path]:
    private = tmp_path / "signing.pem"
    public = tmp_path / "signing.pub.pem"
    KeyPair.generate().save(private, public)
    return private, public


@pytest.fixture
def project_tree(tmp_path: Path, signing_keys: tuple[Path, Path]) -> Path:
    root = tmp_path / "proj"
    root.mkdir()
    (root / "config").mkdir()
    (root / "config" / "sources.yaml").write_text(
        """
bunker:
  data_root: data
  cache_root: cache
  sync_root: .
sources: []
""",
        encoding="utf-8",
    )
    priv, pub = signing_keys
    key_dir = root / "data" / "keys"
    key_dir.mkdir(parents=True)
    key_dir.joinpath("signing.pem").write_bytes(priv.read_bytes())
    key_dir.joinpath("signing.pub.pem").write_bytes(pub.read_bytes())
    (root / "data").mkdir(exist_ok=True)
    return root