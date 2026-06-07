# Phase A — Foundation

**Goal:** A clean repo, reproducible environment, and validated raw data on disk.

---

## A.1 — Repo skeleton and tooling

**What to build:**

```text
assareh-v2/ (repo root)
├── pyproject.toml
├── uv.lock
├── README.md
├── LICENSE
├── CLAUDE.md
├── docs/
│   ├── PHASE_A.md          # this file
│   ├── PHASE_B.md
│   ├── VISION.md
│   ├── PLAN.md
│   ├── DECISIONS.md
│   ├── LEARNINGS.md
│   └── GLOSSARY.md
├── .gitignore
├── .env.example
├── src/
│   └── assareh/
│       ├── __init__.py
│       ├── config.py
│       ├── data/
│       │   ├── __init__.py
│       │   ├── schemas.py
│       │   ├── loader.py
│       │   └── integrity.py
│       └── features/       # lands in Phase B (D-031)
│           ├── __init__.py
│           └── patr.py     # B.0, multi-tf pATR
├── scripts/
│   ├── data_downloader.py
│   └── fetch_binance_ohlcv.py
├── tests/
│   ├── __init__.py
│   ├── conftest.py         # synthetic_ohlcv fixture
│   ├── test_integrity.py
│   └── test_placeholder.py
├── data/
│   ├── raw/                # btcusdt_{1m,15m,1h,4h}.parquet + checksums.jsonl
│   ├── interim/
│   └── external/
└── notebooks/
```

**Tooling decisions (logged in DECISIONS.md):**

- Package manager: `uv` (fast, modern, good on M-series)
- Python: 3.12 (stable, broadly supported)
- Dataframes: Polars for I/O and preprocessing; pandas at the sklearn/torch
  and pandas-ta boundary only
- Config: `pydantic-settings` (typed, env-aware)
- Experiment tracking: MLflow with local file backend (no server in this iteration)
- Testing: pytest
- Linting: ruff
- Type checking: mypy (gradual, not strict yet)
- Logging: stdlib `logging` (no structlog)

### `pyproject.toml`

Pin majors; let `uv.lock` (committed) handle exact versions.

```toml
[project]
name = "assareh"
version = "0.1.0"
requires-python = ">=3.12,<3.13"
dependencies = [
    "polars>=1.20,<2",
    "pandas>=2.2,<3",            
    "numpy>=1.26,<3",
    "pydantic>=2.7,<3",
    "pydantic-settings>=2.3,<3",
    "mlflow>=2.15,<3",
    "scikit-learn>=1.5,<2",
    "torch>=2.4,<3",
    "requests>=2.32,<3",
    "ccxt>=4.4,<5",
    "tqdm>=4.66,<5",
]

[dependency-groups]
dev = [
    "pytest>=8",
    "pytest-cov",
    "ruff>=0.6",
    "mypy>=1.11",
    "ipykernel",
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/assareh"]

[tool.ruff]
line-length = 100
target-version = "py312"

[tool.mypy]
python_version = "3.12"
ignore_missing_imports = true   # gradual; tighten later

[tool.pytest.ini_options]
testpaths = ["tests"]
```

### `src/assareh/config.py`

```python
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="ASSAREH_", env_file=".env")

    # Paths
    data_dir: Path = Path("data")
    raw_subdir: str = "raw"
    interim_subdir: str = "interim"
    external_subdir: str = "external"

    # Data
    symbol: str = "BTCUSDT"
    intervals: list[str] = ["1m", "15m", "1h", "4h"]

    # Experiment tracking
    mlflow_tracking_uri: str = "file:./mlruns"

    # Misc
    random_seed: int = 42
    log_level: str = "INFO"

    @property
    def raw_dir(self) -> Path:
        return self.data_dir / self.raw_subdir

    @property
    def interim_dir(self) -> Path:
        return self.data_dir / self.interim_subdir

    @property
    def external_dir(self) -> Path:
        return self.data_dir / self.external_subdir
```

Library code accepts `Settings` (or specific paths from it) as an argument.
Never reads it from a global.

### `src/assareh/data/schemas.py`

