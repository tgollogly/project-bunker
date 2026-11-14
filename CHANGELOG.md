# Changelog

## [0.3.0] — 2026-11-14

### Bunker Continuity (Microsoft 365 outage kit)

- Microsoft Graph sync: calendars (14d), contacts, SharePoint folder docs → Parquet + SHA-256 doc manifests.
- `bunker continuity sync` / `continuity status`; cache retention when cloud unreachable.
- `bunker watch` with OK/DEGRADED/DOWN hysteresis; local incident on DOWN; Matrix + SMS (stub/Twilio).
- `bunker serve` — offline FastAPI portal (calendar, contacts, docs, status, Element link).
- Fernet encryption for sync metadata (`BUNKER_DATA_KEY`); `SECURITY.md` (UK GDPR notes).
- Docker Compose profile: Conduit + Element for `#outage` backup chat.
- `scripts/continuity-outage-demo.sh` — simulated outage walkthrough.
- Continuity Parquet included in signed sync bundles.

## [0.2.0] — 2026-11-14

### Added

- Hive-style Parquet parts (`ingest_date=…/part-*.parquet`) with DuckDB `COPY` (ZSTD) writes and atomic file replace.
- Parser registry (`parser:` / source `id` in `config/sources.yaml`).
- Cache freshness gate for `min_fetch_interval_seconds`.
- Primary-key deduplication via DuckDB `_current.parquet` compaction.
- Ed25519-signed sync manifests (`bunker keygen`, `verify-sync`, `import-sync`).
- Bundle format v2: rejects unknown versions and unlisted extra files.
- HMAC-signed UDP LAN alerts (`BUNKER_MESH_KEY`, replay and staleness checks).
- `scripts/walkthrough-demo.sh` for terminal demos / asciinema.
- Mypy + expanded pytest coverage (≥85%); CI matrix on Linux, macOS, Windows, Python 3.10–3.13.

### Changed

- `sync-package` requires a local signing key (`data/keys/signing.pem`).
- README toned to match implemented behaviour.

## [0.1.0] — 2026-11-14

Initial offline-first scaffold: ingest, Parquet lake, basic sync bundles, UDP alert prototype.