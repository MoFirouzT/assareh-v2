# Phase B — Target definition and split design

**Goal:**
Define the prediction target rigorously, design splits
that respect both the temporal structure and the label horizon, and lock the
evaluation-harness skeleton — all *before* writing any model.

This is the phase where most of v1's credibility problems live, and the phase
where the dual-arm methodology starts paying for itself.
Nothing here fits a model.
Everything here decides whether the eventual model's numbers will mean anything.

> **Hard prerequisite:**
> Phase A complete. Real OHLCV for all four timeframes on disk, integrity-clean, cross-timeframe aligned.
> The 1m series in particular must be trustworthy — it is the barrier-resolution substrate.

---

## Module layout (D-030)

Phase B introduces the following modules. Pin these paths now so all of B.1–B.4
land in agreed locations; downstream phases import from them:

```text
src/assareh/
  features/
    patr.py            # B.0 — multi-timeframe pATR (D-012, D-026, D-031)
  labels/
    targets.py         # B.1 — make_labels, LabelResult
    diagnostics.py     # B.2 — target_stats helper
  splits/
    splits.py          # B.3 — Fold, make_walkforward_folds
    weights.py         # B.3 — average_uniqueness, n_eff_kish, renormalize
notebooks/
  target_diagnostics.ipynb   # B.2
tests/
  test_patr.py          # B.0
  test_targets.py       # B.1
  test_splits.py        # B.3
  test_weights.py       # B.3
  conftest.py           # extended — see B.1 Tests
```

---

## B.0 — Multi-timeframe pATR (prerequisite)

`make_labels` requires the two pATR series attached to the 15m frame. The pATR
formula is locked (D-012); the multi-timeframe split is locked (D-026); the
module path is locked (D-031).

```python
# src/assareh/features/patr.py

def attach_patr(
    df15: pl.DataFrame,
    df1m: pl.DataFrame,
    *,
    window: int = 10,
    timeframes_minutes: tuple[int, ...] = (15, 60, 240),
) -> pl.DataFrame:
    """Return df15 with patr_<tf> columns attached, one per requested timeframe.

    For each timeframe `tf` in `timeframes_minutes`, computes percent ATR (pATR)
    via Wilder smoothing (window=10), directional true range via the `up_first`
    flag derived from 1m sub-candles within each tf bar, then as-of joins onto
    the 15m clock. Higher-timeframe pATR series are lagged by v1's `shift(3)`
    guard before the join — see Q4 below.
    """
```

Default output adds `patr_15`, `patr_60`, `patr_240` to `df15`. Phase D may
extend `timeframes_minutes`; Phase B only needs `patr_60` and `patr_240` (the
defaults for stop and target per D-026).

> **Open question — Q4 (`shift(3)` mechanics).** v1's `shift(3)` lag on higher-
> timeframe pATR is preserved (D-012), but the exact shift unit — 3 bars of the
> higher tf vs. 3 bars of the 15m clock — has not been pinned in v2. Investigate
> during B.0 implementation by inspecting v1's `IndicatorEngineer` /
> `FeatureEngineer`; record the verdict and rationale as a new DECISIONS.md
> entry before B.0 is marked done. Until then, `attach_patr` must accept a
> `shift_higher_tf_bars: int = 3` parameter that is **explicitly applied in the
> higher tf** as the working hypothesis.

### B.0 Tests

- Wilder recurrence: `attach_patr` on a hand-built OHLCV series matches the
  closed-form `pATR[i] = (pATR[i-1]·(n-1) + pTR[i]) / n` with `n=10` to within
  float tolerance.
- Gap-term coverage: a synthetic series with a between-bar jump exercises the
  `|H − C_prev|` / `|L − C_prev|` terms of the true range.
- `up_first` determinism: a 15m bar whose 1m sub-candles trend cleanly up has
  `up_first = 1`; cleanly down has `up_first = 0`; mixed paths resolve by the
  sign of the net move.
- `shift_higher_tf_bars` invariance: with `shift_higher_tf_bars=0` and equal
  timeframes, `patr_15 == patr_native_on_15m` (sanity).

### B.0 Definition of done

- `attach_patr` returns the canonical three pATR columns on the 15m frame
- Tests pass; Q4 resolution is committed to DECISIONS.md
- D-012, D-026, D-031 reflected; module path matches the layout above

---

## B.1 — Target definition

### What it is

The v1 three-class triple-barrier label, rebuilt cleanly with tests:

