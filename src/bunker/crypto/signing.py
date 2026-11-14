from __future__ import annotations

import base64
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)


@dataclass
class KeyPair:
    private_key: Ed25519PrivateKey
    public_key: Ed25519PublicKey

    @classmethod
    def generate(cls) -> KeyPair:
        private_key = Ed25519PrivateKey.generate()
        return cls(private_key=private_key, public_key=private_key.public_key())

    def save(self, private_path: Path, public_path: Path) -> None:
        private_path.parent.mkdir(parents=True, exist_ok=True)
        private_path.write_bytes(
            self.private_key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.PKCS8,
                encryption_algorithm=serialization.NoEncryption(),
            )
        )
        public_path.write_bytes(
            self.public_key.public_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PublicFormat.SubjectPublicKeyInfo,
            )
        )


def load_private_key(path: Path) -> Ed25519PrivateKey:
    data = path.read_bytes()
    key = serialization.load_pem_private_key(data, password=None)
    if not isinstance(key, Ed25519PrivateKey):
        raise TypeError("Expected Ed25519 private key PEM")
    return key


def load_public_key(path: Path) -> Ed25519PublicKey:
    data = path.read_bytes()
    key = serialization.load_pem_public_key(data)
    if not isinstance(key, Ed25519PublicKey):
        raise TypeError("Expected Ed25519 public key PEM")
    return key


def canonical_manifest_bytes(payload: dict[str, Any]) -> bytes:
    """Deterministic JSON for signing (excludes signature field)."""
    signable = {k: v for k, v in payload.items() if k != "signature"}
    return json.dumps(signable, sort_keys=True, separators=(",", ":")).encode("utf-8")


def sign_manifest_payload(
    payload: dict[str, Any],
    private_key: Ed25519PrivateKey,
) -> str:
    sig = private_key.sign(canonical_manifest_bytes(payload))
    return base64.b64encode(sig).decode("ascii")


def verify_manifest_signature(
    payload: dict[str, Any],
    signature_b64: str,
    public_key: Ed25519PublicKey,
) -> bool:
    try:
        sig = base64.b64decode(signature_b64.encode("ascii"))
        public_key.verify(sig, canonical_manifest_bytes(payload))
        return True
    except Exception:
        return False