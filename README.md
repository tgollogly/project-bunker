```
 ██████╗ ██╗   ██╗███╗   ██╗██╗  ██╗███████╗██████╗
 ██╔══██╗██║   ██║████╗  ██║██║ ██╔╝██╔════╝██╔══██╗
 ██████╔╝██║   ██║██╔██╗ ██║█████╔╝ █████╗  ██████╔╝
 ██╔══██╗██║   ██║██║╚██╗██║██╔═██╗ ██╔══╝  ██╔══██╗
 ██████╔╝╚██████╔╝██║ ╚████║██║  ██╗███████╗██████╔╝
 ╚═════╝  ╚═════╝ ╚═╝  ╚═══╝╚═╝  ╚═╝╚══════╝╚═════╝
     Local ingest · DuckDB · Parquet · signed bundles
```

# Project Bunker

[![CI](https://github.com/tgollogly/project-bunker/actions/workflows/ci.yml/badge.svg)](https://github.com/tgollogly/project-bunker/actions/workflows/ci.yml)
![Version](https://img.shields.io/badge/version-0.2.0-informational)
![License](https://img.shields.io/badge/License-Thomas%20Gollogly-blue)
![DuckDB](https://img.shields.io/badge/DuckDB-embedded-yellow)

**Project Bunker** is a small Python toolkit for copying open-data API responses into a **local Parquet lake**, querying with **embedded DuckDB**, and shipping updates as **signed, hash-verified folder bundles** you can move by USB, SMB, or any file copy — no custom P2P protocol.

---

## Why this exists

Councils, field teams, community groups, and disaster-response volunteers often need **the same datasets when uplinks are slow or gone**: incident feeds, weather snapshots, asset registers. Bunker:

- Pulls from configured HTTP APIs when online (respecting cache freshness and rate limits).
- Falls back to **`cache/`** snapshots when the network fails.
- Writes **Hive-style date parts** under `data/parquet/` and compacts deduplicated **`_current.parquet`** slices with DuckDB.
- Packages **`bunker_sync_YYYY-MM-DD/`** folders (Parquet shards + `schema.json` + **Ed25519-signed** `manifest.json`).
- Offers **optional HMAC-signed UDP broadcasts** on your LAN (`BUNKER_MESH_KEY`) — not a full mesh network.

---

## What is actually implemented (v0.2)

| Capability | Reality |
|------------|---------|
| **DuckDB transforms** | Parquet writes use `COPY … (FORMAT parquet, COMPRESSION zstd)`; dedup/compaction runs in DuckDB. |
| **Partitioning** | `…/<dataset>/ingest_date=YYYY-MM-DD/part-<uuid>.parquet` (not a distributed table catalog). |
| **“P2P sync”** | **Manual** folder replication; `bunker import-sync` merges verified bundles into the local lake. |
| **“Mesh”** | **Signed UDP alerts** on port 41567; optional zeroconf helper script — no routing fabric. |
| **Resilience** | Retries + cache fallback + offline ingest flag; not a distributed HA system. |
| **Security** | SHA-256 file hashes + Ed25519 manifest signatures; LAN alerts use HMAC with replay checks. |

---

## Architecture

```text
 Open API ──▶ fetch (or cache) ──▶ parser registry ──▶ DuckDB COPY ──▶ Parquet parts
                                                      └──▶ dedup ──▶ _current.parquet
                                                                        │
                                                                        ▼
                                              signed bunker_sync_*  ──▶ USB / LAN copy ──▶ import-sync
```

> [!NOTE]
> **Attribution:** Every source in `config/sources.yaml` includes license/attribution fields. You are responsible for compliance with upstream ToS and rate limits.

> [!WARNING]
> **Blackout:** `bunker ingest --offline` / `make ingest-offline` uses **only** `cache/` bytes. Run a normal ingest once while online to seed cache.

---

## Quick start

```bash
make init
bunker keygen
make ingest-all          # needs network unless cache already seeded
make sync
bunker verify-sync ./bunker_sync_$(date -u +%Y-%m-%d) --public-key data/keys/signing.pub.pem
```

**Terminal walkthrough (asciinema-friendly):**

```bash
make walkthrough
# or: asciinema rec -c "bash scripts/walkthrough-demo.sh"
```

Simulates: ingest → offline ingest → signed sync → verify → `import-sync` → UDP alert.

---

## CLI

```bash
bunker ingest --source usgs_earthquakes_day
bunker ingest-all --offline
bunker sync-package
bunker verify-sync <bundle> --public-key data/keys/signing.pub.pem
bunker import-sync <bundle> --public-key data/keys/signing.pub.pem
bunker query "SELECT COUNT(*) FROM bunker_data"
export BUNKER_MESH_KEY='your-16+-byte-secret'
python -m bunker.comms.udp_broadcast send "bundle ready"
```

---

## Limitations

- **Single-node** tool — no cluster coordinator, no CRDT sync, no background daemon.
- **Trust model:** Ed25519 public key must be distributed out-of-band; UDP alerts trust a shared symmetric key.
- **Parsers:** Only registered parsers run; extending sources requires config + (usually) a small Python function.
- **Windows/macOS/Linux** are CI-tested, but USB paths and permissions remain your OS concern.
- **Not audited** for hostile-network deployments; treat bundles like any other file from an external peer until verified.

---

## Blackout playbook (short)

1. `make ingest-offline` — build Parquet from cache.  
2. `make sync` — signed bundle (needs `data/keys/signing.pem`).  
3. Hand off folder; peer runs `bunker verify-sync` then `bunker import-sync`.  
4. Optional: `export BUNKER_MESH_KEY=…` and `make mesh-alert MSG="…"`.

See `scripts/blackout-recovery.sh` for automation.

---

## Development

```bash
make test        # pytest, ≥85% coverage on src/bunker
make lint        # ruff check .
make typecheck   # mypy
```

See [CONTRIBUTING.md](CONTRIBUTING.md) and [CHANGELOG.md](CHANGELOG.md).

---

## Legal & attribution

**Copyright © 2026 Thomas Gollogly. All rights reserved.**

This software and its associated documentation are provided **"as-is"**, without warranty of any kind, express or implied, including but not limited to the warranties of merchantability, fitness for a particular purpose, and non-infringement. In no event shall the author, **Thomas Gollogly**, be liable for any claim, damages, or other liability arising from, out of, or in connection with the software or the use or other dealings in the software.

Third-party open data used in default configuration remains subject to each provider’s license and attribution requirements (see `config/sources.yaml`).