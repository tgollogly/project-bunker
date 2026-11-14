import os
from pathlib import Path

import pytest

_BUNKER_ENV_EXACT = frozenset(
    {
        "BUNKER_DATA_KEY",
        "BUNKER_DATA_KEY_NEW",
        "BUNKER_MESH_KEY",
        "BUNKER_SMS_TO",
        "BUNKER_SP_DRIVE_ID",
    }
)
_BUNKER_ENV_PREFIXES = ("BUNKER_GRAPH_", "BUNKER_MATRIX_", "BUNKER_TWILIO_")


@pytest.fixture(autouse=True)
def isolate_bunker_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ignore shell BUNKER_* exports so tests only see env they set explicitly."""
    for key in list(os.environ):
        if key in _BUNKER_ENV_EXACT or key.startswith(_BUNKER_ENV_PREFIXES):
            monkeypatch.delenv(key, raising=False)
from cryptography.fernet import Fernet

from bunker.continuity.paths import ContinuityPaths
from bunker.crypto.signing import KeyPair


class FakeGraph:
    def get(self, path: str, **kwargs: object) -> dict:
        if "calendarView" in path:
            return {
                "value": [
                    {
                        "id": "e1",
                        "subject": "Stand-up",
                        "start": {"dateTime": "2026-11-15T09:00:00"},
                        "end": {"dateTime": "2026-11-15T09:30:00"},
                        "organizer": {"emailAddress": {"name": "Team"}},
                        "location": {"displayName": "Room A"},
                    }
                ]
            }
        if "contacts" in path:
            return {
                "value": [
                    {"id": "c1", "displayName": "Alex", "emailAddresses": [{"address": "a@x.com"}]}
                ]
            }
        return {"value": []}

    def get_bytes(self, path: str) -> bytes:
        return b"runbook"


def continuity_paths(tmp_path: Path) -> ContinuityPaths:
    return ContinuityPaths.from_config(
        tmp_path,
        {"continuity": {"data_root": "data/continuity"}},
    )


@pytest.fixture
def bunker_data_key(monkeypatch: pytest.MonkeyPatch) -> str:
    key = Fernet.generate_key().decode("ascii")
    monkeypatch.setenv("BUNKER_DATA_KEY", key)
    return key


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