- **Profit barrier:** +4 × pATR from entry
- **Stop barrier:** −2.5 × pATR from entry
- **Vertical barrier (horizon):** `n = 16 × 16 × 2 − 1 = 511` 15m bars
  (≈ 5.3 days), matching v1's `TargetExtractor3`
- **Labels:** `+1` if the profit barrier is touched first, `−1` if the stop is
  touched first, `0` if neither is touched before the horizon expires
- **Decision cadence:** one label per 15m bar close (D-002)

pATR is produced by `attach_patr` (B.0). The formula is locked to D-012 and
the multi-timeframe split below is locked to D-026.

**Multi-timeframe pATR (D-026).** The profit target and the stop are anchored on
*different* pATR timeframes: a **longer-horizon pATR** scales the target (slow,
wide — only large moves relative to the medium-term regime count as wins) and a
**shorter-horizon pATR** scales the stop (reactive — tightens in volatile
regimes, widens in calm). The defaults follow v1's `TargetExtractor3`:
`target_patr = patr_240` (4h smoothing), `stop_patr = patr_60` (1h smoothing).
`make_labels` takes the two pATR columns separately; the asymmetry is
deliberate, not a code smell. The single-timeframe `target_patr == stop_patr ==
native_patr` configuration is retained as the v1-`TargetExtractor1` comparison
point, not as the default.

### The one place we improve on v1: barrier-touch resolution (D-006)

When the profit and stop barriers both fall inside a single bar's high–low
range, the order of touch is ambiguous from that bar's OHLC alone. v1 resolved
this on **15m** bars with the optimistic same-bar assumption (favorable barrier
assumed first). That single assumption can manufacture most of a fake edge.

We have 1m data. So:

- **Primary (honest) arm:** resolve touch order on the **1m** series. For each
  15m decision point, walk the 1m bars forward and record which barrier's price
  is reached first.
- **Comparison (v1-faithful) arm:** the 15m-optimistic resolution, reproduced
  exactly.

Both arms produce a label per decision point. The pipeline records, per arm:

1. the label series, and
2. the **same-bar-ambiguity rate** — what fraction of touches required a
   tie-break — logged at **both** the 15m and 1m grain (D-006 added detail).
   The 15m rate bounds how much the two arms can diverge; the 1m rate is
   the residual ambiguity inside a single 1m bar that straddles both
   barriers, and bounds the irreducible bias of the honest arm itself.

```python
def make_labels(
    df15: pl.DataFrame,            # 15m decision clock, with target_patr & stop_patr columns attached
    df1m: pl.DataFrame,            # 1m barrier-resolution substrate
    *,
    target_patr_col: str = "patr_240",  # longer-horizon pATR scales the profit target (D-026)
    stop_patr_col:   str = "patr_60",   # shorter-horizon pATR scales the stop (D-026)
    m_target: float = 4.0,
    m_stop: float = 2.5,
    horizon_bars: int = 511,
    resolution: Literal["1m", "15m"] = "1m",   # "15m" == v1-faithful arm (D-006)
    gap_fill: Literal["observed", "v1_noncausal"] = "observed",          # D-036 probe: gap discipline on df1m
    patr_fill: Literal["realised_only", "v1_ffill_bfill"] = "realised_only",  # D-038 probe: pATR fill inside labeler
    target2: bool = True,          # produce meta-label (target3) alongside side (rt3)
    stop2_slack: float = 1.0,      # stop2 = (1 − (m_stop + slack) × stop_patr) × price
) -> LabelResult:
    """Triple-barrier labels. resolution selects honest vs v1-faithful arm.

    Barrier construction (D-026, multi-timeframe pATR):
      profit_level = (1 + m_target × df15[target_patr_col]) × entry_price
      stop_level   = (1 − m_stop   × df15[stop_patr_col])   × entry_price
      stop2_level  = (1 − (m_stop + stop2_slack) × df15[stop_patr_col]) × entry_price

    Setting target_patr_col == stop_patr_col reproduces the single-timeframe
    v1-`TargetExtractor1` configuration (comparison only; not the default).

    gap_fill selects the data-handling probe at the 1m substrate (D-036):
      - 'observed' (honest, default): the walk halts at any missing 1m bar
        inside the horizon; unresolved labels emit typed null (D-029).
      - 'v1_noncausal': apply v1's LinearInterpolator non-causal
        weighted-average fill to df1m before the walk; reproduces L-008.

    patr_fill selects the data-handling probe at the pATR series (D-038):
      - 'realised_only' (honest, default): NaN pATR at the decision bar
        emits typed null for the row (no fabricated barrier width).
      - 'v1_ffill_bfill': apply patr_*.fillna('ffill').fillna('bfill')
        before barrier construction; reproduces L-010.

    When target2=True, returns both:
      - rt3  : raw first crossing in {-1, 0, +1}  — the side / primary label
      - target3 : meta-label — rt3 when the target is touched cleanly;
                  0 when stop2 (slack-expanded stop) is touched first.
    When target2=False, target3 == rt3 (no meta-label filtering).

    Also returns the per-decision first-touch bar index and same-bar
    ambiguity rates **at both the 15m and 1m grain** (D-006 added detail —
    the 1m rate bounds the irreducible residual bias of the honest arm) and
    the stop2 levels. Tail rows whose horizon window is incomplete carry
    `rt3 = null`, `target3 = null`, `is_complete = False` (D-029); they remain
    in the frame so the index stays aligned to the 15m clock and consumers
    filter on `is_complete` at the boundary.
    """
```

