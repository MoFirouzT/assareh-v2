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
