# Phase B — Target definition and split design

**Goal:** Define the prediction target rigorously, design walk-forward splits
that respect both the temporal structure and the label horizon, and lock the
evaluation-harness skeleton — all *before* writing any model.

This is the phase where most of v1's credibility problems live, and the phase
where the dual-arm methodology (DECISIONS.md D-001) starts paying for itself.
Nothing here fits a model. Everything here decides whether the eventual model's
numbers will mean anything.

> **Hard prerequisite:** Phase A complete. Real OHLCV for all four timeframes on
> disk, integrity-clean, cross-timeframe aligned. The 1m series in particular
> must be trustworthy — it is the barrier-resolution substrate (B.1 / D-006).

---

## B.0 — Reading (do this first)

~8 hours, before writing code. This is the highest-leverage learning in Layer 1.

- **López de Prado, ch. 3 — Labeling.** The triple-barrier method and meta-
  labeling. This *is* our target. Read closely.
- **ch. 4 — Sample weights.** Overlapping outcomes, average uniqueness,
  sequential bootstrap. Directly informs B.3's uniqueness weighting.
- **ch. 7 — Cross-validation in finance.** Purging and embargo. Directly
  informs B.3's walk-forward scheme.
- **Skim ch. 11–12 — Backtest overfitting.** CSCV, Probability of Backtest
  Overfitting, Deflated Sharpe Ratio. Informs the success threshold (B.5) and
  the Phase C metrics. You don't need to implement all of it, but the success
  bar should be set with these failure modes in mind.

Log one LEARNINGS.md entry capturing the two or three ideas that change how you
were going to build the target or the splits. If nothing changed your plan, you
either already knew it or didn't read closely enough.

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

pATR is the v1 proportional ATR (Wilder smoothing, window 10, directional true
range via the `up_first` flag from 1m sub-candles). It is reproduced exactly and
locked — see D-012. Keep v1's `shift(3)` lag on higher-timeframe pATR; it is the
existing guard against current-bar bleed.

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
2. the **same-bar-ambiguity rate** — what fraction of touches required a tie-
   break — which bounds how much the two arms can possibly diverge.

```python
def make_labels(
    df15: pl.DataFrame,            # 15m decision clock, pATR attached
    df1m: pl.DataFrame,            # 1m barrier-resolution substrate
    *,
    m_target: float = 4.0,
    m_stop: float = 2.5,
    horizon_bars: int = 511,
    resolution: Literal["1m", "15m"] = "1m",   # "15m" == v1-faithful arm
) -> LabelResult:
    """Triple-barrier labels. resolution selects honest vs v1-faithful arm.

    Returns labels in {-1, 0, +1}, the per-decision first-touch bar index,
    and the same-bar ambiguity rate. Tail rows whose horizon window is
    incomplete are returned as a null/sentinel label and dropped downstream.
    """
```

### Leakage discipline

- The label at decision time `t` uses only bars **after** `t` for the forward
  path, and only data available **at or before** `t` for the entry price and
  pATR. No bar that produced the label may also appear inside the feature window
  for the same sample (Phase D enforces the feature side; B.1 enforces the label
  side).
- Tail rows with an incomplete horizon window are labeled with a sentinel and
  dropped — never partially labeled, never forward-filled. (v1's `fillna(33)` on
  the tail did exactly this; keep the behavior, drop the magic number in favor of
  a typed null.)

### Tests

- A handcrafted 1m path that touches profit-then-stop labels `+1`; stop-then-
  profit labels `−1`; neither labels `0`.
- A path where both barriers fall in one 15m bar but the 1m sub-path clearly
  hits the stop first → honest arm `−1`, v1-faithful arm `+1`. This test *is* the
  D-006 finding in miniature; assert the two arms disagree on exactly this case.
- Horizon boundary: a touch on the last in-window bar counts; a touch one bar
  past the horizon yields `0`.
- Tail rows with an incomplete window are dropped, not mislabeled.

### Definition of done

- `make_labels(...)` produces both arms with identical interfaces
- All tests pass, including the deliberate honest-vs-v1 disagreement case
- Same-bar ambiguity rate is computed and logged for both arms
- D-002, D-003, D-006, D-012 entries written to DECISIONS.md

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