`target2=True` with `stop2_slack=1.0` reproduces v1's `TargetExtractor3`
default exactly. `target2=False` produces a plain three-class label without the
meta-label filter. Both are needed: `rt3` feeds D-014's primary side model;
`target3` feeds the meta-model. See L-006 and D-014 for the full theoretical
connection.

### `LabelResult` schema (D-029)

`LabelResult` is a single Polars `DataFrame` aligned to the 15m decision clock —
one row per 15m bar in `df15`, never reindexed or filtered. Downstream consumers
join on `open_time`. Columns:

| column                | dtype                          | meaning                                              |
|-----------------------|--------------------------------|------------------------------------------------------|
| `open_time`           | `Datetime("us", tz="UTC")`     | 15m decision-clock timestamp (key)                   |
| `rt3`                 | `Int8` (nullable)              | side label ∈ {−1, 0, +1}; `null` for tail rows       |
| `target3`             | `Int8` (nullable)              | meta-label; equals `rt3` when `target2=False`        |
| `first_touch_idx_1m`  | `Int64` (nullable)             | 1m bar index of first barrier touch (or `null`)      |
| `entry_price`         | `Float64`                      | 15m close at decision time (D-027)                   |
| `profit_level`        | `Float64`                      | `(1 + m_target × target_patr) × entry_price`         |
| `stop_level`          | `Float64`                      | `(1 − m_stop × stop_patr) × entry_price`             |
| `stop2_level`         | `Float64`                      | `(1 − (m_stop + slack) × stop_patr) × entry_price`   |
| `ambig_15m`           | `Boolean`                      | both barriers in the same 15m bar at first touch     |
| `ambig_1m`            | `Boolean`                      | both barriers in the same 1m bar (residual, honest)  |
| `is_complete`         | `Boolean`                      | `False` for tail rows; `True` otherwise              |

Scalar diagnostics (per-arm ambiguity rates, no-touch fraction, etc.) are
returned in `LabelResult.attrs` (a dict stored alongside the DataFrame by the
labeler), not as columns. The DataFrame is the primary artifact; the dict is
read by B.2's `target_stats` helper.

**Tail-row policy (D-029).** Rows whose `t + horizon_bars` exceeds the end of
`df1m` carry `rt3 = null`, `target3 = null`, `first_touch_idx_1m = null`, and
`is_complete = False`. They remain in the frame so the index stays aligned to
the 15m clock; consumers filter on `is_complete` (or drop nulls in `rt3`) at
the boundary.

### Entry-price convention (D-027)

The barriers at decision time `t` are anchored on the **close of the 15m bar
at `t`**, reproducing v1 exactly:

```text
entry_price  = df15["close"][t]
profit_level = (1 + m_target × df15[target_patr_col][t]) × entry_price
stop_level   = (1 − m_stop   × df15[stop_patr_col][t])   × entry_price
stop2_level  = (1 − (m_stop + stop2_slack) × df15[stop_patr_col][t]) × entry_price
```

The forward walk scans `df1m` strictly **after** the 15m close timestamp at `t`,
so no 1m bar that falls inside the entry 15m bar contributes to the label.

### 1m intra-bar tie-break (D-028)

When a single 1m bar's high–low range contains *both* barriers, the order of
first touch inside that 1m bar is unidentified from OHLC alone (D-006 added
detail). The honest arm resolves it deterministically using the bar's net
direction:

- If `close > open`: assume the **high was touched first** → if that 1m bar
  hits the profit barrier, label `+1`; if it hits the stop, label `−1`.
- If `close ≤ open`: assume the **low was touched first** → if that 1m bar hits
  the stop, label `−1`; if it hits the profit barrier, label `+1`.

