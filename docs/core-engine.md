# Core Bunker engine

Project Bunker’s original scope is **open-data ingest → DuckDB → Parquet → signed air-gap bundles**:

- Configure sources in `config/sources.yaml`.
- `bunker keygen` — Ed25519 signing keys under `data/keys/`.
- `bunker ingest` / `bunker ingest-all` — fetch, parse, deduplicate into hive-style Parquet.
- `bunker sync-package` — signed `bunker_sync_YYYY-MM-DD` folder for USB/LAN transfer. Fails with a clear error if there is nothing to ship (no open-data Parquet and no continuity `.parquet.enc` cache). After `bunker continuity sync` or `bunker continuity seed-sample`, continuity encrypted Parquet shards are included automatically.
- `bunker import-sync` / `bunker verify-sync` — verify signature and merge on the receiving site.
- `bunker query` — ad-hoc SQL over local Parquet via DuckDB.

**Bunker Continuity** (calendar, contacts, runbooks, `bunker watch`, `bunker serve`) layers on top of this storage and signing stack. See the [README](../README.md) and [CHANGELOG](../CHANGELOG.md) for continuity features.