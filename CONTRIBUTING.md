# Contributing to Project Bunker

Copyright © 2026 Thomas Gollogly. All rights reserved.

## Development setup

```bash
make init
make test
make lint
make typecheck
```

## Adding a data source

1. Add an entry to `config/sources.yaml` with `url`, `parser`, `primary_key`, and `parquet_partition`.
2. Register a parser in `src/bunker/ingest/parsers.py` (or reference an existing parser id).
3. Add tests with fixture payloads — no live network in unit tests.

## Pull requests

- Keep commits focused; include tests for behaviour changes.
- `ruff check .`, `mypy`, and `pytest` must pass locally.
- Do not weaken manifest verification or remove signing without discussion.

## Security

Report suspected vulnerabilities privately to the repository owner. Do not commit private keys or real `BUNKER_MESH_KEY` values.