This rule mirrors the price path the close-vs-open relation already implies
without re-using the `up_first` flag (which is computed from a *different*
1m-window aggregation for pATR and would couple the labeler to a feature signal
it should be independent of). Bars flagged `ambig_1m = True` are exactly the
bars where this tie-break is invoked; the rate is logged in B.2.

### Forward-walk vectorization (D-033)

Naive iteration is ~2.3B 1m lookups (306K decisions × ~7.7K bars each) and
unacceptably slow. The honest-arm resolution is implemented in Polars without a
Python loop over decision points:

1. Build a per-decision boolean mask on `df1m`:
   `hit_target = df1m["high"] >= profit_level_for_decision_t` (broadcast).
   This is built as a join-on-window, not a Cartesian product — see step 3.
2. Same for `hit_stop = df1m["low"] <= stop_level_for_decision_t` and
   `hit_stop2 = df1m["low"] <= stop2_level_for_decision_t`.
3. Use a Polars window-join (`join_asof` with `by="decision_t"` and a range
   filter `1m.open_time ∈ (15m.close_time[t], 15m.close_time[t] + horizon)`) to
   find the **first** 1m bar in each decision's horizon where any hit fires.
   The arg-min over 1m index is a `groupby(decision_t).first()` after sorting.
4. Apply the D-028 tie-break only on rows flagged `ambig_1m`.

The whole pipeline stays lazy until the final `.collect()` at the boundary,
per the Polars convention in CLAUDE.md.

### Data-handling leakage probes (D-036, D-038)

Two probes from the v1 audit (L-008, L-010) land at this step rather than
in feature engineering, because both affect the *label's* dependence on
data beyond `t`. Each is a leakage probe per D-001 — honest arm primary,
v1-faithful arm run *once* to measure inflation, then retired.

**Gap-fill discipline (D-036).** The 1m forward walk consumes `df1m` for
barrier resolution. If a 1m bar is missing inside a decision's horizon
window:

- *Honest arm* (`gap_fill="observed"`, default). The walk halts at the
  first missing 1m bar in its forward path. If no barrier was touched
  before the gap, the label emits typed null (`rt3 = null`,
  `target3 = null`, `is_complete = False`, per D-029). The conservative
  rule (any in-window gap → unresolvable) is the spec default; a refined
  rule that emits null only when the gap could have changed the outcome
  is a tracked follow-up for after B.2 quantifies how much sample the
  conservative rule costs.
- *v1-faithful arm* (`gap_fill="v1_noncausal"`). Apply v1's
  `LinearInterpolator._estimate_ohlcv_and_insert_the_candles` non-causal
  weighted-average fill to `df1m` before the walk. Synthesized bars
  participate in barrier resolution; resulting labels carry the
  future-bar contamination L-008 documents.

**pATR fill policy (D-038).** Barriers at `t` are sized from
`target_patr_col[t]` and `stop_patr_col[t]`. When either is NaN at `t`
(series start, gap-adjacent, indicator warm-up):

- *Honest arm* (`patr_fill="realised_only"`, default). Emit typed null
  for the entire `LabelResult` row — the label is unresolvable without
  a realised barrier width at `t`.
- *v1-faithful arm* (`patr_fill="v1_ffill_bfill"`). Apply
  `target_patr_col.fillna(method='ffill').fillna(method='bfill')` (and
  the same for `stop_patr_col`) on a *copy* of the relevant columns
  before barrier construction. Reproduces the chain `TargetExtractor2`
  and `TargetExtractor3` run internally; resulting barriers carry the
  future-pATR contamination L-010 documents. The fill operates on a
  copy so the input `df15` is not mutated.

Both arms share every other code path — the forward-walk vectorization,
the entry-price convention (D-027), the 1m intra-bar tie-break (D-028),
the `LabelResult` schema (D-029). The two probe parameters compose
independently with `resolution` (D-006), giving `2 × 2 × 2 = 8` arm
configurations at the labeler. The trial set in D-008's `V` accounting
must include these as distinct trials; B.4's pre-registration pins this.

### Leakage discipline

- The label at decision time `t` uses only bars **after** `t` for the forward
  path, and only data available **at or before** `t` for the entry price and
  pATR. No bar that produced the label may also appear inside the feature window
  for the same sample (Phase D enforces the feature side; B.1 enforces the label
  side).
