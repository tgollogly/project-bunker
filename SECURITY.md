# Security & privacy (Bunker Continuity)

Copyright (c) 2026 Thomas Gollogly. Released under the MIT License (see `LICENSE`).

## Personal data (UK GDPR)

Calendar and contact snapshots may contain **personal data**. Bunker Continuity:

- Stores them under `data/continuity/` as **Fernet-encrypted** Parquet (`.parquet.enc`), encrypted documents (`.enc`), and encrypted metadata/manifests when `BUNKER_DATA_KEY` is set.
- Does **not** delete local copies when cloud sync fails (availability over automatic erasure).
- Supports `retention_days` in `config/continuity.yaml` — implement archival/purge procedures in your organisation (automation not enabled by default).

**Data controller:** your organisation. **Purpose:** business continuity during cloud outages (Microsoft, Google, iCal, or local sources). **Lawful basis:** typically legitimate interests or public task (verify with your DPO).

## Encryption

| Mechanism | Use |
|-----------|-----|
| `BUNKER_DATA_KEY` | Fernet at rest for continuity Parquet, docs, meta, manifests, and delta state. Accepts a 44-char url-safe Fernet key **or** a passphrase derived with scrypt + per-site salt (`data/continuity/.fernet_salt`). |
| `require_encryption` | Defaults to `true` in `config/continuity.yaml`; sync refuses when no key is configured. |
| `bunker continuity rekey` | Rotates ciphertext using `BUNKER_DATA_KEY` (current) and `BUNKER_DATA_KEY_NEW`. |
| `data/keys/signing.pem` | Ed25519 bundle signing (0600 on POSIX; optional PEM passphrase). |
| `BUNKER_MESH_KEY` | HMAC for LAN UDP alerts (16+ bytes) |
| `BUNKER_MATRIX_ACCESS_TOKEN` | Matrix bot token (treat as secret) |

Never commit credentials. v0.4.0 stores wizard and sync secrets in the **OS keychain** (`keyring`, service name `project-bunker`) with **`BUNKER_*` environment variable fallback**. See [docs/SECURITY_AUDIT.md](docs/SECURITY_AUDIT.md).

Plaintext Parquet or document bytes are **not** written to disk for continuity data; the serve UI decrypts in memory for display/query.

## Microsoft Graph (least privilege)

Prefer **application permissions** scoped narrowly for sync service accounts:

| Permission | Why |
|------------|-----|
| `Calendars.Read` | Read calendar view for snapshot |
| `Contacts.Read` | Read contacts / GAL export |
| `Files.Read.All` or `Sites.Read.All` | Read configured SharePoint/OneDrive runbook folders |
| `ServiceHealth.Read` (optional) | Health overview for `bunker watch` |

Avoid `Mail.Read`, `User.ReadWrite.All`, or broad `Directory.ReadWrite.All` unless strictly required.

## Threat model (honest)

This kit targets **trusted LAN / single-org** continuity, not hostile-internet multi-tenant hosting.

- `bunker serve` binds to loopback by default.
- Non-loopback hosts require `bunker serve set-password` (scrypt hash, session cookie, login rate limit) and should use TLS (`--certfile` / `--keyfile`).
- The offline UI uses Jinja2 autoescape, validates `element_url` as http(s) only, and sets CSP / `nosniff` / `Referrer-Policy` headers.

Matrix and Element in Docker are **convenience** fallbacks; harden Conduit/Synapse per Matrix.org production guidance before internet exposure.

## v0.3.2 hardening

| Topic | Change |
|-------|--------|
| Rekey | Per-file atomic replace; new passphrase salt written only after all ciphertext is updated (no half-migrated tree). |
| Serve brute force | Failed login counts persist on disk (`serve_login_attempts.json`, `0600`), not only in memory. |
| Session cookies | `Secure` automatically when TLS cert/key pair is configured for `bunker serve`. |

## Security review fixes (v0.3.1)

| Issue | Fix |
|-------|-----|
| XSS in offline web UI | Jinja2 templates with autoescape; http(s)-only Element links; CSP / nosniff / no-referrer headers. |
| Encryption at rest gaps | Encrypt calendar/contact Parquet, documents, meta, manifests, deltas; scrypt passphrase derivation; `require_encryption` + `continuity rekey`. |
| Graph token cached forever | MSAL silent/refresh with expiry margin; single 401 refresh retry in Graph client. |
| Superficial health checks | Parse service health overviews; configurable watched services; 401/403 probes count as up; optional Graph auth probe. |
| Unauthenticated LAN serve | Password + session auth off loopback; TLS options; login rate limiting. |
| Signing key permissions | Private keys written 0600; refuse world-readable PEM on POSIX; optional BestAvailableEncryption passphrase. |