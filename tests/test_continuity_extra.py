from unittest.mock import MagicMock, patch

from conftest import continuity_paths
from fastapi.testclient import TestClient

from bunker.continuity.graph.auth import GraphAuthSettings, MsalTokenProvider
from bunker.continuity.graph.client import HttpxGraphClient
from bunker.continuity.notify.sms import TwilioSmsProvider, build_sms_provider
from bunker.continuity.serve.app import create_app
from bunker.continuity.watch.health import probe_graph_health


def test_msal_token_provider() -> None:
    settings = GraphAuthSettings(
        tenant_id="t",
        client_id="c",
        client_secret="s",
        scopes=["https://graph.microsoft.com/.default"],
    )
    with patch("msal.ConfidentialClientApplication") as app_cls:
        app_cls.return_value.acquire_token_silent.return_value = None
        app_cls.return_value.acquire_token_for_client.return_value = {
            "access_token": "tok",
            "expires_in": 3600,
        }
        prov = MsalTokenProvider(settings)
        assert prov.get_token() == "tok"


def test_probe_graph_health() -> None:
    client = MagicMock()
    client.get.return_value = {"value": []}
    reachable, unhealthy, bad = probe_graph_health(client, watched_services=["Exchange Online"])
    assert reachable is True and unhealthy is False
    client.get.side_effect = RuntimeError("x")
    reachable2, _, _ = probe_graph_health(client, watched_services=[])
    assert reachable2 is False


def test_twilio_sms_mocked() -> None:
    with patch("httpx.Client") as mock_client:
        inst = mock_client.return_value.__enter__.return_value
        inst.post.return_value = MagicMock(status_code=201, raise_for_status=lambda: None)
        TwilioSmsProvider(
            account_sid="sid",
            auth_token="tok",
            from_number="+1000",
            to_number="+2000",
        ).send("alert")


def test_build_twilio_provider_env() -> None:
    with patch.dict(
        "os.environ",
        {
            "BUNKER_TWILIO_ACCOUNT_SID": "sid",
            "BUNKER_TWILIO_AUTH_TOKEN": "tok",
            "BUNKER_TWILIO_FROM": "+1",
            "BUNKER_SMS_TO": "+2",
        },
    ):
        p = build_sms_provider("twilio")
        assert isinstance(p, TwilioSmsProvider)


def test_serve_contacts_and_docs(tmp_path, bunker_data_key) -> None:
    paths = continuity_paths(tmp_path)
    from bunker.continuity.storage import write_encrypted_file

    write_encrypted_file(
        paths.docs_root / "runbooks" / "r.txt",
        b"doc",
        continuity_root=paths.continuity_root,
    )
    app = create_app(paths, {"continuity": {}})
    c = TestClient(app)
    assert "Contacts" in c.get("/contacts").text
    runbooks = c.get("/runbooks", follow_redirects=True)
    assert runbooks.status_code == 200
    assert "r.txt" in runbooks.text


def test_graph_get_bytes() -> None:
    from bunker.continuity.graph.auth import StaticTokenProvider

    prov = StaticTokenProvider("t")
    with patch("httpx.Client") as mock_client:
        inst = mock_client.return_value.__enter__.return_value
        inst.get.return_value = MagicMock(
            status_code=200,
            content=b"bin",
            raise_for_status=lambda: None,
        )
        data = HttpxGraphClient(prov).get_bytes("/file")
        assert data == b"bin"