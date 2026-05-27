# DECISIONS

This file is the append-only log of design decisions.

## Tooling choices

- Package manager: `uv` (fast, modern, lockfile-backed, has native ARM support)
- Python: 3.12 (latest well-supported for ARM)
- Dataframes:
  - `polars` for I/O and preprocessing (better element, learning objective)
  - `pandas` for sklearn/torch
- Config: `pydantic-settings` (typed, env-aware settings and easier to override)
- Experiment tracking: `mlflow` with local file backend for Layer 1
- Testing: `pytest` with `tests/` discovery
- Linting: `ruff` (fast formatter/linter)
- Type checking: `mypy` (gradual; `ignore_missing_imports = true` initially)
- Logging: stdlib `logging` (no structlog)

## Loading Data

### Negative volume is a hard integrity failure

Negative volume is physically impossible.
It indicates source corruption or a parse error — not a data quirk like a zero-volume bar (which is real at low-activity periods).

---

### Loader casts to OHLCV_SCHEMA rather than asserting exact match

The downloader writes Parquet via pandas, which may round-trip timestamps at
a different precision (ms vs us).
A strict schema comparison would reject valid data that differs only in precision.
The loader now reads the Parquet, checks for missing columns (hard error), then casts every column to the canonical OHLCV_SCHEMA type.
This guarantees the output schema is always correct without rejecting recoverable mismatches.

---

## D-001 — Dual-arm methodology (governing rule)

- **Date:** 2026-05-22 — **Phase:** B (applies B→F) — **Status:** Accepted
- **Decision.** Wherever v1 made a choice we want to improve on, keep **two
  arms**: a *v1-faithful* arm that reproduces v1 exactly (so comparison to v1's
  reported numbers is valid) and an *honest* arm that is methodologically
  correct. Both run through the same harness (Phase C). The honest arm is the
  trusted result; the v1-faithful arm is reported alongside; the **gap is a
  finding**. Where the v1 choice is a defect rather than a design (D-004, D-006,
  D-011, D-013), the honest arm is primary and the v1 config is run *once* as a
  **leakage/optimism probe** to measure the inflation, then retired.
- **v1 behavior.** Single configuration; no comparison harness; reported numbers
  taken at face value.
- **Verdict.** New (governing).
- **Rationale.** Honors "reproduce faithfully, improve transparently" (VISION).
  Turns the four leakage-prone v1 choices into measurements instead of discarded
  alternatives — a stronger research story than either reproducing or replacing
  v1 alone.
- **Recorded alternative.** Replace v1 wholesale (loses comparability) or
  reproduce v1 wholesale (loses honesty). Rejected; dual-arm captures both.

## D-002 — Decision cadence: 15m bar close

- **Date:** 2026-05-22 — **Phase:** B — **Status:** Accepted
- **Decision.** One prediction/label per **15m** bar close. 1m is the inference-
  timing and barrier-resolution substrate; 4h/1h are auxiliary feature inputs,
  not decision clocks.
- **v1 behavior.** Identical — `TargetExtractor3` operates on 15m; production
  fires every minute but only acts on 15m boundaries.
- **Verdict.** Adopt (no change).
- **Rationale.** No methodological problem with v1's cadence; changing it would
  break comparability for no benefit. Cadence sets sample count, label overlap,
  and turnover, so it is fixed deliberately rather than by default.
- **Recorded alternative.** 1m, 1h, or 4h cadence — not pursued in Layer 1.

## D-003 — Vertical barrier: horizon length and no-touch handling

- **Date:** 2026-05-22 — **Phase:** B — **Status:** Accepted
- **Decision.** Horizon `n = 16 × 16 × 2 − 1 = 511` 15m bars (≈ 5.3 days),
  matching v1's `TargetExtractor3`. Three-class label `{-1, 0, +1}`; **no-touch
  within the horizon → `0`**. Add **timeout-rate logging** (fraction labeled `0`
  by horizon expiry) and emit a binary-collapsed view for headline reporting.
  Resolve whether training uses one three-class head or two binary (long/short)
  heads and record it in the model phase.
- **v1 behavior.** Same 511-bar horizon and same `0`-for-no-touch rule; the
  `reversal_detector` returns `(0, 0, …)` on no-touch. v1 never logged the
  timeout rate, and its imbalance weights (`w0`/`w1`) read as binary while the
  labels are three-class — an unresolved ambiguity.
- **Verdict.** Adopt v1 + add diagnostics.
- **Rationale.** Horizon and no-touch semantics are sound and worth preserving
  for comparability; the only gaps are observability (timeout rate) and the
  head ambiguity, both free to fix.
- **Recorded alternative.** Drop no-touch samples, or label them `−1` for a
  strictly binary target — would change the base rate; not used, but noted as a
  sensitivity to revisit if the `0` class dominates.
- **Added detail (2026-05-25).** A *third* no-touch option exists beyond the two
  recorded alternatives: de Prado's `getBins` relabels vertical-barrier touches
  by the **sign of the return at the horizon**, eliminating the `0` class.
  Explicitly **rejected** — it manufactures ±1 labels from non-events (a flat
  drift closing +0.1% becomes a "win"), exactly the optimistic labeling this
  project avoids. The open head-architecture question (three-class vs. binary) is
  resolved by **D-014 (meta-labeling)**: the primary model predicts side and a
  binary meta-model absorbs the `0` class as "don't act."

## D-004 — Embargo and purging

- **Date:** 2026-05-22 — **Phase:** B — **Status:** Accepted
- **Decision.** Purge any training sample whose 511-bar label-outcome window
  overlaps the test fold, and embargo a buffer of **≥ 511 bars** (default =
  full horizon) on the test-adjacent side. Run the honest geometry once with
  embargo = 0 as a **leakage probe** to measure the inflation, then retire it.
- **v1 behavior.** No proper embargo. Only the *feature* window was overlapped
  backward by `n_input_steps − 1 = 20` steps (~3.3 days); the 511-bar (~5.3-day)
  *label* horizon exceeded this, so future outcomes leaked into training labels.
- **Verdict.** Leakage probe (honest primary; v1 no-embargo run once to measure).
- **Rationale.** v1's overlap guards the input sequence, not the label horizon —
  a genuine defect, not a design choice. Embargo ≥ horizon is the standard
  remedy (LdP ch. 7).
- **Recorded alternative.** v1's feature-only overlap (embargo = 0). Retained
  solely as the probe configuration; not a co-equal default.
- **Added detail (2026-05-25).** Purge and embargo remove **two distinct leaks**.
  *Purging* removes training labels whose outcome **window** overlaps the test
  span (an outcome leak). *Embargo* removes a post-test buffer to kill
  **serial-correlation** leakage that purging cannot see — a label whose window
  ends *before* the test block (no overlap, so purge keeps it) can still share
  the boundary's regime/volatility state. Different mechanisms, different fixes;
  any leak surviving a correct purge is embargo's department. Implementation
  (`getTrainTimes`) must handle three overlap cases — train starts within test,
  train ends within test, train envelops test — with a property-based test
  asserting no surviving training window intersects any test span. The embargo
  length is pinned to the **horizon** (511), deliberately stronger than LdP's
  "~1% of observations" heuristic, because the horizon is the true dependence
  timescale here.

