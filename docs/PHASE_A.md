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
│   └── LEARNINGS.md       
├── .gitignore
├── .env.example           
├── src/
│   └── assareh/
│       ├── __init__.py
│       ├── config.py       
│       └── data/
│           ├── __init__.py
│           ├── schemas.py  
│           ├── loader.py   
│           └── integrity.py 
├── scripts/
│   ├── data_downloader.py        
│   └── fetch_binance_ohlcv.py    
├── tests/
│   ├── __init__.py
│   ├── conftest.py         
│   ├── test_integrity.py  
│   └── test_placeholder.py
├── data/
│   ├── raw/                
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
- Experiment tracking: MLflow with local file backend (no server in Layer 1)
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
- Never random-split time-series data. Always walk-forward.
- Never fit scalers, feature selectors, or any stateful transform on data
  outside the current training fold.
- Never reference future timestamps in features, even by one bar.
- Embargo every walk-forward fold by at least the full label horizon
  (511 15m bars). Purge any training label whose outcome window overlaps test.
- Every meaningful design decision goes in DECISIONS.md in the same commit
  as the code implementing it, with the verdict, rationale, and v1 alternative.

## Dual-arm rule
- Where v1 made a choice we improve on, keep both a v1-faithful arm and an
  honest arm, both runnable through the same harness. The honest arm is the
  trusted result; the gap is a finding. See DECISIONS.md D-001.

## Logging
- Library modules: `logger = logging.getLogger(__name__)`, no handler setup.
- Entrypoints (scripts/, __main__): configure root logger with format
  `%(asctime)s [%(levelname)s] %(name)s: %(message)s`, level from
  `Settings.log_level`.
- Never use `print()` outside notebooks.

## Paths
- All filesystem paths come from `Settings`. Library code accepts paths or
  a `Settings` instance as arguments. Never read a global.
- Tests use the `tmp_path` fixture and an override `Settings`.

## Test fixtures
- Synthetic OHLCV always comes from the `synthetic_ohlcv` fixture in
  `tests/conftest.py`. Don't reinvent it per test.

## Polars
- Lazy by default for any pipeline > 2 operations. Collect at the boundary.
- `.to_pandas()` only at the sklearn/torch boundary or when calling
  pandas-ta. Annotate the crossing with a comment.

## DECISIONS vs LEARNINGS
- DECISIONS.md: a choice between alternatives where future-you will ask
  "why did we pick that?". Logged in the same commit as the code.
- LEARNINGS.md: a finding, surprise, or dead end. Logged when discovered.

## Commits
- `<phase>.<step>: <what>`, e.g. `A.4: add binance loader and integrity checks`

## Out of scope (Layer 1)
- Other assets, hyperparameter optimization, deployment, exotic architectures.
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

**Approach:** Reuse the existing `BinanceDownloader` class.
It already implements the right strategy:
monthly ZIP archives from `data.binance.vision` for history, daily
ZIP archives for the current month, and `ccxt` as the tail filler for the
most recent bars not yet archived.
It also cross-verifies ccxt data against Vision data on the overlap before appending. Adapt rather than rewrite.

> **1m is first-class.** All four timeframes are downloaded and validated to the
> same standard. The 1m series is not a convenience copy — it is the substrate
> for barrier-touch resolution in Phase B (D-006). Treat its integrity with the
> same weight as the 15m decision-clock series.

### Required modifications before use

1. **Output format → Parquet, not CSV.**
   - `_get_file_path`: return `.parquet` instead of `.csv`
   - `download` / `update` / `update_with_ccxt`:
     `to_parquet(path, compression='zstd')`
   - `load`: read with Parquet; the downloader stays pandas internally and
     writes Parquet for the Polars loader (A.3) to consume.

2. **Schema: keep 9 columns, not 6.**
   Update `_parse_csv` to keep:
   `open_time, open, high, low, close, volume, close_time,
   number_of_trades, taker_buy_base_volume, taker_buy_quote_volume`.
   Drop only `quote_asset_volume` (redundant with close × volume) and the
   `ignore` field. Use `open_time` as the canonical index, UTC.

3. **Timezone: explicit UTC everywhere.**
   - After `pd.to_datetime(..., unit='ms')`, add `.dt.tz_localize('UTC')`.
   - Replace every `datetime.now()` with `datetime.now(timezone.utc)`.
   - Remove the `tzinfo=None` stripping in `_is_candle_complete` — compare
     in UTC directly.

