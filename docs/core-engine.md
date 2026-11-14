# Core Bunker engine

Project Bunker’s original scope is **open-data ingest → DuckDB → Parquet → signed air-gap bundles**:

- Configure sources in `config/sources.yaml`.
- `bunker keygen` — Ed25519 signing keys under `data/keys/`.
- `bunker ingest` / `bunker ingest-all` — fetch, parse, deduplicate into hive-style Parquet.
- `bunker sync-package` — signed `bunker_sync_YYYY-MM-DD` folder for USB/LAN transfer.
- `bunker import-sync` / `bunker verify-sync` — verify signature and merge on the receiving site.
- `bunker query` — ad-hoc SQL over local Parquet via DuckDB.

**Bunker Continuity** (calendar, contacts, runbooks, `bunker watch`, `bunker serve`) layers on top of this storage and signing stack. See the [README](../README.md) and [CHANGELOG](../CHANGELOG.md) for continuity features.