## D-005 — Sample-uniqueness weighting

- **Date:** 2026-05-22 — **Phase:** B — **Status:** Accepted
- **Decision.** Keep v1's class-imbalance weights **and** multiply in
  average-uniqueness weights (LdP ch. 4): `weight = class × uniqueness`. Compute
  effective sample size `N_eff` and use it for confidence intervals on test
  metrics (Phase C), not the raw row count.
- **v1 behavior.** `QualifiedWeightedConvCandlesDataset` applied class-imbalance
  weights (`w0 = fraction_negative`, `w1 = fraction_positive`) against the 9.3%
  positive rate — but no uniqueness weighting and no effective-N adjustment.
- **Verdict.** Both (additive).
- **Rationale.** Overlapping labels break i.i.d. in both training and CI width.
  Class weights and uniqueness weights solve different problems and compose
  cleanly; v1's class weights are kept, not discarded.
- **Recorded alternative.** Class weights only (v1) — kept as the inner factor;
  uniqueness layered on top.
- **Added detail (2026-05-25).** Definitions to lock. Concurrency
  `c_t = Σ_i 1[t_{i,0} ≤ t ≤ t_{i,1}]`. Average uniqueness
  `ū_i = (1/|window_i|) · Σ_{t∈window_i} (1/c_t)` — sanity test: `ū_i = 1` when
  all `c_t = 1`; note `|window_i|` is the bar count, **not** a concurrency value.
  Effective sample size via Kish: `N_eff = (Σ w_i)² / Σ w_i²`, used as the
  denominator in every interval (`SE ≈ σ/√N_eff`); expect `N_eff` one-to-two
  orders of magnitude below the raw row count given 511-bar overlap. After
  `class × uniqueness`, **renormalize** weights to sum to `N` (or `N_eff`) so the
  effective learning rate is unchanged — assert in a test. Concurrency and
  uniqueness must be computed on **training-fold labels only** (windows inside
  the fold); computing across the full series leaks test-period overlap structure
  into training weights.

## D-006 — Barrier-touch resolution source

- **Date:** 2026-05-22 — **Phase:** B — **Status:** Accepted
- **Decision.** Resolve TP-vs-SL first-touch on the **1m** series (honest arm).
  Keep v1's **15m-optimistic** resolution as the comparison arm. Report (a) the
  same-bar ambiguity rate and (b) the edge delta between the two arms.
- **v1 behavior.** `reversal_detector` used `idxmax()` on 15m high/low; when both
  barriers fell in one 15m bar it took the optimistic same-bar assumption. 1m
  data existed (DB kickstart) but was not used for resolution.
- **Verdict.** Primary + comparison (honest 1m primary; 15m kept).
- **Rationale.** Same-bar ambiguity on coarse bars is a leading source of
  optimistic bias in triple-barrier backtests, and we already have the 1m data
  (and the 1m `up_first` machinery from pATR). The arm delta is one of the more
  interesting honest findings.
- **Recorded alternative.** 15m-optimistic resolution (v1) — kept as the
  comparison arm, reported, not trusted.
- **Added detail (2026-05-25).** 1m resolution **reduces but does not eliminate**
  same-bar ambiguity: the identical tie-break problem recurs inside any single
  1m bar that straddles both barriers. The residual is ~an order of magnitude
  rarer than at 15m, so the residual bias is small — but log the **1m** same-bar
  ambiguity rate too, so the residual is bounded by measurement rather than
  assumed zero. Formally the label needs `min(τ_u, τ_ℓ)`, which is *unidentified*
  from any bar's OHLC when both barriers fall inside it; finer bars shrink, but
  never fully close, that set of unidentified cases.

## D-007 — Breakeven reference (38.5%, not 50%)

- **Date:** 2026-05-22 — **Phase:** B — **Status:** Accepted
- **Decision.** Record the pre-cost breakeven hit rate
  `2.5 / (4 + 2.5) = 38.5%` as the reference against which every precision-at-
  threshold is judged. Drop implicit use of 50%.
- **v1 behavior.** Multipliers `m_of_target = 4`, `m_of_stop = 2.5` were used,
  but the implied 38.5% breakeven was never written down; 50% was the implicit
  yardstick.
- **Verdict.** Adopt (no real optionality).
- **Rationale.** With a 1.6 : 1 reward:risk, 50% is the wrong bar; a 45%
  precision is already an edge here. Stating the true bar prevents misreading
  results.
- **Recorded alternative.** Implicit 50% (v1) — incorrect; superseded.
- **Added detail (2026-05-25).** The 38.5% bar is the general payoff identity
  `breakeven = ℓ / (u + ℓ)` and is **pre-cost**. Net of fees + slippage the
  *effective* breakeven rises **above** 38.5%, because each trade must also pay
  its costs. The honest comparison is therefore net-precision against the
  cost-adjusted breakeven, not net-precision against 38.5%. Compute the
  cost-adjusted breakeven once the D-011 cost model is fixed and record it
  alongside the pre-cost reference; the success threshold (D-008) judges against
  the cost-adjusted number.
- **Added detail (2026-05-27) — theoretical basis.** The formula
  `ℓ / (u + ℓ)` is the **expected-value breakeven** from basic probability:
  if `p` is the hit rate and `(1−p)` the stop rate, expected P&L per unit =
  `p·u − (1−p)·ℓ = 0` solves to `p = ℓ/(u+ℓ)`. This is also the
  **Kelly fraction denominator** recentred on zero edge — not a heuristic but
  a direct consequence of requiring non-negative expectation. The practical
  implication: a strategy with 45% precision on this payoff already has
  positive expectation pre-cost, yet reads as "below 50%" to naive
  interpretation. Stating the true bar explicitly is not a cosmetic choice;
  it changes whether individual fold results are read as passes or failures.

## D-008 — Success-threshold pre-registration

- **Date:** 2026-05-22 — **Phase:** B — **Status:** Accepted
- **Decision.** Before any model is trained, commit a falsifiable success
  condition to this log: net-of-cost out-of-sample precision above 38.5% with an
  `N_eff`-based CI excluding 38.5%, on at least K of N walk-forward test folds,
  plus Deflated Sharpe > 0 on the aggregated OOS equity curve. Fix K, N, and the
  Sharpe floor at the end of Phase B.
- **v1 behavior.** None — no pre-registered hypothesis; "success" was whatever
  the numbers were, compared loosely to buy-and-hold.
