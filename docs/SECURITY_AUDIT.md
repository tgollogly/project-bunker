# Security audit — v0.4.2 (2026-11-17)

Scope: full `src/bunker` tree, Python dependencies, git history secret patterns, offline web UI, OAuth/token storage, sync bundle import, LAN UDP HMAC, and file permissions.

## Method

| Step | Tool / action |
|------|----------------|
| SAST | `bandit -r src/bunker -ll -q --exit-zero` (report) + `-lll` (CI gate: fail only on **High**) |
| Dependencies | `pip-audit` on locked install set (CI) |
| Secret history | `git log -p` scan for `client_secret`, `BEGIN PRIVATE KEY`, `BUNKER_DATA_KEY=` literals (none found in committed history) |
| Manual review | serve auth/CSP, encryption, `import_sync_bundle` path traversal, Graph/Google token handling, wizard POST CSRF surface |

## Findings summary

| Severity | Count | Open |
|----------|------:|-----:|
| Critical | 0 | 0 |
| High | 0 | 0 |
| Medium | 2 | 0 |
| Low | 27 | 0 (accepted) |

### Medium (fixed or mitigated)

1. **Setup wizard POST without CSRF token (Medium)**  
   - **Risk:** A malicious page on the same browser profile could trick an authenticated LAN user into changing sources or secrets.  
   - **Fix / mitigation:** Setup binds to loopback by default; LAN serve still requires password + session. Documented in `SECURITY.md`. v0.4.1 backlog: double-submit cookie or SameSite=strict session for setup when served on LAN.  
   - **Status:** Accepted with documentation for v0.4.0 (localhost-first).

2. **Keyring backend may expose secrets to OS APIs (Medium)**  
   - **Risk:** Misconfigured keyring backends could log or fail open.  
   - **Fix:** `FailKeyring` / `NoKeyringBackend` detection skips keyring and falls back to env vars only; wizard documents manual env fallback.  
   - **Status:** Fixed (detection in `secrets/store.py`).

### Low (accepted)

- Bandit `B110`/`B112` try/except pass in schedule installer and notify stubs — intentional best-effort OS integration.  
- Bandit `B603` subprocess for systemd/launchd/schtasks — required for documented `bunker continuity schedule-install`; user must run locally.  
- Pickle not used anywhere in continuity path (Parquet via pyarrow only).

## Component notes

| Area | Result |
|------|--------|
| XSS | Jinja2 autoescape; regression tests in `tests/test_serve_xss.py` |
| Path traversal (runbooks) | `runbook_plaintext` resolves under `docs_root` |
| Path traversal (sync import) | Existing manifest + signature checks unchanged; tests in `tests/test_import_merge.py` |
| Encryption at rest | Fernet/scrypt unchanged; secrets can load from keychain |
| OAuth tokens | Graph: MSAL + env/keychain; Google: refresh via HTTPS only, no token logging |
| PDF outage pack | Latin-1 sanitization to avoid font injection |
| UDP mesh HMAC | Unchanged from v0.3.x; requires `BUNKER_MESH_KEY` |

## Owner actions

1. **Microsoft Azure app registration** — tenant-specific; use least privilege listed in README.  
2. **Google OAuth client** — register desktop/OAuth client; publish refresh token via setup wizard (not shipped in repo).  
3. **Optional public OAuth client** — if the project ships a shared client ID later, rotate client secret on a schedule.

Copyright (c) 2026 Thomas Gollogly. MIT License.

---

## Re-audit — v0.4.2 (2026-11-17)

Full-repo pass over `src/`, `tests/`, `scripts/`, `.github/workflows/ci.yml`, `Dockerfile`, and `Makefile`.

| Finding | Severity | Resolution in v0.4.2 |
|---------|----------|------------------------|
| `import_sync_bundle` copied every shard into every `merge_hints` partition | High | Shard↔partition matching via `sync/partition_paths.py`; partition path validation |
| `target_partition` path traversal if manifest hints malicious | High | `validate_relative_partition` + resolved path under `parquet_root` |
| Continuity registry `raise` after first source failure contradicted “local copies kept” | Medium | Per-source `ok` flag; CLI exits 1 when any source fails |
| Setup wizard missing Google client secret field | Medium | `google_client_secret` in form + keychain |
| `doctor` ignored keychain-only secrets | Medium | `get_secret()` / `inject_secrets_into_environ()` in encryption and Graph checks |
| `bunker query` accepted arbitrary SQL | Medium | Gate to read-only statement prefixes |
| systemd/launchd shell command injection via cwd | Medium | `shlex.quote` in schedule install helpers |
| `/healthz` whitelisted but unregistered | Low | `GET /healthz` added |
| Version drift (`__init__` 0.3.6 vs pyproject) | Low | `importlib.metadata` + CLI `--version` + UI footer |
| `seed-sample` without encryption key (README first-run) | Low | `ensure_local_demo_data_key()` |
| Open-data example place name in label | Low | Generic “demo coordinates” label |

**SAST (local):** `bandit -ll --exit-zero` + `bandit -lll` (fail on High); `pip-audit` on dev extras.

**Residual (accepted):** Setup POST CSRF on loopback (documented); UDP mesh HMAC without confidentiality; iCal URL SSRF from operator-supplied config; rekey mid-crash mixed ciphertext (document in SECURITY.md — operator should re-run `continuity rekey`).