4. **SHA256 checksum verification.**
   For every monthly/daily ZIP at `{url}.zip`, also fetch `{url}.zip.CHECKSUM`
   (a one-line file: `<sha256>  <filename>`). Verify the SHA256 of the
   downloaded bytes matches; reject mismatches with a hard error. Append
   verified hashes to `data/raw/checksums.jsonl` for audit.

5. **Keep timestamp auto-detection; do not pin to `ms`.**
   Binance has historically used both millisecond (13-digit) and microsecond
   (16-digit) timestamps across different data sources and time periods.
   Pinning to `ms` would silently corrupt any `us`-encoded rows. Instead,
   detect by numeric range in `_parse_csv`: ms values fall in
   `[1_262_304_000_000, 32_503_680_000_000]`, us values are 1000× larger,
   seconds values are 1000× smaller — the ranges are non-overlapping so
   detection is unambiguous. Apply the check column-wide (`.all()`) since
   Vision CSVs use a single consistent encoding per file.

6. **Logging and config.**
   - Replace every `print(...)` with stdlib `logging` (logger name
     `assareh.fetch`).
   - Inject `data_dir` from `Settings` rather than the relative default.
     The entrypoint reads `Settings`; the downloader accepts the path.

7. **Retry with backoff.**
   Wrap downloads in a `requests.Session` configured with:

   ```python
   HTTPAdapter(max_retries=Retry(
       total=5, backoff_factor=1.0,
       status_forcelist=[429, 500, 502, 503, 504],
   ))
   ```

### What to keep from the original

- Current month is skipped in monthly archives (Vision doesn't publish it
  until the month closes) and filled in via daily archives. Correct.
- `_remove_incomplete_candles` filters the currently-forming bar before
  any merge. Keep — this is what makes re-runs safe.
- ccxt overlap-verification uses 10 candles by default and a 20%-rows-differ
  failure threshold for volume. This is the right tolerance for cross-source
  comparison; do not tighten.
- The `_get_interval_config` lookback-per-interval table is well-reasoned;
  keep as-is.

### Entrypoint: `scripts/fetch_binance_ohlcv.py`

- Loads `Settings`.
- Configures root logger from `Settings.log_level`.
- For each of `Settings.intervals`: calls `downloader.update(intv)`, then
  `downloader.update_with_ccxt(intv, verify=True)`.
- Idempotent: re-running fetches only what's new.
- Exit code 0 on success; non-zero on any checksum failure or verify failure.

### Definition of done

- Four Parquet files exist: `data/raw/btcusdt_{1m,15m,1h,4h}.parquet`
- Each file's schema matches `OHLCV_SCHEMA` exactly (9 columns,
  `open_time` UTC-tz-aware)
- `data/raw/checksums.jsonl` records the SHA256 of every Vision archive
  consumed
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
    """Load raw OHLCV from Parquet. Asserts schema matches OHLCV_SCHEMA."""