- **Verdict.** New.
- **Rationale.** Pre-registration is the operational form of "honesty over
  results"; it removes the Phase-E temptation to retrofit the bar.
- **Recorded alternative.** Post-hoc judgement (v1) — rejected.
- **Added detail (2026-05-25) — correction to the Sharpe clause.**
  "**Deflated Sharpe > 0**" is **not a meaningful bar**: the DSR is a
  *probability* in `[0, 1]` and is almost always > 0. Replace with
  **DSR > 0.95** (or the chosen confidence). The DSR formula additionally
  requires `N` (number of trials run) and `V` (variance of Sharpe *across*
  trials); a single aggregated walk-forward curve supplies **neither**. Resolve
  the `V` source: either run reduced CPCV (**D-016**) to obtain a path
  distribution, **or** define the trial set explicitly (walk-forward folds + the
  two dual arms + the four baselines) and estimate `V` from it. Logging every
  configuration to MLflow is what supplies `N`. Also reference the breakeven as
  the **cost-adjusted** value (D-007 added detail), not the bare 38.5%. Finalize
  K, N, the DSR confidence, the PBO ceiling (consider adding a `PBO < 0.2`
  clause), and the `V` source before Phase E begins.
- **Added detail (2026-05-27) — pinned values.** The pre-registered condition
  is committed at the close of Phase B with:
  - **N = 8** (walk-forward fold count, D-010 added detail).
  - **K = 5** (60% pass rate). Stricter than majority (4) but tolerates one or
    two regime folds going badly; "all 8" is too brittle given regime variance.
  - **DSR confidence = 0.95** (default).
  - **PBO ceiling = 0.2** (default).
  - **`V` source = trial-set estimator** (option (b) of the prior added detail):
    variance of Sharpe across `folds × dual arms × baselines`, all logged to
    MLflow. Option (a) — reduced CPCV — was rejected as the *primary* `V` source
    because pre-registration must close at the end of Phase B and CPCV depends
    on Phase-E model output; CPCV remains available in Phase C as a secondary
    `V` source if the trial-set estimator turns out to be too narrow.
  Breakeven reference is the **cost-adjusted** value (D-007 added detail), to
  be computed once the D-011 cost model is finalized in Phase C.

## D-009 — Loss function

- **Date:** 2026-05-22 — **Phase:** E (decided in B) — **Status:** Accepted
- **Decision.** Two arms. v1-faithful: combined `0.7·MSE + 0.3·MAE` on a scalar
  output with post-hoc threshold search. Honest: a class-weighted **BCE / focal**
  classifier producing calibrated probabilities; weights = class × uniqueness
  (D-005). Compare both under the harness.
- **v1 behavior.** Combined MSE+MAE primary (`E4_LossFn.ipynb` also tried pure
  MSE); scalar output, threshold searched post-hoc. BCE/focal never used.
- **Verdict.** Both (genuinely co-runnable).
- **Rationale.** A regression loss on a `{-1,0,+1}` target is unusual; focal loss
  is well-motivated at a 9.3% positive rate. But v1's loss is needed for a valid
  v1 comparison, so we run it rather than discard it.
- **Recorded alternative.** MSE+MAE-only (v1) — kept as the comparison arm.

## D-010 — Walk-forward geometry

- **Date:** 2026-05-22 — **Phase:** B — **Status:** Accepted
- **Decision.** Multi-fold walk-forward (expanding, anchored; fold count set so
  each test fold spans months and regimes are represented) is **primary**.
  Reproduce v1's single 75/15/10 chronological split as a one-off comparison
  point only.
- **v1 behavior.** Single chronological split (`training_portion=0.75`,
  `validation_portion=0.4` → 75% train / 15% early-stop "test" / 10% held-out
  "val"); expanding, anchored; no folds.
- **Verdict.** Primary + comparison — **and** the one place v1 conflicts with the
  project's own hard rule ("always walk-forward").
- **Rationale.** A single split makes regime sensitivity invisible and gives one
  noisy OOS estimate. Multi-fold is required by VISION/PLAN's hard rules; keeping
  the single split as primary would void the rigor built in B and C. The honest
  arm therefore wins outright; v1's split survives only as a reported number.
- **Recorded alternative.** v1 single 75/15/10 split — comparison point, not a
  default.
- **Added detail (2026-05-27) — concrete sizing.** The honest-arm geometry is
  pinned with the following defaults in `make_walkforward_folds`:

  | parameter             | value                            |
  |-----------------------|----------------------------------|
  | `n_folds`             | 8                                |
  | initial-train anchor  | ~2 years (~70,000 15m bars)      |
  | `test_fold_bars`      | ~8,640 (≈ 1 calendar quarter)    |
  | `val_fold_bars`       | ~4,032 (≈ 6 weeks)               |
  | `slide_step_bars`     | = `test_fold_bars`               |
  | `embargo_bars`        | 511 each side (D-004)            |

  Total span consumed ≈ 2y anchor + 8 × (val + test) + embargos ≈ 6 years on
  the ~8.75-year common span; ~2.75 y headroom rolls into the expanding-train
  tail. Each major regime (2017/2021 bull, 2018/2022 bear, 2023–25 recovery,
  2025 pullback) lands in at least one test fold. These sizes flow into
  D-008's K-of-N (K = 5, N = 8).

## D-011 — Cost model

- **Date:** 2026-05-22 — **Phase:** C — **Status:** Accepted
- **Decision.** Add a cost model: taker fee + slippage cushion sized to sub-1m
  touch ambiguity. Report **gross** P&L (lines up with v1) **and** net P&L (the
  honest number). Fills at the barrier price on 1m touch (consistent with D-006).
- **v1 behavior.** None. All P&L gross; `StrategyTester._close_current_position`
  computes `100*(price-entry)/entry` with no fee/slippage; entry at bar close.
- **Verdict.** Both (gross retained as the v1-faithful arm; net is primary).
- **Rationale.** Gross-only is an omission, not a decision. A path-dependent
  signal at 15m cadence can churn enough that costs decide profitability, so net
  is the only honest headline.
- **Recorded alternative.** Gross-only, entry-at-close (v1) — kept as the gross
  arm for comparability.

## D-012 — pATR definition lock

- **Date:** 2026-05-22 — **Phase:** B — **Status:** Accepted
- **Decision.** Adopt v1's proportional ATR exactly: Wilder smoothing, window 10,
  directional true range via the `up_first` flag derived from 1m sub-candles;
  `p_atr[i] = (p_atr[i-1]·(window-1) + p_true_range[i]) / window`. Keep the
  `shift(3)` lag on higher-timeframe pATR. Lock the formula; no changes.
