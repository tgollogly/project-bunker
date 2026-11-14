# Security & privacy (Bunker Continuity)

Copyright © 2026 Thomas Gollogly.

## Personal data (UK GDPR)

Calendar and contact snapshots may contain **personal data**. Bunker Continuity:

- Stores them under `data/continuity/` as Parquet and encrypted metadata when `BUNKER_DATA_KEY` is set (Fernet).
- Does **not** delete local copies when cloud sync fails (availability over automatic erasure).
- Supports `retention_days` in `config/continuity.yaml` — implement archival/purge procedures in your organisation (automation not enabled by default).

**Data controller:** your organisation. **Purpose:** business continuity during Microsoft 365 outages. **Lawful basis:** typically legitimate interests or public task (verify with your DPO).

## Encryption

| Mechanism | Use |
|-----------|-----|
| `BUNKER_DATA_KEY` | Fernet encryption for sync metadata at rest (32+ bytes or urlsafe key) |
| `data/keys/signing.pem` | Ed25519 bundle signing (not for M365 content) |
| `BUNKER_MESH_KEY` | HMAC for LAN UDP alerts (16+ bytes) |
| `BUNKER_MATRIX_ACCESS_TOKEN` | Matrix bot token (treat as secret) |

Never commit credentials. Use environment variables or your OS secret store.

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

This kit targets **trusted LAN / single-org** continuity, not hostile-internet multi-tenant hosting. `bunker serve` binds to loopback by default — put a reverse proxy and authentication in front if exposed.

Matrix and Element in Docker are **convenience** fallbacks; harden Conduit/Synapse per Matrix.org production guidance before internet exposure.