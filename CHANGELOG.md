# Changelog

## [0.3.5] — 2026-11-14

### Fixed

- Tests ignore shell `BUNKER_*` env vars (autouse fixture) so `make test` works after README quick-start exports.
- Outage alerts: missing `BUNKER_MATRIX_ACCESS_TOKEN` logs **Matrix not configured — skipping** (INFO) instead of a failure line.

### Changed

- CI smoke job runs full `pytest` with `BUNKER_DATA_KEY` still exported after the demo.
- **Serve UI** — navy/teal offline dashboard (`/static/continuity.css`), status banner on every page, home cards, probe dots, contacts search (`?q=`), `/runbooks` views; README screenshots retaken with seeded DOWN state.

## [0.3.4] — 2026-11-14

### Added

- `bunker continuity seed-sample` — writes fictional calendar, contacts, and runbook data into the real continuity data root (encrypted with `BUNKER_DATA_KEY`).
- CI **smoke** job (Ubuntu, Python 3.12): keygen, outage demo, serve HTTP checks, `sync-package` + `verify-sync`.

### Fixed

- `scripts/continuity-outage-demo.sh` uses `seed-sample` instead of pytest (no coverage abort on fresh clones).
- `bunker doctor` reads `continuity.watch.probe_hosts` (shipped `config/continuity.yaml`).
- `bunker sync-package` exits non-zero when there is no Parquet or continuity cache to ship (continuity `.parquet.enc` still included when present).

### Changed

- README: “Try it in 2 minutes” quick start with sample data.
- Serve home page shows the first cached contact name when sample/real data exists.

## [0.3.3] — 2026-11-14

### Added

- `bunker doctor` — checks `sources.yaml` / `continuity.yaml`, signing key permissions, encryption config, Graph env vars, probe hosts, and basic Graph reachability (PASS/FAIL lines).
- `docs/real-tenant-test.md` — M365 Developer Program walkthrough.
- `docs/core-engine.md` — open-data ingest / sync bundle engine (moved from README).
- README screenshots from real `bunker serve` UI (sample data).

### Changed

- Test coverage floor raised to **88%** in CI; expanded tests for doctor and continuity paths.
- README focused on Bunker Continuity; links to core-engine and tenant test docs.

## [0.3.2] — 2026-11-14

### License

- Project Bunker is now open-sourced under the **MIT License** (`LICENSE` at repository root). Contributions are accepted under MIT (see `CONTRIBUTING.md`).

### Reliability & hardening

- `bunker continuity rekey` uses atomic writes per file; passphrase rekeys defer new `.fernet_salt` until all blobs are re-encrypted.
- Serve login rate limits persist in `serve_login_attempts.json` (mode `0600`) across restarts.
- `bunker serve` sets `Secure` on session cookies when both `--certfile` and `--keyfile` are set; clearer LAN-without-TLS warning at startup.
- Fix duplicated `FakeGraph` / `continuity_paths` definitions in `tests/conftest.py` (CI Ruff F811).

## [0.3.1] — 2026-11-14

### Security (Bunker Continuity)

- Offline UI: Jinja2 autoescape, http(s)-only `element_url`, CSP / `X-Content-Type-Options` / `Referrer-Policy`.
- Encrypt calendar/contact Parquet (`.parquet.enc`), documents, manifests, and deltas; scrypt passphrase + salt; `require_encryption`; `bunker continuity rekey`.
- MSAL token refresh with expiry margin; Graph 401 refresh-and-retry once.
- Parse M365 service health overviews; smarter HTTP probes; optional authenticated Graph probe; fix redundant watch recovery branch.
- `bunker serve set-password`, session cookies off loopback, TLS flags, login rate limit.
- Signing private keys: `0600` permissions, optional passphrase, POSIX permission check on load.

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