- **v1 behavior.** Identical (this is v1's design).
- **Verdict.** Adopt (no change).
- **Rationale.** Well-constructed and already leakage-aware (completed bars only;
  `shift(3)` prevents current-bar bleed). It is also the same 1m machinery D-006
  relies on. No reason to alter it.
- **Recorded alternative.** A standard (non-directional) ATR — would break
  comparability and discard a sound design; not used.
- **Added detail (2026-05-25) — estimator-faithfulness footnote.** For the
  record: López de Prado's reference sets the volatility target `trgt` to an
  **EWMA standard deviation of close-to-close returns**, not to ATR. ATR is built
  from the high / low / previous-close true range and is a different (though
  closely related) estimator. We deliberately **retain** v1's pATR for
  faithfulness; the EWMA-of-returns alternative is noted and **not adopted**. No
  methodology conflict — only an explicit acknowledgment that `trgt ≡ pATR` is a
  chosen estimator, not the book's default. (For reference, the true-range term
  is `TR_t = max[H_t − L_t, |H_t − C_{t-1}|, |L_t − C_{t-1}|]`, with the gap
  terms capturing between-bar jumps.)
- **Added detail (2026-05-27) — sources and extensions.**
  ATR originates in J. Welles Wilder, *New Concepts in Technical Trading
  Systems* (1978). The Wilder smoothing recurrence is:
  `pATR[i] = (pATR[i−1] × (n−1) + pTR[i]) / n` with `n = 10`.
  This is an exponential moving average with decay `α = 1/n`, identical to
  `EMA(pTR, 2n−1)` in the standard `2/(span+1)` convention — the two forms
  produce the same series.
  v1 extends standard ATR in one deliberate way: the **`up_first` flag**,
  derived from 1m sub-candles, makes the true range *directional*. A standard
  ATR treats `|H−C_prev|` and `|L−C_prev|` symmetrically; the `up_first`
  flag records whether the bar's net move was upward or downward, and the
  barrier-resolution machinery uses this to determine which gap term is
  "active." This is a v1 design choice, not standard Wilder ATR, and it feeds
  directly into the 1m first-touch ordering used by D-006.

## D-013 — Feature-selection scope

- **Date:** 2026-05-22 — **Phase:** D — **Status:** Accepted
- **Decision.** Keep v1's *method* (Pearson filter at 0.95 + mutual-information
  ranking) but change the *scope*: rerun **per fold on training rows only**
  (honest arm). Run v1's single global selection (90% of data) once as a
  **selection-leakage probe**, then retire it.
- **v1 behavior.** `FeatureEngineer2` ran selection once on
  `iloc[0:0.9·N]` — a global, leakage-prone fit; the feature set was fixed across
  the whole dataset rather than re-derived inside each training fold.
- **Verdict.** Leakage probe — **and** a place v1 conflicts with PLAN's own rule
  ("rerun honestly per fold, not globally").
- **Rationale.** Selecting features on data that includes future folds leaks. The
  method is fine; only the scope is wrong. Per-fold selection is required by the
  hard rules; global selection survives only to measure the leak.
- **Recorded alternative.** v1 global selection on 90% of data — probe only.

## D-014 — Meta-labeling (side / size decomposition)

- **Date:** 2026-05-25 — **Phase:** E (decided in B) — **Status:** Proposed
  (ratify Layer-1 vs Layer-2 placement before Phase E)
