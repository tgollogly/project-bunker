```
 ██████╗ ██╗   ██╗███╗   ██╗██╗  ██╗███████╗██████╗
 ██╔══██╗██║   ██║████╗  ██║██║ ██╔╝██╔════╝██╔══██╗
 ██████╔╝██║   ██║██╔██╗ ██║█████╔╝ █████╗  ██████╔╝
 ██╔══██╗██║   ██║██║╚██╗██║██╔═██╗ ██╔══╝  ██╔══██╗
 ██████╔╝╚██████╔╝██║ ╚████║██║  ██╗███████╗████████╗
 ╚═════╝  ╚═════╝ ╚═╝  ╚═══╝╚═╝  ╚═╝╚══════╝╚═════╝
   Bunker Continuity — when Microsoft 365 goes dark
```

# Project Bunker

[![CI](https://github.com/tgollogly/project-bunker/actions/workflows/ci.yml/badge.svg)](https://github.com/tgollogly/project-bunker/actions/workflows/ci.yml)
![Version](https://img.shields.io/badge/version-0.3.0-informational)
![License](https://img.shields.io/badge/License-Thomas%20Gollogly-blue)

**Bunker Continuity** (built on Project Bunker v0.3) helps a **small organisation keep working** when **Microsoft 365** (Outlook, Teams, Exchange Online) is unavailable — as in the long global outage of **12–14 November 2026**.

It does **not** replace email or Teams. It keeps **schedules, contacts, runbook documents, backup chat, and signed offline bundles** on premises.

---

## Why this exists

When M365 is down for 24+ hours:

- Staff still need **today’s meetings** and **who to call**.
- Incident leads need **runbooks** without SharePoint.
- You need a **fallback channel** that does not depend on Microsoft’s status page loading.

Bunker:

1. **Snapshots** Graph data (calendar 14d, contacts, configured SharePoint folders) into **local Parquet + files**.
2. **`bunker watch`** tracks reachability (Outlook/Teams URLs + optional Graph service health) with **OK / DEGRADED / DOWN** and hysteresis.
3. On **DOWN**, writes a **local incident** and alerts **Matrix** (optional) + **SMS** (stub/Twilio) + **HMAC-signed LAN UDP**.
4. **`bunker serve`** — offline FastAPI web UI on loopback (Jinja2 autoescape, no CDN). Use `bunker serve set-password` before binding to a LAN address.
5. **`bunker sync-package`** — **Ed25519-signed** bundles for USB/LAN site transfer (existing Bunker engine).

---

## Honest limitations

| Claim | Reality |
|-------|---------|
| Replaces Outlook/Teams | **No** — backup visibility + chat only |
| Full P2P mesh | **No** — signed folder handoff + `import-sync` |
| Matrix “production” | **Docker profile** for Conduit + Element — you must configure users/rooms |
| Graph sync | Requires **Azure app** or token via env; tests use **mocks only** |
| Email archive | **Not implemented** |

See [SECURITY.md](SECURITY.md) for UK GDPR and Graph permissions.

---

## Microsoft Graph permissions (least privilege)

| Permission | Purpose |
|------------|---------|
| `Calendars.Read` | Calendar view snapshot |
| `Contacts.Read` | Contact / address list |
| `Files.Read.All` or `Sites.Read.All` | Configured runbook libraries |
| `ServiceHealth.Read.All` | Optional health signal for `bunker watch` |

Use a dedicated app registration with admin consent; store secrets in environment variables only.

---

## Environment variables

| Variable | Purpose |
|----------|---------|
| `BUNKER_GRAPH_TENANT_ID`, `CLIENT_ID`, `CLIENT_SECRET` | App-only Graph |
| `BUNKER_GRAPH_ACCESS_TOKEN` | Tests / delegated token (no MSAL) |
| `BUNKER_DATA_KEY` | Fernet encrypt continuity Parquet/docs/meta (44-char key or passphrase + salt) |
| `BUNKER_DATA_KEY_NEW` | New key for `bunker continuity rekey` |
| `BUNKER_MATRIX_ACCESS_TOKEN`, `BUNKER_MATRIX_HOMESERVER` | Matrix alerts |
| `BUNKER_MESH_KEY` | HMAC LAN UDP alerts (16+ bytes) |
| Twilio suite | `BUNKER_TWILIO_*`, `BUNKER_SMS_TO` |
| `BUNKER_SP_DRIVE_ID` | SharePoint runbook drive in `config/continuity.yaml` |

---

## Quick start

```bash
make init
bunker keygen
export BUNKER_GRAPH_ACCESS_TOKEN=...   # or app-only Graph env vars
bunker continuity sync
bunker continuity status
bunker watch
bunker serve --port 8765
```

**Outage demo (simulated probes):**

```bash
bash scripts/continuity-outage-demo.sh
```

**Matrix (optional):**

```bash
docker compose -f docker-compose.continuity.yml --profile matrix up -d
```

---

## Core Bunker engine (unchanged)

Open-data ingest → DuckDB → Parquet → signed `bunker_sync_*` bundles: see `make ingest-all`, `make sync`, [CHANGELOG.md](CHANGELOG.md).

---

## Development

```bash
make test
make lint
make typecheck
```

---

## Legal & attribution

**Copyright © 2026 Thomas Gollogly. All rights reserved.**

This software and its associated documentation are provided **"as-is"**, without warranty of any kind, express or implied, including but not limited to the warranties of merchantability, fitness for a particular purpose, and non-infringement. In no event shall the author, **Thomas Gollogly**, be liable for any claim, damages, or other liability arising from, out of, or in connection with the software or the use or other dealings in the software.

Third-party open data used in default configuration remains subject to each provider’s license and attribution requirements (see `config/sources.yaml`).