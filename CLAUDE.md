# Assareh project conventions

## Hard rules — never violate
- Never random-split time-series data. Always walk-forward.
- Never fit scalers, feature selectors, or any stateful transform on data
  outside the current training fold.
- Never reference future timestamps in features, even by one bar.
- Every meaningful design decision goes in DECISIONS.md in the same commit
  as the code implementing it.

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

Do not open a Markdown preview, Simple Browser, or any preview tab.