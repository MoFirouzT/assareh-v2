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

A.4: negative volume is a hard integrity failure

Negative volume is physically impossible. It indicates source corruption or
a parse error — not a data quirk like a zero-volume bar (which is real at
low-activity periods). Treating it as a hard failure makes the pipeline fail
loudly rather than silently propagate bad data into features.

---

A.4: loader casts to OHLCV_SCHEMA rather than asserting exact match

The downloader writes Parquet via pandas, which may round-trip timestamps at
a different precision (ms vs us). A strict schema comparison would reject
valid data that differs only in precision. The loader now reads the Parquet,
checks for missing columns (hard error), then casts every column to the
canonical OHLCV_SCHEMA type. This guarantees the output schema is always
correct without rejecting recoverable mismatches.

---

(Additional decisions will be appended here alongside the implementing commits.)