- Tail rows with an incomplete horizon window are sentineled per D-029 — typed
  `null` in `rt3` / `target3`, `is_complete = False`, row retained for index
  alignment. Consumers filter on `is_complete` at the boundary; never
  partially labeled, never forward-filled. (v1's `fillna(33)` collapsed
  unlabeled rows into the negative class; the typed-null replacement preserves
  the unobservability rather than fabricating it.)

### B.1 Tests

B.1 tests use a new fixture `synthetic_barrier_path` in `tests/conftest.py`
that builds matched 1m / 15m OHLCV plus pATR columns from a `PathSpec`
(e.g. "+2σ at bar 100, −3σ at bar 200, flat thereafter") so each test
prescribes a controlled price path. The Phase-A `synthetic_ohlcv` fixture is
unchanged — barrier-path tests are a separate concern.

- A handcrafted 1m path that touches profit-then-stop labels `+1`; stop-then-
  profit labels `−1`; neither labels `0`.
- A path where both barriers fall in one 15m bar but the 1m sub-path clearly
  hits the stop first → honest arm `−1`, v1-faithful arm `+1`. This test *is* the
  D-006 finding in miniature; assert the two arms disagree on exactly this case.
- A path where both barriers fall in **one 1m bar** (residual ambiguity).
  Construct two variants — `close > open` and `close < open` — and assert the
  D-028 tie-break resolves each deterministically; assert `ambig_1m = True`.
- Horizon boundary: a touch on the last in-window bar counts; a touch one bar
  past the horizon yields `0`.
- Entry-price convention (D-027): a synthetic 15m bar whose close differs from
  its open by a known amount; assert `entry_price == close_15m_at_t` exactly and
  that barriers are anchored on that value, not the open or `next_open`.
- Tail rows with an incomplete window carry `is_complete = False`, `rt3 = null`,
  and the row remains in the frame (D-029).
- Gap-fill discipline (D-036). A handcrafted path where:
  - *(a)* the honest arm resolves a barrier *before* an in-horizon gap →
    label is non-null and matches the resolution.
  - *(b)* the honest arm reaches an in-horizon gap before any barrier
    touch → label is typed null with `is_complete = False`.
  - *(c)* the v1-faithful arm (`gap_fill="v1_noncausal"`) on the same
    input synthesizes the gap via non-causal weighted average and
    produces a non-null label.

  Assert (b) and (c) on the same input give different `LabelResult`
  rows — this is the D-036 probe in miniature.
- pATR fill policy (D-038). A path where `target_patr_col[t]` or
  `stop_patr_col[t]` is NaN at the decision bar (e.g., before Wilder
  warm-up, or at the bar immediately after a gap that L-001 documents).
  - Honest arm (`patr_fill="realised_only"`, default): row emits typed
    null.
  - v1-faithful arm (`patr_fill="v1_ffill_bfill"`): pATR is filled from
    a later realised value, barriers are computed from the filled width,
    label is non-null.

  Assert the two arms produce different rows on the same input — this
  is the D-038 probe in miniature.

### B.1 Definition of done

- `make_labels(...)` produces both arms with identical interfaces
- Both `rt3` (side / primary label) and `target3` (meta-label) are returned
  when `target2=True`; `stop2` levels are included in `LabelResult`
- All tests pass, including the deliberate honest-vs-v1 disagreement case
- A test asserts that when `stop2` is touched before the target,
  `target3 = 0` while `rt3` still records the raw direction — confirming
  the meta-label logic is correct independent of resolution arm
- Same-bar ambiguity rate is computed and logged at both 15m and 1m grain
- `LabelResult` schema (D-029) is honored; tail rows sentineled but retained
- Entry-price convention (D-027) and 1m intra-bar tie-break (D-028) are
  implemented and exercised by tests
- `gap_fill` and `patr_fill` arm parameters wired into `make_labels` with
  the honest defaults (`"observed"`, `"realised_only"`); the v1-faithful
  values (`"v1_noncausal"`, `"v1_ffill_bfill"`) reproduce v1's L-008 and
  L-010 behaviors and pass the dedicated D-036 / D-038 tests above
- D-002, D-003, D-006, D-012, D-014, D-026, D-027, D-028, D-029, D-033,
  D-036, D-038 entries reflected in DECISIONS.md (D-033 governs the
  Polars forward-walk strategy; D-036 and D-038 are the data-handling
  leakage probes from the v1 audit)

---

## B.2 — Target statistics and diagnostics

Before trusting the target, characterize it. A `notebooks/target_diagnostics.ipynb`
plus a small `target_stats(labels, ...) -> dict` helper.

**Required statistics:**

