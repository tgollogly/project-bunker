<p align="center"><img src="docs/images/banner.png?v=20261117" alt="Project Bunker: keep an offline copy when the cloud goes down. Free and open source, MIT License." width="100%"></p>

# Project Bunker

[![CI](https://github.com/tgollogly/project-bunker/actions/workflows/ci.yml/badge.svg)](https://github.com/tgollogly/project-bunker/actions/workflows/ci.yml)
![Version](https://img.shields.io/badge/version-0.4.2-informational)
![License](https://img.shields.io/badge/License-MIT-green.svg)

**Keep an offline copy of what you need when the cloud goes down.**  
Bunker Continuity works with **Microsoft cloud (Graph API)**, **Google Workspace**, **iCal (.ics)**, **CSV/vCard contacts**, and **local document folders** — for compatibility only. Not affiliated with Microsoft, Google, or any cloud provider.

---

## What it does (plain English)

- **Snapshots** your calendar, contacts, and important files to **encrypted storage on your computer**.
- **Shows them** in a simple **offline web page** (`bunker serve`) — meetings, contacts, runbooks.
- **Watches** whether major cloud endpoints look up or down (optional).
- **Prints an outage pack** (PDF) after each sync — next 7 days of meetings, contacts, and document list.
- **Optional** open-data demo engine (USGS / Open-Meteo) lives in `examples/open-data/` for developers.

It does **not** replace email, Teams, or Slack. It is a **local safety copy** for outages and drills.

---

## Install (~10 minutes)

### Linux or macOS (recommended)

```bash
curl -fsSL https://raw.githubusercontent.com/tgollogly/project-bunker/main/scripts/install-bunker.sh | bash
```

Or:

```bash
pipx install git+https://github.com/tgollogly/project-bunker.git
```

### Windows

1. Download the **`bunker-windows-portable`** artifact from the latest [GitHub Actions CI](https://github.com/tgollogly/project-bunker/actions) run (`windows-portable` job).
2. Unzip and run `bunker.exe` from a folder that includes `config/`.
3. Or: `pip install git+https://github.com/tgollogly/project-bunker.git` if you use Python 3.10+.

### Docker (optional)

```bash
make init
bunker serve --port 8765
```

---

## First run (no environment variables required)

1. **Try sample data** (no cloud account):

```bash
bunker continuity seed-sample
bunker serve --port 8765
```

Open `http://127.0.0.1:8765` and click **Setup** to walk through sources, passwords, and sync schedule.

2. **Set an encryption passphrase** in Setup (stored in your **OS keychain** when available, else `BUNKER_DATA_KEY`).
3. **Choose sources** — Microsoft Graph, Google, iCal URL, contact files, local folder.
4. **Sign in** — register your own OAuth apps (see below); the wizard stores client IDs and tokens in the keychain.
5. **Run a sync:** `bunker continuity sync`
6. **Background sync:** `bunker continuity schedule-install --hours 6`

---

## Cloud sign-in (you register the apps)

| Provider | What you create | Scopes (read-only) |
|----------|-----------------|-------------------|
| Microsoft (Entra) | App registration + admin consent | `Calendars.Read`, `Contacts.Read`, optional `Files.Read` / `ServiceHealth.Read` |
| Google Cloud | OAuth desktop client | Calendar, People (contacts), Drive read |

Use **device code** or **refresh tokens**; Bunker never ships a shared production client secret in the repo.  
Details: [Testing on an M365 Developer tenant](docs/real-tenant-test.md) (same pattern for any tenant).

---

## Honest limitations

| Claim | Reality |
|-------|---------|
| Replaces Outlook/Teams/Gmail | **No** — backup visibility only |
| Works with zero setup | **Sample data yes**; real sync needs your OAuth apps or files |
| Full P2P mesh | **No** — signed USB/LAN bundles (`bunker sync-package`) |
| Email archive | **Not implemented** |
| Shared OAuth app in the box | **No** — you register your own (owner action) |

---

## Commands you will use

| Command | Purpose |
|---------|---------|
| `bunker continuity sync` | Pull latest from configured sources |
| `bunker continuity status` | Show last sync times |
| `bunker serve` | Offline web UI |
| `bunker continuity outage-pack` | Regenerate PDF |
| `bunker continuity schedule-install` | systemd / launchd / Task Scheduler |
| `bunker --config examples/open-data/sources.yaml ingest-all` | Optional open-data demo |

Core DuckDB / P2P engine: [docs/core-engine.md](docs/core-engine.md).

---

## FAQ

**Do I need to set environment variables?**  
No for normal use after Setup. Advanced users can still set `BUNKER_*` vars (see [SECURITY.md](SECURITY.md)).

**Is my data encrypted?**  
Yes, when `require_encryption` is true (default). Parquet and documents use Fernet at rest.

**Can I use this without Microsoft?**  
Yes — enable Google, iCal, CSV/vCard, and local folders only in Setup or `config/continuity.yaml` `sync_sources`.

**Where is the PDF?**  
`data/continuity/outage_pack.pdf` and **Download** link in the web UI footer.

---

## Troubleshooting

| Problem | Try |
|---------|-----|
| Sync fails “Graph auth unavailable” | Complete Setup or set keychain secrets; check tenant/client ID |
| Blank calendar | Run `bunker continuity sync`; check source enabled in `sync_sources` |
| `serve` asks for password on LAN | Run `bunker serve set-password` first |
| Coverage / tests fail after env exports | Tests ignore stray `BUNKER_*` in shell (see CONTRIBUTING) |

---

## Development

```bash
make test
make lint
make typecheck
```

Security review: [docs/SECURITY_AUDIT.md](docs/SECURITY_AUDIT.md).

---

## Trademarks and affiliation

Project Bunker is an independent, free, open-source project (MIT License, Copyright (c) 2026 Thomas Gollogly). It is **not affiliated with, endorsed by, or sponsored by** Microsoft Corporation, Google LLC, The Bunker, Bunker Technical Solutions, or any other company.  
Microsoft, Microsoft 365, Outlook, Teams, SharePoint, Google, Google Workspace, and Gmail are **trademarks of their respective owners**, used here only to describe compatibility.

---

## License

MIT — see [LICENSE](LICENSE). Software is provided **“as is”, without warranty of any kind**.