- **Decision.** Model the target as **side then size**. The primary model
  (`ConvWideDeepLSTMNet`) predicts direction; a separate **binary meta-model**,
  trained only on bars where the primary takes a position (`ŝ_t ≠ 0`), predicts
  `m_t = 1[ŝ_t = y_t]` (was the primary's call correct) and outputs a calibrated
  probability used to **filter and size** the bet. Act iff `p̂(m=1) > breakeven`
  (D-007, cost-adjusted), and size by conviction above breakeven. This absorbs
  the no-touch (`0`) class as "primary wrong → don't act," resolving the open
  head-architecture question in D-003. Primary model tuned for **high recall**;
  meta-model supplies **precision**.
- **v1 behavior.** None — v1 used a single model/head for direction with no
  separate act/size stage; the scalar output was thresholded post-hoc (D-009).
- **Verdict.** New (honest-arm layer; v1 single-stage retained as comparison via
  D-009).
- **Rationale.** With a ~76% majority `0` class, a single multiclass head spends
  capacity on non-events. Decoupling lets the primary lock recall while the
  meta-model raises precision *without* re-introducing false negatives among
  caught signals — dominating a single model on F1 at the same recall. The action
  threshold becomes **derived** (breakeven) rather than searched. Sizing uses
  de Prado's probability→size map, **recentred on the breakeven** (≈0.385) rather
  than 0.5 — the symmetric-payoff centring is wrong for a 4 : 2.5 payoff and
  would contradict the economic decision near `p = 0.45`.
- **Recorded alternative.** Single-stage three-class / scalar head (v1, D-009) —
  kept as comparison arm. If meta-labeling is deferred to Layer 2, fall back to
  the directional collapse with `0` folded into "no-trade," and revisit.
- **Added detail (2026-05-27) — v1 already implemented this implicitly.**
  Analysis of v1's `TargetExtractor` family reveals that `target2=True` is an
  **embedded, rule-based meta-labeling** step baked into the labeler itself:
  - `rt3` = the *raw first crossing* = **primary label / side**.
    Records which barrier was touched first regardless of confidence.
  - `target3` = the *filtered label* = **meta-label**.
    When `stop2` (the slack-expanded stop) is touched *before* the profit
    target, `target3` is set to `0` — "ambiguous; don't act." When the profit
    target is touched cleanly, `target3 = rt3`.
  - `stop2` = `(1 − (m_stop + slack) × pATR) × price` is the **ambiguity
    threshold**: if price gets this close to the stop, the trade is downgraded
    from a signal to a non-event in the meta-label.
  The two outputs (`rt3`, `target3`) therefore form exactly the (side, meta)
  label pair that the v2 two-stage model consumes. The v1 labeler hard-coded
  the meta-label rule; v2 (D-014) learns it from data. The v1-faithful arm
  in Phase B must reproduce **both outputs**, not just `target3`; see PHASE_B.md
  B.1 for the updated `make_labels` signature.

## D-015 — Labeling event filter (sampling cadence)

- **Date:** 2026-05-25 — **Phase:** B — **Status:** Rejected for Layer 1
  (revisit in Layer 2)
- **Decision.** Honest arm samples decision points with a **symmetric CUSUM
  filter** on de-meaned 15m returns: `S⁺_t = max(0, S⁺_{t-1} + r_t − E[r_t])`,
  `S⁻_t = min(0, S⁻_{t-1} + r_t − E[r_t])`, emit a labeling event (and reset)
  when `S⁺_t ≥ κ` or `S⁻_t ≤ −κ`. v1-faithful arm: the fixed
  one-label-per-15m-close cadence (D-002). This layers *on top of* D-002 — D-002
  fixes the clock; D-015 chooses which ticks become labeled events.
- **v1 behavior.** None — v1 labels every 15m bar (D-002); no activity-based
  event sampling.
- **Verdict.** New (fork; high value — alters class balance and `N_eff`).
- **Rationale.** Clock sampling labels dead, sideways bars that inflate the `0`
  class and worsen overlap (lowering `N_eff`). CUSUM samples more in
  trending/volatile regimes and less when price drifts, preferentially dropping
  likely-timeout bars. Measure in B.2: timeout fraction, ±1 share, average
  uniqueness / `N_eff` per fold span; the arm-to-arm class-balance shift is itself
  a finding. Recommend a **pATR-scaled `κ`** so the trigger breathes with
  volatility (D-012 units). The filter uses past returns only — no look-ahead.
- **Recorded alternative.** Fixed 15m-close cadence (v1, D-002) — the comparison
  arm and the default if CUSUM is descoped from Layer 1.
- **Added detail (2026-05-27) — descoped.** CUSUM event sampling is **out of
  scope for Layer 1**. Honest-arm cadence stays at every 15m close (D-002).
  Rationale: B.2 already produces the diagnostics (timeout fraction, average
  uniqueness / `N_eff`) that would motivate CUSUM; if those numbers reveal the
  fixed-clock cadence is hurting more than helping, the filter can be added in
  Layer 2 as an honest-arm refinement without disturbing the Phase-B label /
  split / weight contracts. Pinning `κ` and re-measuring is also itself a
  multi-day investigation; deferring it keeps Layer 1 focused.

## D-016 — Backtest geometry: walk-forward vs. CPCV

- **Date:** 2026-05-25 — **Phase:** C (decided in B) — **Status:** Proposed
  (compute-gated)
- **Decision.** Primary backtester = single-path purged + embargoed
  **walk-forward** (D-010). Run **Combinatorial Purged CV (CPCV)** in a *reduced*
  configuration — on the four baselines and a reduced-epoch model — to obtain the
  distribution of out-of-sample Sharpe across `φ = C(N−1, k−1)` paths, supplying
  the across-trial variance `V` the Deflated Sharpe needs (D-008). The headline
  deep model reports its walk-forward point.
- **v1 behavior.** None — single chronological split, single Sharpe (subsumed by
  D-010's comparison arm); no path distribution.
- **Verdict.** New (fork; compute-gated).
- **Rationale.** One walk-forward run = one equity curve = one Sharpe = a size-1
  sample; it yields neither an honest CI nor the across-trial `V` in the DSR
  formula. CPCV with `N` groups and `k` held out gives many full-length OOS paths
  and thus a Sharpe distribution. Full CPCV on the deep model costs
  `C(N,k)/k ×` the training budget (likely prohibitive), so cheap models
  characterize `V` while the expensive model reports a walk-forward point.
  Directly enables the D-008 tightening (DSR > 0.95).
- **Recorded alternative.** Walk-forward only, no CPCV — acceptable **iff** `V`
  is instead estimated from folds + the two dual arms + the four baselines treated
  as the trial set; record the chosen `V` source in D-008.
- **Added detail (2026-05-27) — scheme value reserved in Phase B.** The
  `scheme="cpcv"` value is **reserved in `make_walkforward_folds`** at Phase B
  to keep the API stable; the implementation lands in Phase C and is
  compute-gated. D-008's pinned values (added detail 2026-05-27) take
  trial-set estimation as the **primary** `V` source; reduced CPCV is the
  **secondary** option, run only if the trial-set estimator is too narrow.

## D-017 — Time-decay on sample weights

- **Date:** 2026-05-25 — **Phase:** B — **Status:** Accepted (resolved to "off")
- **Decision.** **No time decay** in Layer 1. Final weight = `class × uniqueness`
  (D-005) with de Prado's piecewise-linear decay on cumulative uniqueness disabled
  (`c = 1`).
- **v1 behavior.** No time decay either — so there is no faithfulness conflict;
  this entry documents that the honest arm *also* declines it, by reasoned choice
  rather than oversight.
- **Verdict.** New (an explicit decision to do less).
- **Rationale.** Decay down-weights older observations to address
  non-stationarity, but (a) walk-forward retraining already adapts to regime drift
  per fold, and (b) `N_eff` is already small from 511-bar overlap — decay would
  shrink it further and widen every CI for marginal regime-adaptation gain. The
  cost/benefit favors preserving `N_eff`.
- **Recorded alternative.** Mild decay `c ∈ [0.5, 1)` — revisit only if B.2's
  per-quarter class distribution shows regime drift the walk-forward folds do not
  absorb.

## D-018 — Grid containment check: modulo arithmetic over presence-based anti-join

- **Date:** 2026-05-26 — **Phase:** A — **Status:** Accepted
- **Decision.** `check_cross_timeframe_alignment` determines whether a
  coarser-tf `open_time` is "on the 1m grid" via a **modulo check**:
  `open_time_us % 60_000_000 == 0` (i.e., the timestamp is an exact
  whole-minute boundary from the UTC epoch). The initial implementation used
  an **anti-join** against the 1m series instead.
- **v1 behavior.** No cross-timeframe alignment check existed.
- **Verdict.** Adopt modulo (corrects the anti-join).
- **Rationale.** An anti-join conflates two structurally different problems:
  (a) a coarser-tf bar whose timestamp is not at a minute boundary — a genuine
  grid defect — and (b) a coarser-tf bar at a clean minute boundary that
  simply has no matching 1m row because the 1m series has a coverage gap at
  that moment. Conflating them produces misleading counts and wrong attribution:
  in practice the anti-join reported 1,366 15m "failures" when only 81 were
  genuine (the rest were 1m coverage gaps already caught by `check_integrity`).
  Modulo isolates (a) cleanly; (b) is already covered by gap detection.
- **Recorded alternative.** Presence-based anti-join against the 1m series —
  conflates timestamp defects with 1m coverage gaps; rejected.

## D-019 — CHECKSUM verification: soft on missing files

- **Date:** 2026-05-26 — **Phase:** A — **Status:** Accepted
- **Decision.** When fetching a Binance Vision ZIP, attempt to retrieve the
  co-located `.CHECKSUM` file. If the file is **absent** (HTTP 404 or any
  fetch error), log a warning and proceed. If the file **is present**, verify
  the SHA-256 and **hard-fail** on mismatch. Log every verified hash to
  `data/raw/checksums.jsonl`; log nothing when no checksum was available.
- **v1 behavior.** No checksum verification of any kind.
- **Verdict.** New.
- **Rationale.** Binance Vision does not consistently provide `.CHECKSUM`
  files for older archives — hard-requiring them would block most historical
  back-fills. The protection is asymmetric and honest: a present checksum is
  always enforced (strong guard); a missing checksum is an absence of
  guarantee, not evidence of corruption. The audit log is only written when a
  checksum was actually verified, so it never overstates coverage.
- **Recorded alternative.** Always require a checksum — blocks historical
  downloads for the majority of the dataset; rejected.

## D-020 — ccxt tail bars: zero-fill missing ancillary columns

- **Date:** 2026-05-26 — **Phase:** A — **Status:** Accepted
- **Decision.** When the tail is filled via ccxt (`_fetch_ccxt_ohlcv`), set
  `number_of_trades`, `taker_buy_base_volume`, and `taker_buy_quote_volume`
  to **`0`** (integer / float zero) rather than `NaN` / `null`.
- **v1 behavior.** These columns were not part of v1's schema; the question
  did not arise.
- **Verdict.** New.
- **Rationale.** The ccxt `fetch_ohlcv` response carries only five OHLCV
  columns; the three ancillary fields are unavailable. Zero is preferred over
  NaN because (a) the canonical `OHLCV_SCHEMA` types are non-nullable
  (`Int64` / `Float64`), making NaN harder to propagate cleanly, and (b) a
  structural zero is **explicitly detectable** in Phase D feature engineering
  (`col > 0` guard or a `has_ancillary` boolean flag), whereas NaN can
  silently propagate through indicator calculations producing harder-to-trace
  artifacts. The consequence — a small number of recent tail bars carry
  meaningless zeros in these three columns — is documented in L-003 and must
  be guarded in Phase D.
- **Recorded alternative.** NaN / null fill — propagates unpredictably
  through floating-point indicator math; rejected in favour of an explicit
  zero that can be detected and filtered deterministically.

## D-021 — OHLCV schema: 9 columns

- **Date:** 2026-05-26 — **Phase:** A — **Status:** Accepted
- **Decision.** The canonical `OHLCV_SCHEMA` keeps **9 of the 12 columns**
  from a Binance Vision klines CSV:
  `open_time, open, high, low, close, volume, close_time, number_of_trades,
  taker_buy_base_volume, taker_buy_quote_volume`.
  Dropped: `quote_asset_volume` (col 7), `taker_buy_base_asset_volume` alias
  (col 9, renamed on ingest), and `ignore` (col 11).
- **v1 behavior.** v1 kept 6 columns (OHLCV + open_time); the three
  ancillary columns were absent from its schema.
- **Verdict.** New (richer schema).
- **Rationale.** `close_time` pins the bar's exact close boundary, needed
  for Phase B barrier resolution. `number_of_trades` and the taker-buy pair
  encode order-flow composition (aggressor-side volume fraction) that may
  contribute features in Phase D. `quote_asset_volume` is dropped because it
  is reconstructible as `close × volume` and adds no information; `ignore` is
  a Binance placeholder with no defined semantics.
- **Recorded alternative.** 6-column OHLCV-only (v1) — loses order-flow
  signal and the close-time boundary pin; retained as a comparison point for
  feature-ablation only.

## D-022 — Integrity check severity taxonomy: physically-impossible = hard, market-real = soft

- **Date:** 2026-05-26 — **Phase:** A — **Status:** Accepted
- **Decision.** The governing rule for `check_integrity` severity
  classification:
  - **Hard failure** — condition is *physically impossible* or indicates
    source corruption / parse error. Flips `passed = False`. Downstream code
    may not safely use data that triggered a hard failure.
    *Checks:* duplicate `open_time`s, non-monotonic timestamps, NaN/null in
    any OHLC column, OHLC arithmetic violation (`high < max(O, C)` or
    `low > min(O, C)`), close price outside sanity bounds, negative volume,
    `open_time` not UTC-aware.
  - **Soft observation** — condition is anomalous but *can occur in real
    market data*. Counted and surfaced in the report; `passed` unaffected.
    *Checks:* gaps > 1 interval, zero-volume bars, OHLC-equal bars
    (O=H=L=C), NaN in ancillary columns.
- **v1 behavior.** No integrity layer; data was used as-is.
- **Verdict.** New (governing).
- **Rationale.** Hard failures indicate the data source cannot be trusted
  and must be investigated before any analysis. Soft observations are real
  market events — exchange maintenance windows create genuine gaps; thin
  early markets produce genuine zero-volume minutes — and silently filtering
  them would distort analysis. The separation makes the contract explicit:
  a `passed = True` report is a meaningful guarantee, not a vacuous one.
- **Recorded alternative.** Treat every anomaly as a hard failure — would
  reject real-but-anomalous data (e.g., a single maintenance gap) and make
  the dataset effectively unusable; rejected.

## D-023 — Price sanity bounds: close ∈ [100, 1 000 000] for BTC/USDT

- **Date:** 2026-05-26 — **Phase:** A — **Status:** Accepted
- **Decision.** Flag `close < 100` or `close > 1_000_000` as a **hard
  integrity failure**.
- **v1 behavior.** No price-range check.
- **Verdict.** New.
- **Rationale.** BTC/USDT has ranged from ~$3,200 (2018–2019 bear lows) to
  ~$126,000 (2025 high observed in the dataset). The bounds $100 and
  $1,000,000 span this range with wide margin on both sides, catching unit
  errors (e.g., price expressed in cents: a $30,000 BTC price would appear
  as $300, below $3,200 but above $100 — caught) and source corruption, with
  no realistic risk of a false positive at any foreseeable BTC price. The
  range is deliberately asymmetric: the lower bound is more important because
  unit confusion and parse errors almost always produce anomalously small
  values.
- **Recorded alternative.** No bounds check (v1) — silently accepts
  corrupted or unit-confused prices; rejected. Tighter upper bound (e.g.,
  $500,000) — introduces false-positive risk during price discovery at new
  ATHs; rejected.

## D-024 — Gap handling: soft observation, never forward-fill

- **Date:** 2026-05-26 — **Phase:** A — **Status:** Accepted
- **Decision.** Gaps (missing bars where the expected bar is absent) are
  recorded in `IntegrityReport.gaps` as soft observations and the DataFrame
  is returned unmodified. Forward-filling, interpolation, or any other
  synthetic bar insertion is explicitly rejected at the data layer.
- **v1 behavior.** v1 did not have an integrity layer; gap handling was
  implicit and unspecified.
- **Verdict.** New.
- **Rationale.** Gaps represent real market events — scheduled exchange
  maintenance, unscheduled outages, circuit breakers. A manufactured
  forward-filled bar has stale prices (wrong), volume = 0 (wrong), and a
  close_time that was never a real trading period. Any downstream phase that
  must handle a gap (Phase B barrier resolution skips to the next real bar;
  Phase D feature windows may need to flag the disruption) should do so
  explicitly and locally, with full knowledge that a gap occurred. Silently
  patching the data layer removes that knowledge.
- **Recorded alternative.** Forward-fill with previous bar's close — creates
  fictitious bars that distort volume-based features, OHLC arithmetic, and
  any volatility estimator; rejected.

## D-025 — Cross-timeframe alignment check severity: grid containment HARD, spacing and coverage SOFT

- **Date:** 2026-05-26 — **Phase:** A — **Status:** Accepted
- **Decision.** The three sub-checks inside `check_cross_timeframe_alignment`
  have different severity:
  - **Grid containment** (coarser-tf `open_time` not at a whole-minute
    boundary): **HARD FAILURE**. Recorded per-timeframe in `misaligned_opens`.
  - **Nominal spacing violations** (spacing between consecutive bars ≠
    nominal interval): **SOFT**. Recorded in `spacing_violations`; these are
    the same events as per-timeframe gaps viewed from a different direction.
  - **Coverage overlap** (date-range mismatch between timeframes): **SOFT,
    informational**. Recorded as a human note in `coverage_mismatch`.
- **v1 behavior.** No cross-timeframe alignment check existed.
- **Verdict.** New.
- **Rationale.** An off-grid coarser-tf timestamp is an unrecoverable
  structural defect: Phase D's backward as-of joins and Phase B's 1m
  barrier-resolution scans both assume that a 15m/1h/4h bar's `open_time`
  is exactly a minute boundary that can be located in the 1m grid. A
  fractional-second offset silently causes a one-bar anchor error with no
  runtime signal. Spacing violations and coverage mismatches are real but
  survivable — gaps are already handled by `check_integrity`, and downstream
  phases operate only on the common coverage span anyway.
- **Recorded alternative.** All three checks as hard failures — would
  hard-fail on the known Binance early-data timestamp anomaly (L-001)
  without delivering additional protection, since the anomaly is fully
  characterised and its downstream impact is bounded; rejected.

## D-026 — Multi-timeframe pATR: longer-horizon ATR for target, shorter for stop

- **Date:** 2026-05-27 — **Phase:** B (applies to TargetExtractors 2–4 in v1;
  governs Phase B barrier construction in v2) — **Status:** Accepted (adopt v1)
- **Decision.** When multiple pATR timeframes are available (15m / 60m / 240m,
  or 5m / 15m / 60m / 240m), use a **longer-horizon pATR for the profit target**
  and a **shorter-horizon pATR for the stop**. For example, TargetExtractor3
  defaults to `target_patr = patr_240`, `stop_patr = patr_60`. The two can be
  configured independently; the asymmetry is deliberate.
- **v1 behavior.** TargetExtractor (single-timeframe) used native pATR for both.
  TargetExtractors 2–4 introduced the MTF split, with `patr_240` for targets
  and `patr_60` (plus `stop2` slack) for stops as the primary configuration.
- **Verdict.** Adopt (no change from v1).
- **Rationale.** The choice is an application of **volatility term structure**
  reasoning to barrier design:
  - A *longer-horizon ATR* (`patr_240`, 4h smoothing) is slower-moving and
    wider. It gives the trade room to breathe through normal short-term noise
    before declaring a win — the profit target only fires on a move that is
    large relative to the medium-term regime, not a transient spike.
  - A *shorter-horizon ATR* (`patr_60`, 1h smoothing) is more reactive. If
    recent volatility rises, the stop tightens quickly, cutting losses before
    the regime worsens further. If volatility falls, the stop gives more room
    to avoid being picked off by microstructure noise.
  Using a single pATR for both barriers creates a mismatch: a wide
  (long-vol) stop pairs with a wide target, leading to many timeout labels in
  calm regimes; a tight (short-vol) target fires too easily in volatile
  regimes on moves that are not really "wins." The MTF split prevents both
  failure modes and reduces the timeout (`0`) class relative to a
  single-timeframe baseline.
- **Recorded alternative.** Single-timeframe pATR for both barriers (v1's
  TargetExtractor1 configuration) — kept as the single-timeframe comparison;
  not the default for multi-timeframe runs.

## D-027 — Entry-price convention: close of the 15m bar at `t`

- **Date:** 2026-05-27 — **Phase:** B — **Status:** Accepted
- **Decision.** The barriers at decision time `t` are anchored on
  `entry_price = df15["close"][t]`. The 1m forward walk scans strictly
  **after** `df15["close_time"][t]`, so no 1m bar that falls inside the entry
  15m bar contributes to the label.
- **v1 behavior.** Identical — v1's `StrategyTester` enters at the 15m bar
  close (`_close_current_position` and the entry-fill logic are anchored on
  close), and `TargetExtractor` constructs barriers from that close as the
  reference price.
- **Verdict.** Adopt (no change from v1).
- **Rationale.** The 15m close is the first price observable at the decision
  boundary; using it preserves comparability with v1 and matches the cadence
  fixed in D-002. Anchoring on `next_open` would introduce a one-bar
  conservatism that is not in the v1 reference and would require its own
  honest-arm justification.
- **Recorded alternative.** Anchor on the open of the **next** 15m bar at
  `t+1` (no current-bar bleed in the price either) — rejected for Layer 1 as
  unnecessary; revisit only if leakage analysis finds the close anchor lets a
  feature-side leak survive.

## D-028 — 1m intra-bar tie-break (honest arm)

- **Date:** 2026-05-27 — **Phase:** B — **Status:** Accepted
- **Decision.** When a single 1m bar's high–low range contains *both*
  barriers, the honest arm resolves the order of first touch deterministically
  using the bar's net direction:
  - `close > open` → assume the **high was touched first**.
  - `close ≤ open` → assume the **low was touched first**.
  Bars where this tie-break fires are flagged `ambig_1m = True` in
  `LabelResult`; the rate is logged per fold (D-006 added detail).
- **v1 behavior.** v1 resolved barrier order on 15m bars with an unconditional
  optimistic same-bar assumption (favorable barrier wins). v1 did not address
  the 1m residual at all because it did not resolve on 1m.
- **Verdict.** New (honest arm only; the v1-faithful arm keeps the 15m
  optimistic rule per D-006).
- **Rationale.** Inside a 1m bar that straddles both barriers, first-touch
  order is unidentified from OHLC (D-006 added detail). The close-vs-open
  rule mirrors the dominant intra-bar direction without re-using the
  `up_first` flag (which is a feature signal computed from a different
  aggregation for pATR — coupling the labeler to it would be a subtle
  cross-contamination). The residual ambiguity rate at the 1m grain bounds
  the irreducible bias of the honest arm and is logged in B.2.
- **Recorded alternative.**
  - Always-pessimistic (stop wins) — eliminates upward bias but creates a
    symmetric downward one; rejected.
  - Reuse `up_first` — couples the labeler to a feature signal; rejected.
  - Random tie-break — defensible but non-deterministic and harder to test;
    rejected.

## D-029 — `LabelResult` schema and tail-sentinel dtype

- **Date:** 2026-05-27 — **Phase:** B — **Status:** Accepted
- **Decision.** `make_labels` returns a single Polars `DataFrame` aligned to
  the 15m decision clock — one row per 15m bar in `df15`, never reindexed or
  filtered by the labeler. Columns (full list in PHASE_B.md B.1):
  `open_time, rt3, target3, first_touch_idx_1m, entry_price, profit_level,
  stop_level, stop2_level, ambig_15m, ambig_1m, is_complete`.
  - `rt3` and `target3` are `Int8` nullable; tail rows whose horizon window
    is incomplete carry `null` in both label columns plus
    `is_complete = False`.
  - Scalar per-arm diagnostics (ambiguity rates, no-touch fraction) live in
    `LabelResult.attrs` (a dict alongside the DataFrame), read by B.2.
- **v1 behavior.** v1's `TargetExtractor` returned a NumPy/Pandas vector of
  labels with `fillna(33)` on the tail — a magic number collapsed into the
  negative class downstream, fabricating an observable label where none
  existed.
- **Verdict.** New (preserves the labeler's clock-aligned index; replaces
  v1's magic-number tail with a typed null + explicit `is_complete` flag).
- **Rationale.** A single Polars DataFrame on the 15m clock makes downstream
  joins (features in Phase D, splits in B.3) trivial and unambiguous.
  Sentinelling instead of dropping preserves the index alignment that every
  consumer relies on. Typed null is the cleanest representation of an
  *unobservable* label — collapsing into a class fabricates information.
- **Recorded alternative.**
  - Pydantic/dataclass with separate Series + scalar diagnostics — rejected
    because the DataFrame is the natural artifact for every downstream
    consumer.
  - Drop tail rows in `make_labels` — rejected; destroys index alignment.
  - Boolean `is_labelable` column with arbitrary values in `rt3`/`target3`
    for unlabeled rows — rejected; `rt3.is_null()` already conveys
    unlabelability and a typed null is harder to misuse than a sentinel
    integer.

## D-030 — Phase-B module layout

- **Date:** 2026-05-27 — **Phase:** B — **Status:** Accepted
- **Decision.** Phase B introduces modules under three packages:
  - `src/assareh/features/patr.py` — multi-timeframe pATR (D-031)
  - `src/assareh/labels/targets.py` — `make_labels`, `LabelResult`
  - `src/assareh/labels/diagnostics.py` — `target_stats` helper (B.2)
  - `src/assareh/splits/splits.py` — `Fold`, `make_walkforward_folds`
  - `src/assareh/splits/weights.py` — `average_uniqueness`, Kish `N_eff`,
    renormalization
- **v1 behavior.** v1 mixed labeling, indicators, and split logic across
  ad-hoc modules; no package-level discipline.
- **Verdict.** New.
- **Rationale.** Pinning the layout at the start of Phase B prevents the
  drift of "label code in a feature module" and gives Phase C / Phase D
  unambiguous import paths. `labels/` and `splits/` are separate packages
  because Phase C's harness should be able to import either without pulling
  the other.
- **Recorded alternative.** Flat `src/assareh/targets.py` and
  `src/assareh/splits.py` — rejected; the diagnostic helper and the weights
  module each need a sibling and a flat layout makes that uglier than the
  package layout.

## D-031 — pATR module location

- **Date:** 2026-05-27 — **Phase:** B — **Status:** Accepted
- **Decision.** Multi-timeframe pATR lives at `src/assareh/features/patr.py`
  and exposes `attach_patr(df15, df1m, *, window=10,
  timeframes_minutes=(15, 60, 240)) -> pl.DataFrame` returning `df15` with
  `patr_<tf>` columns attached.
- **v1 behavior.** v1's pATR computation was embedded in the indicator
  engineer alongside other features; the labeler reached into the feature
  module to retrieve it.
- **Verdict.** New (cleaner separation).
- **Rationale.** pATR is a *derived feature* on OHLCV and has at least two
  consumers — the Phase-B labeler and Phase-D feature engineering. Placing
  it under `features/` makes Phase D's import natural and keeps `labels/`
  free of feature-extraction code. Built in Phase B as a B.0 prerequisite.
- **Recorded alternative.** Put pATR under `src/assareh/labels/patr.py`
  because the only Phase-B consumer is the labeler — rejected; forces Phase
  D to import from `labels/`, which is wrong-shaped.

## D-032 — `label_spans` representation

- **Date:** 2026-05-27 — **Phase:** B — **Status:** Accepted
- **Decision.** Label outcome spans are passed to `average_uniqueness` as an
  `np.ndarray` of shape `(n, 2)` with `int64` dtype; columns are
  `(start_idx, end_idx_exclusive)` into the 15m decision clock.
- **v1 behavior.** v1 never computed average uniqueness; the question did
  not arise.
- **Verdict.** New.
- **Rationale.** Uniqueness computation is a numerical kernel
  (concurrency vectors, cumulative sums) on `~10⁵` rows. A contiguous
  ndarray is the natural representation across the numpy boundary
  (vectorized arithmetic, `np.bincount` for concurrency, `np.cumsum` for
  uniqueness windows). `list[tuple[int, int]]` would force Python-level
  iteration and Polars `Series` add no benefit at the numpy boundary.
- **Recorded alternative.** `list[tuple[int, int]]` — rejected (slow);
  `pl.Series` pair — rejected (no benefit at the kernel boundary).

## D-033 — Forward-walk vectorization strategy

- **Date:** 2026-05-27 — **Phase:** B — **Status:** Accepted
- **Decision.** The 1m forward walk in `make_labels` (honest arm) is
  implemented in **Polars**, lazy until the final `.collect()`:
  1. Build per-decision boolean masks on `df1m` for `hit_target`,
     `hit_stop`, `hit_stop2` using broadcast comparisons against the per-
     decision barrier levels.
  2. Use a Polars window-join (`join_asof` with a range filter
     `1m.open_time ∈ (15m.close_time[t], 15m.close_time[t] + horizon)`) to
     find the first 1m bar in each decision's horizon where any hit fires.
  3. Apply the D-028 tie-break on rows flagged `ambig_1m`.
  The whole pipeline stays lazy; no Python loop over decision points.
- **v1 behavior.** v1's `reversal_detector` looped over decision points
  with `idxmax()` on 15m high/low; it never touched 1m for resolution and
  so the question of efficient 1m vectorization did not arise.
- **Verdict.** New.
- **Rationale.** Naive iteration is ~306K decisions × ~7.7K 1m bars each ≈
  2.3B 1m lookups — unacceptably slow. Polars window-joins evaluate the
  same logic in vectorized form on contiguous arrays. Adding a numba /
  cython kernel would deliver more speed at the cost of a build
  dependency and a second code path that needs to stay in sync with the
  Polars one; deferred until profiling proves the Polars path inadequate.
- **Recorded alternative.**
  - Numba / cython kernel — rejected for Layer 1 (build complexity).
  - Naive Python loop — rejected (too slow on the real dataset).
  - Pandas + `numpy` broadcasting — would work but contradicts the
    CLAUDE.md Polars convention; rejected.