The canonical OHLCV schema is a single source of truth.
The loader asserts it on read; downstream modules import `OHLCV_SCHEMA` for their own assertions.

```python
import polars as pl
from datetime import datetime
from pydantic import BaseModel

OHLCV_SCHEMA: dict[str, type[pl.DataType] | pl.DataType] = {
    "open_time":              pl.Datetime("us", time_zone="UTC"),
    "open":                   pl.Float64,
    "high":                   pl.Float64,
    "low":                    pl.Float64,
    "close":                  pl.Float64,
    "volume":                 pl.Float64,
    "close_time":             pl.Datetime("us", time_zone="UTC"),
    "number_of_trades":       pl.Int64,
    "taker_buy_base_volume":  pl.Float64,
    "taker_buy_quote_volume": pl.Float64,
}

class GapRecord(BaseModel):
    start: datetime
    end: datetime
    n_missing: int

class IntegrityReport(BaseModel):
    timeframe: str
    n_rows: int
    date_range_start: datetime
    date_range_end: datetime
    n_duplicates: int
    gaps: list[GapRecord]
    zero_volume_count: int
    ohlc_equal_count: int
    price_min: float
    price_max: float
    ohlc_violation_count: int
    nan_counts: dict[str, int]
    passed: bool
    hard_failures: list[str]

class CrossTimeframeReport(BaseModel):
    """Result of checking that the four timeframes share a consistent grid."""
    reference_timeframe: str            # e.g. "1m"
    misaligned_opens: dict[str, int]    # per coarser tf: count of opens not on the finer grid
    spacing_violations: dict[str, int]  # per tf: bars whose spacing != nominal interval
    coverage_mismatch: dict[str, str]   # per tf: human note on date-range overlap
    passed: bool
    hard_failures: list[str]
```

### `CLAUDE.md` (saved at repo root)

```markdown
# Assareh project conventions

## Hard rules — never violate
- Stick to the plan as much as possible.
The order is: `VISION.md` > `PLAN.md` > `PHASE_X.md`.
- Every meaningful design decision goes in `DECISIONS.md` with the verdict, rationale, and v1 alternative.
Those decisions should be reflected in the plan.
In case of any descrepencies, raise a warning.
- There comes occasions that some decisions take place at the code level and then documented in `DESISION.md`.
Those decisions should be reflected in the plan.

## Dual-arm rule

- Where v1 made a choice we improve on, keep both a v1-faithful arm and an honest arm, both runnable through the same harness. 
The honest arm is the trusted result; the gap is a finding. 
See `DECISIONS.md`.

## Logging
- Library modules: `logger = logging.getLogger(__name__)`, no handler setup.
- Entrypoints (scripts/, __main__): configure root logger with format
  `%(asctime)s [%(levelname)s] %(name)s: %(message)s`, level from
  `Settings.log_level`.
- Never use `print()` outside notebooks.

## Paths
- All filesystem paths come from `Settings`. 
  Library code accepts paths or a `Settings` instance as arguments.Never read a global.
- Tests use the `tmp_path` fixture and an override `Settings`.

## Test fixtures
- Synthetic OHLCV always comes from the `synthetic_ohlcv` fixture in
  `tests/conftest.py`.
  Don't reinvent it per test.

## Polars
- Lazy by default for any pipeline > 2 operations.
  Collect at the boundary.
- `.to_pandas()` only at the sklearn/torch boundary or when calling
  pandas-ta.
  Annotate the crossing with a comment.

## DECISIONS vs LEARNINGS
- DECISIONS.md: a choice between alternatives where future-you will ask "why did we pick that?".
- LEARNINGS.md: a finding, surprise, or dead end.
  Logged when discovered.
```

**Definition of done:**

- `uv sync` produces a working env on the M4
- `uv run pytest` runs and exits clean (even with no tests yet)
- `uv run ruff check .` and `uv run mypy src/` both pass
- All files listed in the tree exist with the contents above (or stubs for
  what gets populated in A.2 / A.3)
- Initial commit pushed; CI not yet required

---

## A.2 — Raw data acquisition

