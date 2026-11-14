from __future__ import annotations

from pathlib import Path

from bunker.crypto.signing import KeyPair


def default_key_dir(root: Path) -> Path:
    return root / "data" / "keys"


def keygen(root: Path, force: bool = False) -> tuple[Path, Path]:
    key_dir = default_key_dir(root)
    private_path = key_dir / "signing.pem"
    public_path = key_dir / "signing.pub.pem"
    if private_path.exists() and not force:
        raise FileExistsError(f"Keys already exist at {key_dir}; use --force to replace")
    pair = KeyPair.generate()
    pair.save(private_path, public_path)
    return private_path, public_path