# Testing Bunker Continuity on a Microsoft 365 Developer tenant

Use a **[Microsoft 365 Developer Program](https://developer.microsoft.com/microsoft-365/dev-program)** tenant (free E5-style sandbox). Test with **synthetic or demo users only** — no production mailboxes.

## 1. Create an app registration

1. Sign in to [Azure Portal](https://portal.azure.com) with your dev tenant admin.
2. **Microsoft Entra ID → App registrations → New registration**.
3. Name: e.g. `Bunker Continuity (dev)`.
4. Supported account types: **Accounts in this organizational directory only**.
5. Register. Note **Application (client) ID** and **Directory (tenant) ID**.

## 2. API permissions (least privilege)

Under **API permissions → Add a permission → Microsoft Graph → Application permissions**:

| Permission | Why |
|------------|-----|
| `Calendars.Read` | Calendar snapshot |
| `Contacts.Read` | Contact list |
| `Files.Read.All` *or* `Sites.Read.All` | Runbook library (if you configure SharePoint) |
| `ServiceHealth.Read.All` | Optional `bunker watch` health signal |

Click **Grant admin consent for &lt;tenant&gt;**.

## 3. Client secret

**Certificates & secrets → New client secret** → copy the **value** once (not the secret ID).

## 4. Configure the repo

From the project root:

```bash
make init
bunker keygen
export BUNKER_DATA_KEY="$(python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())')"
export BUNKER_GRAPH_TENANT_ID="<tenant-id>"
export BUNKER_GRAPH_CLIENT_ID="<client-id>"
export BUNKER_GRAPH_CLIENT_SECRET="<secret>"
# Optional: SharePoint runbook drive from Graph or admin center
export BUNKER_SP_DRIVE_ID="<drive-id>"
```

Run `bunker doctor` — expect **PASS** on configs, signing key, encryption, probes, and Graph credentials (reachability may **PASS** or **FAIL** depending on network).

## 5. Sync and verify local cache

```bash
bunker continuity sync
bunker continuity status
```

**Success:** JSON lists `m365_calendar`, `m365_contacts`, and optionally document sources with recent sync times and byte counts under `data/continuity/`.

## 6. Watch and serve

```bash
bunker watch
bunker serve --port 8765
```

Open `http://127.0.0.1:8765` — calendar, contacts, runbooks, and status pages load from **local** data (no live Graph calls in the UI).

For LAN testing, run `bunker serve set-password` first, then bind with `--host 0.0.0.0` and TLS (`--certfile` / `--keyfile`) as described in [SECURITY.md](../SECURITY.md).

## 7. Tear down

1. **Azure Portal → App registrations** → your app → **Delete**.
2. Revoke or rotate any client secret you created.
3. Remove local continuity data if the tenant had real user PII: `rm -rf data/continuity` (and rotate `BUNKER_DATA_KEY` if you reused it elsewhere).

## Troubleshooting

| Symptom | Check |
|---------|--------|
| `Graph auth unavailable` | Tenant/client/secret env vars; admin consent |
| Empty calendar | User `calendar_user` in `config/continuity.yaml` (default `me` = app context; may need `/users/{id}` for some app-only setups) |
| `require_encryption` errors | `BUNKER_DATA_KEY` set before sync |
| `doctor` FAIL on signing key | Run `bunker keygen`; ensure `data/keys/signing.pem` is mode `0600` on Unix |