**Approach:**
Strategy:
monthly ZIP archives from `data.binance.vision` for history, daily
ZIP archives for the current month, and `ccxt` as the tail filler for the most recent bars not yet archived.
It also cross-verifies ccxt data against binance data on the overlap before appending.

### What the downloader does

The contract `BinanceDownloader` (in `scripts/data_downloader.py`) exposes to
the rest of the project. Each guarantee points at the decision or learning
that governs it.

- **Output.** One Parquet file per interval at
  `data/raw/btcusdt_{interval}.parquet`, zstd-compressed, columns
  conforming to `OHLCV_SCHEMA` (D-021). The downloader stays pandas
  internally; the Polars loader (A.3) consumes the Parquet.
- **Timestamps.** UTC-aware throughout. Binance Vision CSVs are not
  internally consistent in timestamp encoding — the parser detects
  ms / us / s by numeric range, column-wide (L-016). `OHLCV_SCHEMA`
  specifies `us`-precision UTC; the loader's cast (D-034) reconciles the
  pandas-Parquet ms round-trip without rejecting valid data, with the
  not-UTC-aware case backstopped as a hard integrity failure (D-022).
- **Archive integrity.** For every monthly/daily ZIP, the co-located
  `.CHECKSUM` is fetched when available; SHA-256 verification is enforced
  on presence and skipped with a warning on absence (D-019, L-005). Every
  verified hash is appended to `data/raw/checksums.jsonl` for audit; the
  log records *only* checksums that were actually verified, so it never
  overstates coverage.
- **Tail fill.** `ccxt` fills the gap between the last archived day and
  "now". Before append, the new bars are cross-verified against the
  existing Binance archive on 10 completed overlapping candles, with a
  ≤20% per-column mismatch tolerance (looser on volume than OHLC) — a
  larger mismatch raises and aborts the update. The three ancillary
  columns (`number_of_trades`, `taker_buy_base_volume`,
  `taker_buy_quote_volume`) are unavailable from `ccxt.fetch_ohlcv` and
  are filled with **explicit zero** rather than NaN (D-020); Phase D
  must guard these columns with a `> 0` check or `has_ancillary` flag
  (see L-003).
- **Idempotence.** The currently-forming bar is filtered before any
  merge, and merges deduplicate on `open_time`, so re-running the
  entrypoint downloads only what's new and exits cleanly with no
  duplicate rows.
- **Coverage strategy.** The current month is skipped in the monthly
  archive scan (Binance does not publish it until the month closes) and
  filled in via the daily-archive scan; the ccxt tail then covers from
  the last completed daily archive up to "now".
- **Errors.** Hard-fail on a present-but-mismatched archive checksum or
  on ccxt overlap-verification failure. Transient HTTP (429, 5xx) is
  retried with exponential backoff via a `requests.Session` configured
  with `HTTPAdapter(max_retries=Retry(total=5, backoff_factor=1.0,
  status_forcelist=[429, 500, 502, 503, 504]))`.
- **Logging & config.** Paths, symbol, and intervals come from
  `Settings`; the downloader takes them as constructor arguments rather
  than reading globals. All log lines route through
  `logging.getLogger("assareh.fetch")`; the entrypoint configures the
  root logger from `Settings.log_level`. No `print()`.

### Entrypoint: `scripts/fetch_binance_ohlcv.py`

- Loads `Settings`.
- Configures root logger from `Settings.log_level`.
- For each of `Settings.intervals`: calls `downloader.update(intv)`, then `downloader.update_with_ccxt(intv, verify=True)`.
- Idempotent: re-running fetches only what's new.
- Exit code 0 on success; non-zero on any checksum failure or verify failure.

### A.2 Definition of done

- Four Parquet files exist: `data/raw/btcusdt_{1m,15m,1h,4h}.parquet`
- Each file's schema matches `OHLCV_SCHEMA` exactly (9 columns,
  `open_time` UTC-tz-aware)
- `data/raw/checksums.jsonl` records the SHA256 of every Binance archive consumed
- Re-running the entrypoint downloads zero new bars and exits cleanly
- The 1m file is ~4.5M rows and ~200–300 MB Parquet
- A unit test loads each file with the A.3 loader and passes integrity