- **Class balance:** fraction `+1` / `0` / `−1` overall. v1 reported ~9.3%
  positive; confirm and record the full three-class split.
- **Timeout (no-touch) rate:** the fraction labeled `0` because the horizon
  expired. v1 never logged this; it is essential for understanding the base rate
  and for the no-touch decision (D-003).
- **Distribution over time:** class fractions per calendar quarter. Crypto's
  regimes (2017/2021 bull, 2018/2022 bear, 2023–2025 recovery and 2025 pullback)
  will move the positive rate substantially. Plot it.
- **Label run-length / overlap:** the median forward distance to first touch.
  This is the practical measure of how much adjacent labels overlap, and it sets
  expectations for the effective sample size (B.3) and the embargo (D-004).
- **Breakeven reference (D-007):** write down, in the notebook and in
  DECISIONS.md, that the pre-cost breakeven hit rate is
  `2.5 / (4 + 2.5) = 38.5%`. Every precision number from here on is judged
  against this, not against 50%.

**Definition of done:**

- The notebook renders all of the above on real data
- The timeout rate and the per-quarter positive rate are written to LEARNINGS.md
- The 38.5% breakeven reference is recorded in DECISIONS.md (D-007)

---

## B.3 — Walk-forward CV, purging, embargo, and sample weights

This is the heart of the phase. Three things v1 got wrong or skipped — geometry,
embargo, and uniqueness — are fixed here, with the v1 configuration retained for
measurement.

### Walk-forward geometry (D-010, concretized)

- **Primary (honest) arm:** multi-fold walk-forward, expanding and anchored
  (train always starts at the beginning of the common span); each successive
  fold extends train and slides val/test forward.
- **Concrete sizing (D-010 added detail):**

  | param                | value                          | rationale                                            |
  |----------------------|--------------------------------|------------------------------------------------------|
  | `n_folds`            | **8**                          | enough folds for D-008's K-of-N to be meaningful; not so many a deep model can't be retrained per fold |
  | initial-train anchor | **~2 years** (~70,000 bars)    | regime diversity before fold 1                       |
  | `test_fold_bars`     | **~8,640** (≈ 1 quarter)       | "months, not weeks"; one calendar quarter per fold   |
  | `val_fold_bars`      | **~4,032** (≈ 6 weeks)         | threshold tuning + early stopping                    |
  | `slide_step_bars`    | **= `test_fold_bars`**         | non-overlapping test folds                           |
  | `embargo_bars`       | **511** each side              | D-004 default                                        |

  Total span consumed ≈ 2y anchor + 8 × (val + test) + embargos ≈ 6 years;
  ~2.75 y headroom rolls into the expanding-train tail. Each major regime
  (2017/2021 bull, 2018/2022 bear, 2023–25 recovery, 2025 pullback) lands in
  at least one test fold.
- **Comparison (v1-faithful) arm:** the single 75 / 15 / 10 chronological split
  (`training_portion=0.75`, the 15% early-stopping "test", the 10% held-out
  "val"), reproduced exactly. Run once, to report "v1's split gave X; the walk-
  forward honest number is Y."

This is the one collision where v1 conflicts with the project's own hard rule
("always walk-forward"). The honest arm is primary and non-negotiable; the v1
split is a single comparison point, not a co-equal default. See D-010.

### Purging and embargo (D-004)

The label horizon is 511 bars. A training label whose forward window reaches into
a test fold leaks the test period's outcome into training. v1 only overlapped the
*feature* window backward (~20 steps) and never embargoed the *label* horizon —
so this leak was unguarded.

- **Purge:** drop any training sample whose label-outcome window overlaps the
  test fold at all.
- **Embargo:** additionally exclude a buffer of **≥ 511 bars** (the full
  horizon) on the test-adjacent side, so no near-boundary training label can see
  test-period bars. Default embargo = `horizon_bars`.
- **Leakage probe:** run the honest geometry once with embargo = 0 (the v1-style
  no-embargo condition) to measure how much the unguarded leak was worth. Record
  the delta in LEARNINGS.md, then retire the zero-embargo config.

### Sample weights (D-005, D-017)

Overlapping labels break the i.i.d. assumption twice over — in training and in
the width of any confidence interval.

- **Class-imbalance weights:** keep v1's `w0 = fraction_negative`,
  `w1 = fraction_positive` (essential at ~9.3% positive).