```

Single function. Path comes from `settings.raw_dir`. Schema assertion is a
hard check, not a warning — if the file on disk drifts from
`OHLCV_SCHEMA`, fail loudly.

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

- **Duplicate timestamps** — HARD FAILURE if > 0. (Should never happen
  after the downloader's dedup; if it does, something is wrong.)
- **Non-monotonic timestamps** — HARD FAILURE if any out-of-order row.
- **OHLC arithmetic violations** (`high < max(open, close)` or
  `low > min(open, close)`) — HARD FAILURE if > 0.
- **Price out of sanity bounds** (`close < 100` or `close > 1_000_000`) —
  HARD FAILURE. BTC/USDT has ranged from ~$3.2K (2018–2019 lows) to well above
  $100K (2025 highs); as of writing it trades around $77K. This band catches
  unit errors and source corruption with wide margin on both sides and no
  realistic false positives.
- **NaN in OHLC** — HARD FAILURE.
- **Gaps > 1 interval** — SOFT. Record every gap as
  `GapRecord(start, end, n_missing)`. Don't forward-fill. Document any
  gap > 4 hours in LEARNINGS.md with a note on what Binance was doing.
- **Zero-volume bars** — SOFT. Count and record. Most are real (low-activity
  minutes in 2017–2018). Don't filter.
- **OHLC-equal bars** (O=H=L=C) — SOFT. Count and record. Real at low
  volume; useful to know the count.
- **Negative volume** — HARD FAILURE. Physically impossible; indicates
  source corruption or a parse error.
- **NaN in volume** — SOFT. Count by column.
- **UTC timezone** — sanity-check that `open_time` is timezone-aware UTC;
  HARD FAILURE if not (loader should have caught this, this is a backstop).

`passed = (hard_failures == [])`. Soft observations populate the report
but never flip `passed`.

**Cross-timeframe alignment (`check_cross_timeframe_alignment`):**

Phase D assembles features by joining 4h/1h/15m onto the 15m decision clock, and
Phase B resolves barriers on 1m. Both assume the four grids are mutually
consistent. Verify it once, here, rather than discovering a misalignment as a
silent feature bug later:

- **Grid containment** — every 15m / 1h / 4h `open_time` must fall on the 1m
  grid (and each coarser open on every finer grid). HARD FAILURE on any
  off-grid open. Counts recorded in `misaligned_opens`.
- **Nominal spacing** — within each timeframe, the modal spacing must equal the
  nominal interval; count deviations (these are the same events as gaps, cross-
  checked from the other direction) in `spacing_violations`. SOFT — gaps are
  already classified per-timeframe; this is a consistency cross-check.
- **Coverage overlap** — record, per pair of timeframes, the overlapping date
  range. SOFT, informational: Phase B/C/D operate only on the common span.

### Tests: `tests/test_integrity.py`

Use the `synthetic_ohlcv` fixture from `conftest.py`:

```python
synthetic_ohlcv(
    rows: int,
    interval: str,
    issues: set[str] = set(),
) -> pl.DataFrame
```

Supported `issues`: `{"duplicate", "gap", "ohlc_violation",
"negative_volume", "nan_in_close", "nan_in_volume",
"price_out_of_bounds", "non_monotonic", "off_grid"}`.

Required tests:

- Clean synthetic data passes integrity (`passed=True`, empty `hard_failures`).
- Each `issues` flag, planted individually, is detected and classified
  correctly (hard vs soft).
- A clean synthetic set of all four timeframes passes
  `check_cross_timeframe_alignment`; an `off_grid` 15m series fails it.
- Real loaded data (one timeframe, e.g. 15m) passes — or, if it doesn't,
  the failure is documented in LEARNINGS.md with the gap or anomaly that
  caused it, and a decision is logged on whether to treat it as known.

### Definition of done

- `from assareh.data import load_ohlcv; df = load_ohlcv("15m", settings)` works
- `check_integrity(df, "15m")` runs and returns an `IntegrityReport`
- `check_cross_timeframe_alignment({...})` runs and returns a
  `CrossTimeframeReport` with `passed=True` on real data (or documented
  exceptions)
- All four real timeframes pass integrity, OR known soft observations are
  documented
- Tests pass; the `synthetic_ohlcv` fixture covers every `issues` flag

---

## A.4 — Phase A checkpoint

- Update DECISIONS.md with all tooling and library choices made
- Update LEARNINGS.md with anything surprising from A.2 / A.3 (real-data gaps,
  zero-volume counts, any cross-timeframe coverage mismatch)
- Commit with `A: phase complete`
- Self-review: does the repo look like something a senior engineer would
  recognize as well-organized? Iterate once if not.

---

## Cross-cutting conventions

Captured in `CLAUDE.md` (above) for agent sessions; restated here for
human reference.

**Logging.** stdlib `logging`. Library modules:
`logger = logging.getLogger(__name__)`, no handler setup. Entrypoints
configure root logger from `Settings.log_level`. Never `print()` outside
notebooks.

**Paths.** All filesystem paths come from `Settings`. Library code accepts
paths or a `Settings` instance as arguments — never reads a global. Tests
use `tmp_path` and an override `Settings`.

**Test fixtures.** Synthetic OHLCV always comes from the `synthetic_ohlcv`
fixture in `conftest.py`. Don't reinvent it per test.

**Polars.** Lazy by default for pipelines > 2 ops; collect at the boundary.
`.to_pandas()` only at the sklearn/torch boundary or when calling pandas-ta
— annotate the crossing.

**DECISIONS vs LEARNINGS.** DECISIONS = a choice between alternatives,
logged in the same commit as the code. LEARNINGS = a finding, surprise,
or dead end, logged when discovered.
