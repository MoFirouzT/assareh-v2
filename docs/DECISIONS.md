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