- **Average-uniqueness weights:** layer LdP ch. 4 average-uniqueness on top.
  Final per-sample weight = `class_weight × uniqueness_weight`.
  - Concurrency: `c_t = Σ_i 1[t_{i,0} ≤ t ≤ t_{i,1}]`.
  - Average uniqueness: `ū_i = (1/|window_i|) · Σ_{t∈window_i} (1/c_t)` —
    `|window_i|` is the **bar count** of sample `i`'s label window, not a
    concurrency value. Sanity property: `ū_i = 1` when all `c_t = 1`.
  - **Scope:** concurrency and uniqueness are computed on **training-fold
    labels only** (label windows confined to the fold). Computing across the
    full series leaks test-period overlap structure into training weights.
- **No time decay (D-017).** The piecewise-linear time-decay factor on
  cumulative uniqueness (LdP ch. 4) is disabled (`c = 1`). Walk-forward
  retraining already adapts to regime drift; further decay would shrink an
  already-small `N_eff` for marginal gain.
- **Renormalization.** After `class × uniqueness`, renormalize per-fold so
  the weight sum equals `N` (the training-fold row count). This keeps the
  effective learning rate independent of fold size and is asserted in a test.
- **Effective sample size (Kish):** `N_eff = (Σ w_i)² / Σ w_i²`, used as the
  denominator in every interval (`SE ≈ σ/√N_eff`). Expect `N_eff` one-to-two
  orders of magnitude below the raw row count given the 511-bar overlap. A
  headline precision reported without an `N_eff`-based interval is not finished.

```python
# src/assareh/splits/splits.py — the single source of truth for fold membership
@dataclass(frozen=True)
class Fold:
    fold_id: int
    train_idx: np.ndarray   # post-purge, post-embargo
    val_idx: np.ndarray     # threshold tuning + early stopping
    test_idx: np.ndarray    # held-out, scored once per fold
    embargo_bars: int

def make_walkforward_folds(
    index: pl.Series,                # 15m decision-clock open_times
    *,
    horizon_bars: int = 511,
    n_folds: int = 8,                # D-010 added detail
    anchor_train_bars: int = 70_000, # ~2 years of 15m
    test_fold_bars: int = 8_640,     # ~1 calendar quarter
    val_fold_bars: int = 4_032,      # ~6 weeks
    embargo_bars: int = 511,
    scheme: Literal["walkforward", "v1_single", "cpcv"] = "walkforward",
) -> list[Fold]:
    """Single source of truth for what is train/val/test in every fold.

    - 'walkforward' (default, D-010): expanding-anchored multi-fold, sizes above.
    - 'v1_single':  one 75/15/10 chronological split, reproduced exactly.
    - 'cpcv' (D-016, compute-gated): combinatorial purged CV; implementation
      lands in Phase C, but the scheme value is reserved in the B.3 API so
      Phase C consumers don't reshape it.
    """

# src/assareh/splits/weights.py
def average_uniqueness(label_spans: np.ndarray) -> np.ndarray:
    """LdP ch.4 average uniqueness per sample.

    label_spans: shape (n, 2), int64 — columns are (start_idx, end_idx_exclusive)
    into the 15m decision clock. Contiguous-memory ndarray chosen (D-032) for
    vectorized concurrency / uniqueness computation across the numpy boundary.
    """
```

### B.3 Tests

- No `train_idx` sample's label-outcome window overlaps its fold's `test_idx`
  (purge correctness).
- The gap between the last train bar and the first test bar is ≥ `embargo_bars`
  (embargo correctness).
- `val` precedes `test` chronologically in every fold; no fold's test precedes
  its own train.
- `scheme='v1_single'` reproduces the documented 75/15/10 boundaries exactly.
- `average_uniqueness` on a synthetic set of fully-overlapping labels approaches
  `1/n`; on fully-disjoint labels approaches `1.0`.

### B.3 Definition of done

- `splits.py` is the *only* place fold membership is defined; nothing downstream
  recomputes it
- Purge + embargo tested and correct; default embargo = horizon
- Uniqueness weights and `N_eff` (Kish) computed on **training-fold labels
  only**, with `weight = class × uniqueness` renormalized per fold to sum
  to `N` (asserted in a test); no time decay (D-017)
- `walkforward` and `v1_single` schemes produced from one function; the
  `cpcv` scheme value is reserved in the signature for Phase C (D-016)
- Concrete fold geometry (n_folds=8, anchor≈2y, test≈1Q, val≈6w) wired into
  defaults; the trial set (folds × dual arms × baselines) is the V source
  for D-008
- D-004, D-005, D-010, D-017, D-032 reflected in DECISIONS.md; D-016 status
  updated to reflect the reserved scheme value

---

## B.4 — Pre-registration and checkpoint