### Walk-forward geometry (D-010)

- **Primary (honest) arm:** multi-fold walk-forward. Expanding, anchored window
  (train always starts at the beginning of the common span); each successive
  fold extends train and slides val/test forward. Fold count chosen so each test
  fold spans a *meaningful* market period (months, not weeks) and so at least one
  test fold lands in each major regime where data allows.
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

### Sample weights (D-005)

Overlapping labels break the i.i.d. assumption twice over — in training and in
the width of any confidence interval.

- **Class-imbalance weights:** keep v1's `w0 = fraction_negative`,
  `w1 = fraction_positive` (essential at ~9.3% positive).
- **Average-uniqueness weights:** layer LdP ch. 4 average-uniqueness on top.
  Final per-sample weight = `class_weight × uniqueness_weight`.
- **Effective sample size:** compute `N_eff` from the uniqueness weights and use
  it — not the raw row count — when forming confidence intervals on test metrics
  in Phase C. A headline precision reported without an `N_eff`-based interval is
  not finished.

```python
# splits.py — the single source of truth for fold membership
@dataclass(frozen=True)
class Fold:
    fold_id: int
    train_idx: np.ndarray   # post-purge, post-embargo
    val_idx: np.ndarray     # threshold tuning + early stopping
    test_idx: np.ndarray    # held-out, scored once per fold
    embargo_bars: int

def make_walkforward_folds(
    index: pl.Series,          # 15m decision-clock open_times
    horizon_bars: int = 511,
    n_folds: int = ...,        # chosen per the geometry rule above
    embargo_bars: int = 511,
    scheme: Literal["walkforward", "v1_single"] = "walkforward",
) -> list[Fold]:
    """Single source of truth for what is train/val/test in every fold.
    scheme='v1_single' returns the one 75/15/10 chronological split.
    """

def average_uniqueness(label_spans: list[tuple[int, int]]) -> np.ndarray:
    """LdP ch.4 average uniqueness per sample, from label outcome spans."""
```

### Tests

- No `train_idx` sample's label-outcome window overlaps its fold's `test_idx`
  (purge correctness).
- The gap between the last train bar and the first test bar is ≥ `embargo_bars`
  (embargo correctness).
- `val` precedes `test` chronologically in every fold; no fold's test precedes
  its own train.
- `scheme='v1_single'` reproduces the documented 75/15/10 boundaries exactly.
- `average_uniqueness` on a synthetic set of fully-overlapping labels approaches
  `1/n`; on fully-disjoint labels approaches `1.0`.

### Definition of done

- `splits.py` is the *only* place fold membership is defined; nothing downstream
  recomputes it
- Purge + embargo tested and correct; default embargo = horizon
- Uniqueness weights and `N_eff` computed and available to Phase C
- Both `walkforward` and `v1_single` schemes produced from one function
- D-004, D-005, D-010 entries written to DECISIONS.md

---

## B.4 — Pre-registration and checkpoint

### Pre-register the success threshold (D-008)

v1 had no success condition, so "success" was whatever the numbers happened to
be. Fix that here, before any model exists, so Phase E cannot retrofit the bar.

Write into DECISIONS.md (D-008) a concrete, falsifiable condition, e.g.:

> The hypothesis is confirmed if the honest arm achieves **out-of-sample,
> net-of-cost precision-at-threshold above the 38.5% breakeven** with an
> `N_eff`-based confidence interval excluding 38.5%, on **at least K of the N
> walk-forward test folds**, and a **Deflated Sharpe Ratio > 0** on the
> aggregated out-of-sample equity curve.

Pick the actual K, N, and any Sharpe floor now and commit them. The point is not
the exact values — it's that they are fixed before you can see the model's
output.

### Checkpoint

- DECISIONS.md updated with D-002 … D-012 (those not already written in B.1–B.3)
- LEARNINGS.md updated with the target diagnostics, the same-bar ambiguity rate,
  and the embargo leakage-probe delta if run
- `splits.py`, `targets.py`, and their tests committed and green
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

If you find yourself wanting any of these to "see if the target works," stop:
that impulse is exactly what the phase ordering exists to prevent.
