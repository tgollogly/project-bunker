```
 ██████╗ ██╗   ██╗███╗   ██╗██╗  ██╗███████╗██████╗
 ██╔══██╗██║   ██║████╗  ██║██║ ██╔╝██╔════╝██╔══██╗
 ██████╔╝██║   ██║██╔██╗ ██║█████╔╝ █████╗  ██████╔╝
 ██╔══██╗██║   ██║██║╚██╗██║██╔═██╗ ██╔══╝  ██╔══██╗
 ██████╔╝╚██████╔╝██║ ╚████║██║  ██╗███████╗██████╔╝
 ╚═════╝  ╚═════╝ ╚═╝  ╚═══╝╚═╝  ╚═╝╚══════╝╚═════╝
        Offline-First DuckDB · Parquet · P2P Sync
```

# Project Bunker

[![CI](https://github.com/tgollogly/project-bunker/actions/workflows/ci.yml/badge.svg)](https://github.com/tgollogly/project-bunker/actions/workflows/ci.yml)
![License](https://img.shields.io/badge/License-Thomas%20Gollogly-blue)
![Offline Ready](https://img.shields.io/badge/Offline-Ready-success)
![DuckDB](https://img.shields.io/badge/DuckDB-1.x+-yellow)

**Project Bunker** is a zero-cloud-core data engine: ingest respectful open-data APIs, transform in-process with **DuckDB**, persist **ZSTD-compressed Parquet**, and replicate updates through **air-gapped `bunker_sync_*` bundles** (LAN, file share, USB/SD) with **SHA-256 manifests**. When the internet fails, pipelines **self-heal** onto local cache — no unhandled network exceptions in the hot path.

---

## Architecture (data flow)

```text
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────────┐
│  Open Data API  │────▶│ Resilient Fetch  │────▶│ Raw cache + Parquet │
│ (USGS, Open-     │     │ (retry → cache)  │     │ data/parquet/**     │
│  Meteo, …)      │     └────────┬─────────┘     └──────────┬──────────┘
└─────────────────┘              │                            │
                                 ▼                            ▼
                    ┌─────────────────────────┐    ┌──────────────────────────┐
                    │ DuckDB (embedded SQL)  │◀───│ ZSTD Parquet columnar    │
                    │ :memory: or local file │    │ partitioned datasets     │
                    └────────────┬────────────┘    └──────────────────────────┘
                                 │
                                 ▼
              ┌──────────────────────────────────────┐
              │ bunker_sync_YYYY-MM-DD/              │
              │  shards/*.parquet                    │
              │  schema.json  manifest.json (SHA256)│
              └──────────────┬───────────────────────┘
                             │
         ┌───────────────────┼───────────────────┐
         ▼                   ▼                   ▼
   LAN / SMB copy      USB handoff         UDP mesh alert
   (P2P folder sync)   (physical media)    (no DNS)
```

> [!IMPORTANT]
> **Operational invariant:** Core analytics never require a remote database, warehouse, or live internet. Ingest may use the network when available; transforms and queries run on **local Parquet** only.

> [!NOTE]
> **Attribution:** Configured sources include license notes (see `config/sources.yaml`). Honor rate limits, ToS, and citation requirements for every upstream API.

> [!WARNING]
> **Emergency failover:** If APIs are unreachable, run `make ingest-offline` or `scripts/blackout-recovery.sh`. Bunker reads the last good snapshot from `cache/` and continues Parquet + sync packaging.

---

## One-command deploy (&lt; 60 seconds)

**Prerequisites:** Python 3.10+ and `make` (optional: Docker for containerized edge nodes).

```bash
git clone https://github.com/tgollogly/project-bunker.git
cd project-bunker
make init          # venv + editable install + data dirs
make ingest-all    # live fetch → Parquet (or make ingest-offline)
make sync          # creates ./bunker_sync_YYYY-MM-DD/
make status        # row counts + paths
```

**Docker (optional):**

```bash
docker compose up --build
```

**CLI entrypoint:**

```bash
bunker ingest --source usgs_earthquakes_day
bunker sync-package
bunker query "SELECT mag, place FROM bunker_data ORDER BY mag DESC LIMIT 5"
bunker verify-sync ./bunker_sync_2026-01-01
```

---

## Repository layout

| Path | Role |
|------|------|
| `config/sources.yaml` | Source URLs, attribution, Parquet partitions |
| `src/bunker/` | Ingest, DuckDB engine, air-gap packaging, mesh comms |
| `data/parquet/` | Local columnar lake (gitignored) |
| `cache/` | Last-good API snapshots for blackout mode |
| `bunker_sync_*` | Portable sync bundles for P2P / USB |
| `scripts/blackout-recovery.sh` | Worst-case playbook automation |
| `Makefile` | `init`, ingest, sync, mesh alerts, tests |

---

## Air-gapped sync bundles

Each `bunker_sync_YYYY-MM-DD/` directory is **self-contained**:

- `shards/*.parquet` — flattened copies of local datasets  
- `schema.json` — column types (via DuckDB)  
- `manifest.json` — per-file **SHA-256** for integrity after copy  
- `OFFLINE_README.txt` — DuckDB one-liner for querying shards  

**Verify after USB/LAN handoff:**

```bash
make verify SYNC=./bunker_sync_YYYY-MM-DD
# or: bunker verify-sync ./bunker_sync_YYYY-MM-DD
```

**Query offline (DuckDB CLI or Python):**

```sql
SELECT * FROM read_parquet('shards/*.parquet', union_by_name=true);
```

---

## Local mesh communications (no DNS)

Coordinate teams when global routing fails:

```bash
make mesh-listen                    # UDP listener :41567
make mesh-alert MSG="Sync bundle ready bay 3"
python -m bunker.comms.mdns_announce  # broadcast discovery (optional zeroconf extra)
```

---

## Worst-case scenario playbook

### 1. Complete global internet blackout

1. Stop expecting live API pulls.  
2. `make ingest-offline` — rebuild Parquet from `cache/` only.  
3. `make sync` — produce a fresh `bunker_sync_*` folder for physical distribution.  
4. `make mesh-alert MSG="…"` — announce bundle location on LAN.  
5. Peers run `scripts/blackout-recovery.sh /path/to/bunker_sync_*` to verify and import shards.

### 2. Cloud provider / CDN outage

- Fetcher retries with exponential backoff, then **automatic cache fallback** (`ResilientFetcher`).  
- Confirm status: `bunker status` — if `from_cache` in ingest JSON, you are on snapshot data.

### 3. Air-gapped data recovery

1. Receive `bunker_sync_YYYY-MM-DD` via USB or SMB.  
2. `bunker verify-sync <bundle>` — fail closed on hash mismatch.  
3. Copy `shards/*.parquet` into `data/parquet/imported/`.  
4. `bunker query "SELECT COUNT(*) FROM bunker_data"`.

### 4. Corrupt or partial copy

- Manifest verification lists missing paths and hash mismatches.  
- Re-copy only failed shards; do not trust unverified Parquet in production analytics.

---

## Development

```bash
make test
make lint
```

CI runs Ruff + pytest on every push/PR.

---

## Legal & attribution

**Copyright © 2026 Thomas Gollogly. All rights reserved.**

This software and its associated documentation are provided **"as-is"**, without warranty of any kind, express or implied, including but not limited to the warranties of merchantability, fitness for a particular purpose, and non-infringement. In no event shall the author, **Thomas Gollogly**, be liable for any claim, damages, or other liability arising from, out of, or in connection with the software or the use or other dealings in the software.

Third-party open data used in default configuration remains subject to each provider’s license and attribution requirements (see `config/sources.yaml`).