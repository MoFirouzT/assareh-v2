# DECISIONS

This file is the append-only log of design decisions. Entries will be added
in the same commit as the code that implements them.


A.1: tooling choices

- Package manager: `uv` (fast, modern, lockfile-backed; use `uv sync`/`uv lock`)
- Python: 3.12 (minimum supported; chosen for M4/M-series compatibility)
- Dataframes: `polars` for I/O and preprocessing; `pandas` only at sklearn/torch
	boundaries or when using pandas-only libraries
- Config: `pydantic-settings` for typed, env-aware settings
- Experiment tracking: `mlflow` with local file backend for Layer 1
- Testing: `pytest` with `tests/` discovery
- Linting: `ruff` (fast formatter/linter)
- Type checking: `mypy` (gradual; `ignore_missing_imports = true` initially)
- Logging: stdlib `logging` (no structlog)

Rationale: these choices balance modern tooling (Polars, uv) with ecosystem
compatibility (pandas/sklearn/torch). Decisions will be revisited if Layer 1
finds constraints that require different tooling.

---

(Additional decisions will be appended here alongside the implementing commits.)
