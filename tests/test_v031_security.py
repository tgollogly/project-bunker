from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner
from conftest import continuity_paths as _paths
from fastapi.testclient import TestClient

from bunker import cli as bunker_cli
from bunker.continuity.encryption import (
    EncryptionRequiredError,
    decrypt_at_rest,
    encrypt_at_rest,
    ensure_encryption_key,
)
from bunker.continuity.graph.auth import MsalTokenProvider
from bunker.continuity.graph.client import HttpxGraphClient
from bunker.continuity.graph.sync_calendars import sync_calendars
from bunker.continuity.serve.app import create_app
from bunker.continuity.serve.auth import (
    ServeAuthConfig,
    auth_configured,
    login_attempts_path,
    save_password_hash,
)
from bunker.continuity.watch.health import (
    HealthState,
    ProbeState,
    WatchConfig,
    evaluate_watch,
    load_watch_state,
    probe_url,
    unhealthy_watched_services,
)
from bunker.crypto.signing import KeyPair, load_private_key


def test_probe_url_401_is_up() -> None:
    from unittest.mock import MagicMock, patch

    with patch("httpx.Client") as mock_client:
        inst = mock_client.return_value.__enter__.return_value
        inst.get.return_value = MagicMock(status_code=401)
        assert probe_url("https://example.com") == ProbeState.UP


def test_graph_health_interruption_degrades_then_down() -> None:
    cfg = WatchConfig(
        probe_hosts=[],
        degraded_after_failures=1,
        down_after_failures=2,
        recovery_after_successes=2,
    )
    prev = load_watch_state(Path("/nonexistent"))
    prev = evaluate_watch(
        cfg,
        probe_results={},
        graph_reachable=True,
        graph_service_unhealthy=True,
        prev=prev,
    )
    assert prev.state == HealthState.DEGRADED
    prev = evaluate_watch(
        cfg,
        probe_results={},
        graph_reachable=True,
        graph_service_unhealthy=True,
        prev=prev,
    )
    assert prev.state == HealthState.DOWN


def test_unhealthy_watched_services_filters() -> None:
    overviews = [
        {"service": "Exchange Online", "status": "serviceInterruption"},
        {"service": "Microsoft Teams", "status": "serviceOperational"},
    ]
    bad = unhealthy_watched_services(overviews, ["Exchange Online", "Microsoft Teams"])
    assert bad == ["Exchange Online"]


def test_msal_token_refreshes_when_expired() -> None:
    calls = {"n": 0}
    clock = {"t": 1000.0}

    def fake_clock() -> float:
        return clock["t"]

    class FakeApp:
        def acquire_token_silent(self, scopes, account=None):  # type: ignore[no-untyped-def]
            return None

        def acquire_token_for_client(self, scopes):  # type: ignore[no-untyped-def]
            calls["n"] += 1
            return {"access_token": f"tok{calls['n']}", "expires_in": 3600}

    settings = __import__(
        "bunker.continuity.graph.auth", fromlist=["GraphAuthSettings"]
    ).GraphAuthSettings(tenant_id="t", client_id="c", client_secret="s")
    with patch("msal.ConfidentialClientApplication", return_value=FakeApp()):
        provider = MsalTokenProvider(settings, clock=fake_clock)
        assert provider.get_token() == "tok1"
        clock["t"] += 4000
        assert provider.get_token() == "tok2"


def test_graph_client_retries_once_on_401() -> None:
    import httpx

    provider = MagicMock()
    provider.get_token.side_effect = ["bad", "good", "good"]

    req = httpx.Request("GET", "https://graph.microsoft.com/v1.0/x")
    ok = httpx.Response(200, json={"value": []}, request=req)
    unauthorized = httpx.Response(401, request=req)

    http_calls = {"n": 0}

    class FakeClient:
        def __init__(self, *args, **kwargs) -> None:
            pass

        def __enter__(self) -> FakeClient:
            return self

        def __exit__(self, *args) -> None:
            return None

        def request(self, method, url, headers=None, **kwargs):  # type: ignore[no-untyped-def]
            http_calls["n"] += 1
            if http_calls["n"] == 1:
                return unauthorized
            return ok

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(httpx, "Client", FakeClient)
        client = HttpxGraphClient(provider, max_retries=1)
        out = client.get("/x")
        assert out == {"value": []}
        provider.invalidate_token.assert_called_once()


def test_require_encryption_blocks_sync_without_key(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    with pytest.raises(EncryptionRequiredError):
        ensure_encryption_key({"continuity": {"require_encryption": True}}, paths.continuity_root)


def test_encrypted_parquet_roundtrip(tmp_path: Path, bunker_data_key: str) -> None:
    paths = _paths(tmp_path)
    client = MagicMock()
    client.get.return_value = {
        "value": [
            {
                "id": "1",
                "subject": "x",
                "start": {"dateTime": "2026-11-15T09:00:00"},
                "end": {"dateTime": "2026-11-15T10:00:00"},
            }
        ]
    }
    sync_calendars(paths, client, horizon_days=1)
    parts = list(paths.parquet_root.rglob("*.parquet.enc"))
    assert parts
    raw = parts[0].read_bytes()
    assert not raw.startswith(b"PAR1")
    plain = decrypt_at_rest(raw, continuity_root=paths.continuity_root)
    assert plain.startswith(b"PAR1")


def test_serve_non_loopback_requires_auth(tmp_path: Path, bunker_data_key: str) -> None:
    _paths(tmp_path)
    runner = CliRunner()
    result = runner.invoke(
        bunker_cli.serve,
        ["--host", "0.0.0.0", "--port", "9999"],
        catch_exceptions=False,
    )
    assert result.exit_code != 0
    assert "set-password" in result.output


def test_serve_non_loopback_401_without_session(tmp_path: Path, bunker_data_key: str) -> None:
    paths = _paths(tmp_path)
    auth_path = paths.continuity_root / "serve_auth.json"
    save_password_hash(auth_path, "secret")
    assert auth_configured(auth_path)
    auth = ServeAuthConfig(
        auth_path=auth_path,
        rate_limit_path=login_attempts_path(paths.continuity_root),
    )
    app = create_app(paths, {"continuity": {}}, bind_host="0.0.0.0", auth=auth)
    client = TestClient(app)
    assert client.get("/").status_code == 401


def test_signing_key_permissions_posix(tmp_path: Path) -> None:
    priv = tmp_path / "signing.pem"
    pub = tmp_path / "signing.pub.pem"
    KeyPair.generate().save(priv, pub)
    load_private_key(priv)
    priv.chmod(0o644)
    with pytest.raises(PermissionError):
        load_private_key(priv)


def test_passphrase_derived_key(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    paths = _paths(tmp_path)
    monkeypatch.setenv("BUNKER_DATA_KEY", "long-test-passphrase")
    blob = encrypt_at_rest(b"hello", continuity_root=paths.continuity_root)
    assert decrypt_at_rest(blob, continuity_root=paths.continuity_root) == b"hello"