---

## A.3 — Data loader and integrity checks

### The loader: `src/assareh/data/loader.py`

```python
def load_ohlcv(
    timeframe: Literal["1m", "15m", "1h", "4h"],
    settings: Settings,
) -> pl.DataFrame:
    """Load raw OHLCV from Parquet, casting columns to OHLCV_SCHEMA types."""
```

Single function.
Path comes from `settings.raw_dir`.
Per **D-034**, the loader hard-fails if any canonical column is missing, then **casts every column to `OHLCV_SCHEMA` types** rather than asserting strict schema equality.
Rationale: the downloader writes Parquet via pandas, which round-trips `Datetime` timestamps at `ms` precision while the canonical schema specifies `us`;
a strict equality check would reject valid data that differs only in precision.
The cast is paid once at load time and guarantees downstream code always sees the canonical schema (see L-004).

### Integrity checks: `src/assareh/data/integrity.py`

```python
def check_integrity(df: pl.DataFrame, timeframe: str) -> IntegrityReport:
    ...

def check_cross_timeframe_alignment(
    dfs: dict[str, pl.DataFrame],   # {"1m": ..., "15m": ..., "1h": ..., "4h": ...}
) -> CrossTimeframeReport:
    ...
```

**Per-timeframe pathologies and what to do with each:**