### Pre-register the success threshold (D-008)

v1 had no success condition, so "success" was whatever the numbers happened to
be. Fix that here, before any model exists, so Phase E cannot retrofit the bar.

Concrete pre-registered condition (D-008 added detail, this phase):

> The hypothesis is confirmed if the honest arm achieves **out-of-sample,
> net-of-cost precision-at-threshold above the cost-adjusted breakeven**
> (D-007 added detail; not the bare 38.5%, which is pre-cost) with an
> `N_eff`-based confidence interval excluding that bar, on **at least 5 of
> the 8 walk-forward test folds**, with **Deflated Sharpe Ratio > 0.95**
> on the aggregated out-of-sample equity curve and **PBO < 0.2**.

Pinned values, before any model is fit:

| parameter         | value                       | source              |
|-------------------|-----------------------------|---------------------|
| `N` (total folds) | **8**                       | D-010 added detail  |
| `K` (pass folds)  | **5** (60% pass rate)       | this phase          |
| DSR confidence    | **0.95**                    | default             |
| PBO ceiling       | **0.2**                     | default             |
| `V` source        | **trial-set estimator**: variance of Sharpe across `folds × dual-arm configurations × baselines`. Dual-arm configurations cover the full catalogue per Phase C `evaluate()`'s `arm` parameter (8 leakage probes + 2 retained comparison arms); all logged to MLflow | D-008 added detail (option b); D-036–D-039 expansion |

The `V` source is the trial-set estimator (not reduced CPCV), because
pre-registration must complete at the end of Phase B and the CPCV path
requires Phase-E model output. CPCV remains available in Phase C as a
secondary `V` source if the trial-set estimator turns out to be too narrow.

The point of pre-registration is that these are fixed before any model
output exists. They are now fixed.

### Checkpoint

- DECISIONS.md updated with D-002 … D-033 (those not already written in B.0–B.3),
  including the new entries for entry price (D-027), intra-bar tie-break (D-028),
  `LabelResult` schema (D-029), module layout (D-030), pATR module location
  (D-031), and forward-walk vectorization (D-033); status updates on D-008
  (pinned values, expanded V trial-set), D-010 (concrete sizing), D-015 (out of
  scope for this iteration), and D-016 (scheme value reserved). The
  data-handling probes D-036 (gap-fill discipline) and D-038 (pATR fill policy
  in labeler) are wired into `make_labels` at this phase per the v1 audit
  (L-008, L-010); D-037 and D-039 are Phase D concerns and remain Proposed-but-
  not-yet-implemented at the B checkpoint
- LEARNINGS.md updated with the target diagnostics, the same-bar ambiguity rate
  at both grains, the Q4 `shift(3)` verdict from B.0, and the embargo
  leakage-probe delta if run
- `attach_patr`, `make_labels`, `make_walkforward_folds`, `average_uniqueness`
  and their tests committed and green
- Commit `B: phase complete`
- Self-review against the gate: **C must be able to consume `splits.py` and the
  label arms without knowing anything about a model.** If the harness in Phase C
  would need to reach back into target or split internals, the interface is wrong
  — fix it before moving on.

---

## What Phase B deliberately does **not** do

- No features, no indicators beyond pATR (Phase D)
- No scalers fit (Phase D, per-fold only)
- No model, no training, no thresholds tuned against test (Phase C/E)
- No feature selection (Phase D)
- **No CUSUM event filter (D-015).** Out of scope for this iteration; honest-arm
  cadence stays at every 15m close (D-002). Revisit in a follow-on iteration if the
  base-rate / overlap diagnostics in B.2 motivate it.
- **No CPCV implementation in Phase B (D-016).** The `cpcv` scheme value is
  reserved in `make_walkforward_folds` so Phase C consumers don't reshape the
  API, but the implementation lands in Phase C.
- **No feature-side data-handling probes (D-037, D-039).** Phase B wires
  D-036 and D-038 at the labeling step because both directly affect the
  label's dependence on data beyond `t`. The *feature-side* of D-036 (the
  same interpolated 1m / 15m / 1h / 4h series feeding indicators), plus
  D-037 (`DataMixer`'s blanket `bfill`) and D-039 (cross-TF mixing method),
  are Phase D's responsibility and land in feature assembly. Phase B does
  not preemptively define their arm parameters or assemble multi-TF
  features; that boundary is the same one D-010's purge / embargo
  enforces in the temporal direction.

If you find yourself wanting any of these to "see if the target works," stop:
that impulse is exactly what the phase ordering exists to prevent.