- **Duplicate timestamps** — HARD FAILURE if > 0.
(Should never happen after the downloader's dedup; if it does, something is wrong.)
- **Non-monotonic timestamps** — HARD FAILURE if any out-of-order row.
- **OHLC arithmetic violations** (`high < max(open, close)` or `low > min(open, close)`) — HARD FAILURE if > 0.
- **Price out of sanity bounds** (`close < 100` or `close > 1_000_000`) —
  HARD FAILURE.
  BTC/USDT has ranged from ~$3.2K (2018–2019 lows) to well above $100K (2025 highs).
  This band catches unit errors and source corruption with wide margin on both sides and no realistic false positives.
- **NaN in OHLC** — HARD FAILURE.
- **Gaps > 1 interval** — SOFT.
  Record every gap as `GapRecord(start, end, n_missing)`.
  Don't forward-fill.
  Document any gap > 4 hours in `LEARNINGS.md` with a note on what Binance was doing.
- **Zero-volume bars** — SOFT.
  Count and record.
  Most are real (low-activity minutes in 2017–2018).
  Don't filter.
- **OHLC-equal bars** (O=H=L=C) — SOFT.
  Count and record.
  Real at low volume; useful to know the count.
- **Negative volume** — HARD FAILURE.
  Physically impossible; indicates source corruption or a parse error.
- **NaN in volume** — SOFT.
  Count by column.
- **UTC timezone** — sanity-check that `open_time` is timezone-aware UTC;
  HARD FAILURE if not (loader should have caught this, this is a backstop).

`passed = (hard_failures == [])`.
Soft observations populate the report but never flip `passed`.

**Cross-timeframe alignment (`check_cross_timeframe_alignment`):**

Phase D assembles features by joining 4h/1h/15m onto the 15m decision clock, and Phase B resolves barriers on 1m.
Both assume the four grids are mutually consistent.
Verify it once, here, rather than discovering a misalignment as a silent feature bug later:

- **Grid containment** — every 15m / 1h / 4h `open_time` must fall on the 1m
  grid (and each coarser open on every finer grid).
  HARD FAILURE on any off-grid open.
  Counts recorded in `misaligned_opens`.
- **Nominal spacing** — within each timeframe, the modal spacing must equal the
  nominal interval; count deviations (these are the same events as gaps, cross-
  checked from the other direction) in `spacing_violations`.
  SOFT — gaps are already classified per-timeframe; this is a consistency cross-check.
- **Coverage overlap** — record, per pair of timeframes, the overlapping date
  range.
  SOFT, informational: Phase B/C/D operate only on the common span.

### Tests: `tests/test_integrity.py`

Use the `synthetic_ohlcv` fixture from `conftest.py`:

```python
synthetic_ohlcv(
    rows: int,
    interval: str,
    issues: set[str] = set(),
) -> pl.DataFrame
```

Supported `issues`:
`{"duplicate", "gap", "ohlc_violation", "negative_volume", "nan_in_close", "nan_in_volume", "price_out_of_bounds", "non_monotonic", "off_grid"}`.

Required tests:

- Clean synthetic data passes integrity (`passed=True`, empty `hard_failures`).
- Each `issues` flag, planted individually, is detected and classified
  correctly (hard vs soft).
- A clean synthetic set of all four timeframes passes `check_cross_timeframe_alignment`;  
  an `off_grid` 15m series fails it.
- Real loaded data (one timeframe, e.g. 15m) passes — or, if it doesn't,
  the failure is documented in LEARNINGS.md with the gap or anomaly that
  caused it, and a decision is logged on whether to treat it as known.

### A.3 Definition of done

- `from assareh.data import load_ohlcv; df = load_ohlcv("15m", settings)` works
- `check_integrity(df, "15m")` runs and returns an `IntegrityReport`
- `check_cross_timeframe_alignment({...})` runs and returns a `CrossTimeframeReport` with `passed=True` on real data (or documented exceptions)
- All four real timeframes pass integrity, OR known soft observations are documented
- Tests pass; the `synthetic_ohlcv` fixture covers every `issues` flag

---

## A.4 — Phase A checkpoint (closed 2026-05-27)

Phase A is complete. The deliverables called out in PLAN.md and this file are
met; the entries below tick them off explicitly.

**Definition of done — verified:**

- [x] Repo skeleton matches the tree above (`src/assareh/`, `scripts/`, `tests/`,
  `data/`, `docs/`)
- [x] `uv sync` produces a working env on M-series ARM
- [x] `uv run pytest` is green (19/19 passing as of 2026-05-27)
- [x] `uv run ruff check .` and `uv run mypy src/` pass
- [x] Four Parquet files on disk: `data/raw/btcusdt_{1m,15m,1h,4h}.parquet`,
  each conforming to `OHLCV_SCHEMA`
- [x] `data/raw/checksums.jsonl` records the SHA-256 of every verified Binance
  archive (per D-019 — soft on missing CHECKSUMs)
- [x] `from assareh.data import load_ohlcv` works; `check_integrity` and
  `check_cross_timeframe_alignment` return typed reports
- [x] All four real timeframes pass `check_integrity`; cross-timeframe
  alignment hard-failures on the known Binance pre-2018 timestamp anomaly are
  documented in L-001 and bounded by the test
- [x] DECISIONS.md updated with D-018 … D-025, D-034, D-035 (the tooling stack
  is now a numbered entry, D-035; the loader-cast-vs-assert decision is D-034)
- [x] LEARNINGS.md captures L-001 (Binance timestamp offsets), L-002 (integrity
  statistics baseline), L-003 (ancillary-column unreliability), L-004 (loader
  schema-cast rationale), L-005 (missing CHECKSUM files)
- [x] Self-review pass: repo layout and code organization reviewed; no
  follow-up structural changes required before Phase B

**Out of scope, deferred to later phases:**

- pATR computation — moved to Phase B (B.0) per D-031; `attach_patr` lives at
  `src/assareh/features/patr.py`
- CI workflow — **resolved**: a minimal GitHub Actions scaffold (`uv sync`
  → `ruff` → `mypy` → `pytest`) is now a Phase B deliverable in PLAN.md,
  landing before the leakage-sensitive label/split/weight code merges
- v1 data-handling comparison — **closed in A.5 below**

---

## A.5 — v1 data-handling comparison (closed 2026-06-05)

The v1-vs-v2 data-handling comparison that A.4 flagged as a follow-up
landed here. Methodology: a self-contained audit prompt was handed to a
separate Claude session with read access to the v1 repo; the session
returned a row-per-anomaly report covering 21 numbered anomalies plus
four cross-cutting findings, each with `path/file.py:LINE` citations into
the v1 codebase.

**Findings appended to LEARNINGS.md** (each entry includes v1 code
citations and the implication for the affected v2 phase):

- L-008 — v1's default `LinearInterpolator` is non-causal (weighted
  average of *previous and next* available bar) and contaminates the
  triple-barrier target resolution.
- L-009 — v1's `DataMixer.*.load_features` applies blanket
  `btc_df.fillna(method='bfill')` to the assembled feature frame.
- L-010 — v1's `patr*` series is `ffill`+`bfill`'d *inside*
  `TargetExtractor2/3`, so barrier widths in early data depend on future
  pATR observations.
- L-011 — v1's multi-TF mix (`DataMixer3._mix_train`) walks per-TF frames
  with integer counters rather than joining on timestamp; coverage drift
  silently stitches bars from different real times.
- L-012 — v1 silently floor-snaps off-grid bars per timeframe and
  includes the L-001 Binance quirk window (2017-12-04 → 2018-02-10) in
  training with no cross-TF awareness or quirk-aware exclusion.
- L-013 — v1 has no OHLC arithmetic check at any stage; broken bars feed
  ATR / BB / Donchian and the target detector unchanged.
- L-014 — v1 silently clamps `volume < 1 → 1` (so `log_volume = 0` for
  every legitimately zero-volume bar in early data).
- L-015 — minor v1 fill and convention behaviors (catch-all): silent
  duplicate drop on snap collision, silent sort after interpolation,
  tz-naïve timestamps throughout (with implicit local-time risk in the
  seed script `add_kick_start_data_to_db.py`),
  `_create_log_alternative_candles` first-row `fillna('backfill')`, and
  the `fillna(value=33)` sentinel for "no-decision" target rows.

**New dual-arm leakage probes opened** (DECISIONS.md):

- D-036 — gap-fill discipline (label + feature pathways; motivated by L-008)
- D-037 — feature-frame NaN policy (Phase D; motivated by L-009)
- D-038 — pATR fill policy in label construction (Phase B; motivated by L-010)
- D-039 — cross-timeframe alignment method (Phase D; motivated by L-011)

All four follow D-001's leakage-probe flavor (honest primary, v1-faithful
arm run *once* to measure inflation, then retired). PLAN.md's dual-arm
catalogue was extended to two sub-groups — *statistical-discipline
probes* (D-004, D-006, D-010, D-013) and *data-handling probes* (D-036
through D-039) — and the Phase E gap artifact now reports both sub-blocks
with a cross-block interaction view.

**Qualitative finding worth recording up front.** L-008's non-causal
interpolation is the most direct contamination of the label: the
`TargetExtractor.detect_reversals` forward walk reads the *next bar's*
OHLC via the synthesized bar that fills any gap in its path. L-010's
pATR `bfill` is the second-most direct (it changes the barrier widths
the walk uses). Both are labeling-pathway leaks and both compound with
the established statistical-discipline probes (D-004 embargo, D-006
barrier resolution) because they operate before those checks see the
data. **Plausible expectation, to be confirmed by the Phase E gap
artifact:** data-handling leaks dominate the apparent v1 edge, and the
statistical-discipline leaks layer on top.

**Confirmed v1 non-issues** (no v2 probe needed, recorded for completeness):

- v1 uses CSV only — v2's D-034 Parquet schema-cast discipline has no v1
  counterpart.
- v1 doesn't read `number_of_trades` or `taker_buy_*` columns — v2's
  D-020 structural-zero handling is honest-arm-only.
- v1 doesn't verify Binance archive integrity — D-019 is v2-only.
- v1 fetches from a single source — the ccxt overlap-verification path
  is v2-only.

**Definition of done — verified:**

- [x] v1 audit report received with file:line citations for every
  numbered anomaly
- [x] L-008 through L-015 appended to LEARNINGS.md
- [x] D-036 through D-039 appended to DECISIONS.md and added to the
  index
- [x] PLAN.md updated: dual-arm catalogue re-grouped, Phase B label and
  Phase D feature deliverables wire the new probes, Phase C `evaluate()`
  arm dimensions extended, Phase E gap artifact restructured into two
  sub-blocks
- [x] A.4's deferred "v1 data-handling comparison" item closed

---
