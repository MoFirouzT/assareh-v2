# DECISIONS

This file is the living record of the project's design decisions. Entries are
normally added as decisions are made, but may be revised or removed as the
project evolves — prefer marking an entry `Superseded` with a pointer when the
history matters, but outright deletion is allowed.

**Status taxonomy:** `Accepted` · `Proposed` · `Rejected` · `Superseded`.
Qualifiers (e.g. "compute-gated", "governing", "this iteration only") live in the
first line of the decision body, not in the status field.

## Index

| ID    | Title                                                                 | Phase | Status   |
|-------|-----------------------------------------------------------------------|-------|----------|
| D-001 | Dual-arm methodology (governing rule)                                 | B→F   | Accepted |
| D-002 | Decision cadence: 15m bar close                                       | B     | Accepted |
| D-003 | Vertical barrier: horizon length and no-touch handling                | B     | Accepted |
| D-004 | Embargo and purging                                                   | B     | Accepted |
| D-005 | Sample-uniqueness weighting                                           | B     | Accepted |
| D-006 | Barrier-touch resolution source                                       | B     | Accepted |
| D-007 | Breakeven reference (38.5%, not 50%)                                  | B     | Accepted |
| D-008 | Success-threshold pre-registration                                    | B     | Accepted |
| D-009 | Loss function                                                         | E     | Accepted |
| D-010 | Walk-forward geometry                                                 | B     | Accepted |
| D-011 | Cost model                                                            | C     | Accepted |
| D-012 | pATR definition lock                                                  | B     | Accepted |
| D-013 | Feature-selection scope                                               | D     | Accepted |
| D-014 | Meta-labeling (side / size decomposition)                             | E     | Proposed |
| D-015 | Labeling event filter (sampling cadence)                              | B     | Rejected |
| D-016 | Backtest geometry: walk-forward vs. CPCV                              | C     | Proposed |
| D-017 | Time-decay on sample weights                                          | B     | Accepted |
| D-018 | Grid containment check: modulo vs. presence-based anti-join           | A     | Accepted |
| D-019 | CHECKSUM verification: soft on missing files                          | A     | Accepted |
| D-020 | ccxt tail bars: zero-fill missing ancillary columns                   | A     | Accepted |
| D-021 | OHLCV schema: 9 columns                                               | A     | Accepted |
| D-022 | Integrity check severity taxonomy                                     | A     | Accepted |
| D-023 | Price sanity bounds: close ∈ [100, 1 000 000] for BTC/USDT            | A     | Accepted |
| D-024 | Gap handling: soft observation, never forward-fill                    | A     | Accepted |
| D-025 | Cross-timeframe alignment check severity                              | A     | Accepted |
| D-026 | pATR for barriers: 15m for both default (MTF kept available)          | B     | Revised  |
| D-027 | Entry-price convention: close of the 15m bar at `t`                   | B     | Accepted |
| D-028 | 1m intra-bar tie-break (honest arm)                                   | B     | Accepted |
| D-029 | `LabelResult` schema and tail-sentinel dtype                          | B     | Accepted |
| D-036 | Gap-fill discipline (leakage probe)                                   | B     | Accepted |
| D-037 | Feature-frame NaN policy (leakage probe)                              | D     | Accepted |
| D-038 | pATR fill policy in label construction (leakage probe)                | B     | Accepted |
| D-039 | Cross-timeframe alignment method (leakage probe)                      | D     | Accepted |
| D-040 | v1's qualified-event filter (`consider_res`)                          | B     | Accepted |
| D-041 | v1-faithful qualified sample-filter (trend-residual gate)             | D→E   | Accepted |

---

## D-001 — Dual-arm methodology (governing rule)

- **Phase:** B (applies B→F) — **Status:** Accepted
- **Decision.** Wherever v1 made a choice we want to improve on, keep **two
  arms**: a *v1-faithful* arm that reproduces v1 exactly (so comparison to v1's
  reported numbers is valid) and an *honest* arm that is methodologically
  correct. Both run through the same harness (Phase C). The honest arm is the
  trusted result; the v1-faithful arm is reported alongside; the **gap is a
  finding**. Where the v1 choice is a defect rather than a design ([D-004](#d-004--embargo-and-purging), [D-006](#d-006--barrier-touch-resolution-source),
  [D-011](#d-011--cost-model), [D-013](#d-013--feature-selection-scope)), the honest arm is primary and the v1 config is run *once* as a
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

- **Phase:** B — **Status:** Accepted
- **Decision.** One prediction/label per **15m** bar close. 1m is the inference-
  timing and barrier-resolution substrate; 4h/1h are auxiliary feature inputs,
  not decision clocks.
- **v1 behavior.** Identical — `TargetExtractor3` operates on 15m; production
  fires every minute but only acts on 15m boundaries.
- **Verdict.** Adopt (no change).
- **Rationale.** No methodological problem with v1's cadence; changing it would
  break comparability for no benefit. Cadence sets sample count, label overlap,
  and turnover, so it is fixed deliberately rather than by default.
- **Recorded alternative.** 1m, 1h, or 4h cadence — not pursued in this iteration.

## D-003 — Vertical barrier: horizon length and no-touch handling

- **Phase:** B — **Status:** Accepted
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
- **Added detail.** A *third* no-touch option exists beyond the two
  recorded alternatives: de Prado's `getBins` relabels vertical-barrier touches
  by the **sign of the return at the horizon**, eliminating the `0` class.
  Explicitly **rejected** — it manufactures ±1 labels from non-events (a flat
  drift closing +0.1% becomes a "win"), exactly the optimistic labeling this
  project avoids. The open head-architecture question (three-class vs. binary) is
  resolved by **[D-014](#d-014--meta-labeling-side--size-decomposition) (meta-labeling)**: the primary model predicts side and a
  binary meta-model absorbs the `0` class as "don't act."
- **Added detail — horizon length changed: default ≈ 48 bars,
  511 reserved for v1-faithful reproduction.** v1's `TargetExtractor3` used
  `n = 16 × 16 × 2 − 1 = 511` 15m bars (~5.3 days) as the vertical barrier
  (`btc_feature_engineering_utils.py:1080`). A friend who worked on v1 advises
  the **typical horizon should be 2–4 candles of the timeframe two steps higher**
  — for the 15m decision clock that is the 4h frame, so ~3 × 4h = **48 15m bars**
  (~12 h), range **32–64** (2–4 × 4h). v1's 511 is ~8–16× longer than this and
  reads as an unprincipled heuristic (a quadratic in the 4h/15m ratio) rather
  than a horizon chosen to the decision cadence. **Verdict:** the v2 **default
  horizon becomes `horizon_bars = 48`** (configurable 32–64); `511` is kept only
  as the explicit value when reproducing v1's published numbers (v1-faithful
  arm). **Ripple:** every horizon-pinned quantity follows the *active* horizon,
  not a hardcoded 511 — [D-004](#d-004--embargo-and-purging)'s purge/embargo length (`= horizon`), [D-005](#d-005--sample-uniqueness-weighting)'s
  overlap/uniqueness windows, and [D-038](#d-038--patr-fill-policy-in-label-construction-leakage-probe)/[D-036](#d-036--gap-fill-discipline-leakage-probe) typed-null regions all key off
  `horizon_bars`. The "511" figures in D-004/D-005 and [L-002](LEARNINGS.md#l-002--real-data-integrity-statistics-phase-a-baseline)/[L-008](LEARNINGS.md#l-008--v1s-default-gap-interpolation-is-non-causal-and-contaminates-labels) remain valid
  as descriptions of the **v1-faithful** configuration. See [L-017](LEARNINGS.md#l-017--reading-v1s-latest_code_and_results-notebooks-refines-does-not-overturn-several-docs).

## D-004 — Embargo and purging

- **Phase:** B — **Status:** Accepted
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
- **Added detail.** Purge and embargo remove **two distinct leaks**.
  *Purging* removes training labels whose outcome **window** overlaps the test
  span (an outcome leak). *Embargo* removes a post-test buffer to kill
  **serial-correlation** leakage that purging cannot see — a label whose window
  ends *before* the test block (no overlap, so purge keeps it) can still share
  the boundary's regime/volatility state. Different mechanisms, different fixes;
  any leak surviving a correct purge is embargo's department. Implementation
  (`getTrainTimes`) must handle three overlap cases — train starts within test,
  train ends within test, train envelops test — with a property-based test
  asserting no surviving training window intersects any test span. The embargo
  length is pinned to the **active horizon**, deliberately stronger than LdP's
  "~1% of observations" heuristic, because the horizon is the true dependence
  timescale here.
- **Note.** The "511" figures throughout this entry describe the
  **v1-faithful** horizon. Per [D-003](#d-003--vertical-barrier-horizon-length-and-no-touch-handling) (added detail) the v2 default horizon is now
  **48 bars**, so the default purge window and embargo are **48**, not 511 —
  embargo = `horizon_bars` regardless of which value is active. The 511 numbers
  remain correct for the v1-faithful arm.

## D-005 — Sample-uniqueness weighting

- **Phase:** B — **Status:** Accepted
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
- **Added detail.** Definitions to lock. Concurrency
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

- **Phase:** B — **Status:** Accepted
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
- **Added detail.** 1m resolution **reduces but does not eliminate**
  same-bar ambiguity: the identical tie-break problem recurs inside any single
  1m bar that straddles both barriers. The residual is ~an order of magnitude
  rarer than at 15m, so the residual bias is small — but log the **1m** same-bar
  ambiguity rate too, so the residual is bounded by measurement rather than
  assumed zero. Formally the label needs `min(τ_u, τ_ℓ)`, which is *unidentified*
  from any bar's OHLC when both barriers fall inside it; finer bars shrink, but
  never fully close, that set of unidentified cases.

## D-007 — Breakeven reference (38.5%, not 50%)

- **Phase:** B — **Status:** Accepted
- **Decision.** Record the pre-cost breakeven hit rate
  `2.5 / (4 + 2.5) = 38.5%` as the reference against which every precision-at-
  threshold is judged. Drop implicit use of 50%.
- **v1 behavior.** Multipliers `m_of_target = 4`, `m_of_stop = 2.5` were used,
  but the implied 38.5% breakeven was never written down; 50% was the implicit
  yardstick.
- **Note — keep the `4 / 2.5` multipliers (resolved).** While
  reading `latest_code_and_results` I noticed its `TargetExtractor3` ran
  `m_pt=1+√5≈3.236, m_ps=2` (long) and `m_nt=950, m_ns=2` (short), which differs
  from the `4 / 2.5` of the original `TargetExtractor` (`E*_*.ipynb:164`). The
  user confirmed **the old `4 / 2.5` multipliers are OK** — so v2 keeps
  `m_target=4.0, m_stop=2.5` (breakeven 38.5%), and PHASE_B's hardcoded values
  stand. The differing values in that one notebook are recorded for context only
  (and as a reminder that other v1 experiments used other multipliers); not an
  open item. See [L-017](LEARNINGS.md#l-017--reading-v1s-latest_code_and_results-notebooks-refines-does-not-overturn-several-docs).
- **Verdict.** Adopt (no real optionality).
- **Rationale.** With a 1.6 : 1 reward:risk, 50% is the wrong bar; a 45%
  precision is already an edge here. Stating the true bar prevents misreading
  results.
- **Recorded alternative.** Implicit 50% (v1) — incorrect; superseded.
- **Added detail.** The 38.5% bar is the general payoff identity
  `breakeven = ℓ / (u + ℓ)` and is **pre-cost**. Net of fees + slippage the
  *effective* breakeven rises **above** 38.5%, because each trade must also pay
  its costs. The honest comparison is therefore net-precision against the
  cost-adjusted breakeven, not net-precision against 38.5%. Compute the
  cost-adjusted breakeven once the [D-011](#d-011--cost-model) cost model is fixed and record it
  alongside the pre-cost reference; the success threshold ([D-008](#d-008--success-threshold-pre-registration)) judges against
  the cost-adjusted number.
- **Added detail — theoretical basis.** The formula
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

- **Phase:** B — **Status:** Accepted
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
- **Added detail — correction to the Sharpe clause.**
  "**Deflated Sharpe > 0**" is **not a meaningful bar**: the DSR is a
  *probability* in `[0, 1]` and is almost always > 0. Replace with
  **DSR > 0.95** (or the chosen confidence). The DSR formula additionally
  requires `N` (number of trials run) and `V` (variance of Sharpe *across*
  trials); a single aggregated walk-forward curve supplies **neither**. Resolve
  the `V` source: either run reduced CPCV (**[D-016](#d-016--backtest-geometry-walk-forward-vs-cpcv)**) to obtain a path
  distribution, **or** define the trial set explicitly (walk-forward folds + the
  two dual arms + the four baselines) and estimate `V` from it. Logging every
  configuration to MLflow is what supplies `N`. Also reference the breakeven as
  the **cost-adjusted** value ([D-007](#d-007--breakeven-reference-385-not-50) added detail), not the bare 38.5%. Finalize
  K, N, the DSR confidence, the PBO ceiling (consider adding a `PBO < 0.2`
  clause), and the `V` source before Phase E begins.
- **Added detail — pinned values.** The pre-registered condition
  is committed at the close of Phase B with:
  - **N = 8** (walk-forward fold count, [D-010](#d-010--walk-forward-geometry) added detail).
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
  be computed once the [D-011](#d-011--cost-model) cost model is finalized in Phase C.

## D-009 — Loss function

- **Phase:** E (decided in B) — **Status:** Accepted
- **Decision.** Two arms. v1-faithful: combined `0.7·MSE + 0.3·MAE` on a scalar
  output with post-hoc threshold search. Honest: a class-weighted **BCE / focal**
  classifier producing calibrated probabilities; weights = class × uniqueness
  ([D-005](#d-005--sample-uniqueness-weighting)). Compare both under the harness.
- **v1 behavior.** Combined MSE+MAE primary (`E4_LossFn.ipynb` also tried pure
  MSE); scalar output, threshold searched post-hoc. BCE/focal never used.
- **Verdict.** Both (genuinely co-runnable).
- **Rationale.** A regression loss on a `{-1,0,+1}` target is unusual; focal loss
  is well-motivated at a 9.3% positive rate. But v1's loss is needed for a valid
  v1 comparison, so we run it rather than discard it.
- **Recorded alternative.** MSE+MAE-only (v1) — kept as the comparison arm.

## D-010 — Walk-forward geometry

- **Phase:** B — **Status:** Accepted
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
- **Added detail — concrete sizing.** The honest-arm geometry is
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
  [D-008](#d-008--success-threshold-pre-registration)'s K-of-N (K = 5, N = 8).

## D-011 — Cost model

- **Phase:** C — **Status:** Accepted
- **Decision.** Add a cost model: taker fee + slippage cushion sized to sub-1m
  touch ambiguity. Report **gross** P&L (lines up with v1) **and** net P&L (the
  honest number). Fills at the barrier price on 1m touch (consistent with [D-006](#d-006--barrier-touch-resolution-source)).
- **v1 behavior.** None. All P&L gross; `StrategyTester._close_current_position`
  computes `100*(price-entry)/entry` with no fee/slippage; entry at bar close.
- **Verdict.** Both (gross retained as the v1-faithful arm; net is primary).
- **Rationale.** Gross-only is an omission, not a decision. A path-dependent
  signal at 15m cadence can churn enough that costs decide profitability, so net
  is the only honest headline.
- **Recorded alternative.** Gross-only, entry-at-close (v1) — kept as the gross
  arm for comparability.

## D-012 — pATR definition lock

- **Phase:** B — **Status:** Accepted
- **Decision.**
  Adopt v1's **percent ATR** (pATR) formula exactly — Wilder smoothing with
  window 10, directional true range via the `up_first` flag derived from 1m
  sub-candles. Lock the formula (Wilder/`pTR`/`up_first`); no changes.
  Definition, `pTR` formula, Wilder recurrence, and `up_first` mechanics live in [`GLOSSARY.md`](GLOSSARY.md).
- **Higher-tf join lag (resolves Q4; corrected against the v1 call-site).**
  Higher-timeframe pATR is joined onto the 15m decision clock with a lag so a
  15m row never sees a higher-tf bar that is not yet fully closed. The lag is
  cleanest stated as **one fully-closed higher-tf bar**; on the 15m grid that is
  **k 15m steps**, where `k = tf // 15` (1h → 4, 4h → 16). At that lag the
  higher-tf value first appears exactly at the bar's *close* — causal, minimal.
  This is the **honest arm** (`higher_tf_lag="causal"`).
  - **What v1 actually does** (`btc_feature_engineering_utils.py:812-816`):
    `patr_60 = df_60.shift(3)`, `patr_240 = df_240.shift(15)`, on the *15m-indexed*
    series, then `ffill`+`bfill`. The shifts are **k − 1** (3, 15), not k.
  - **Why k − 1 leaks 15 minutes.** v1 labels every candle by its **open** time
    (`exo_feature_engineering_utils.py` `_create_the_h4_candle` /
    `_get_the_1h_candle` store the bar covering `[t, t+tf)` at index `t`; verified
    identical in `offlinepredictor/`). With open-labeling a bar does not *close*
    until `t + k` steps, so `shift(k−1)` makes its pATR visible at `t + (k−1)` —
    **one 15m bar before it finishes forming**. That one step is a genuine
    look-ahead leak.
  - **Arms.** Honest = `shift(k)` (value released at close) + forward-fill carry,
    leading rows left null. **v1-faithful** (`higher_tf_lag="v1_faithful"`) =
    reproduce v1 exactly: `shift(k−1)` + ffill + bfill, carrying the 15-min leak.
    Both runnable through `attach_patr` per
    [D-001](#d-001--dual-arm-methodology-governing-rule). **The gap is exactly
    that one 15m step — the finding.**
- **v1 behavior.** Formula identical (this is v1's design). Higher-tf lag =
  per-timeframe `shift(k−1)` on the 15m clock (`patr_60`→3, `patr_240`→15) +
  ffill/bfill, open-labeled — a 15-minute look-ahead. Reproduced in the
  v1-faithful arm.
- **Verdict.** Adopt the formula unchanged; honest arm lags by one fully-closed
  higher-tf bar (`shift k`, causal); v1-faithful arm reproduces v1's `shift(k−1)`
  + ffill/bfill leak.
- **Recorded alternative.** A standard (non-directional) ATR — would break
  comparability and discard a sound design; not used.
- **Correction note.** An earlier version of this entry described the lag as
  "3 higher-tf bars" in higher-tf units and rejected a "15m-clock lag" as leaky.
  Both were wrong: pinning the v1 call-site showed the lag *is* on the 15m clock,
  is per-timeframe (k − 1), and — because v1 is open-labeled — is itself the
  source of a 15-min leak. The honest fix is `shift k`, not a different unit.
  The leak is documented as [L-018](LEARNINGS.md#l-018--v1s-higher-tf-patr-join-is-a-15-minute-look-ahead-leak-open-labeled-shiftk1).
- **Estimator-faithfulness note.** López de Prado's reference
  sets the volatility target `trgt` to an **EWMA standard deviation of
  close-to-close returns**, not to ATR.
  ATR is a different (though closely related) estimator.
  We deliberately **retain** v1's pATR for faithfulness;
  the EWMA-of-returns alternative is noted and **not adopted**.
  No methodology conflict — only an explicit acknowledgment that `trgt ≡ pATR`
  is a chosen estimator, not the book's default.
- **See also.** [`GLOSSARY.md`](GLOSSARY.md) →
  [pATR](GLOSSARY.md#patr-percent-atr) ·
  [pTR](GLOSSARY.md#ptr-percent-true-range) ·
  [Wilder smoothing](GLOSSARY.md#wilder-smoothing) ·
  [`up_first` flag](GLOSSARY.md#up_first-flag) ·
  [higher-tf join lag](GLOSSARY.md#higher-tf-patr-join-lag).

## D-013 — Feature-selection scope

- **Phase:** D — **Status:** Accepted
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

- **Phase:** E (decided in B) — **Status:** Proposed
- **Open question to resolve before Phase E begins:** ratify whether
  meta-labeling stays in this iteration or moves to a follow-on iteration.
  If deferred, fall back to [D-009](#d-009--loss-function)'s single-stage arms.
- **Decision.** Model the target as **side then size**. The primary model
  (`ConvWideDeepLSTMNet`) predicts direction; a separate **binary meta-model**,
  trained only on bars where the primary takes a position (`ŝ_t ≠ 0`), predicts
  `m_t = 1[ŝ_t = y_t]` (was the primary's call correct) and outputs a calibrated
  probability used to **filter and size** the bet. Act iff `p̂(m=1) > breakeven`
  ([D-007](#d-007--breakeven-reference-385-not-50), cost-adjusted), and size by conviction above breakeven. This absorbs
  the no-touch (`0`) class as "primary wrong → don't act," resolving the open
  head-architecture question in [D-003](#d-003--vertical-barrier-horizon-length-and-no-touch-handling). Primary model tuned for **high recall**;
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
  kept as comparison arm. If meta-labeling is deferred to a follow-on iteration, fall back to
  the directional collapse with `0` folded into "no-trade," and revisit.
- **⚠️ Correction — the "v1 already did this" claim is retracted.**
  The "v1 already implemented this" detail below argued v1 implicitly implemented meta-labeling via
  `target2=True` and that the v1-faithful arm must reproduce both `rt3` and
  `target3`. A friend who worked on v1 reports `target2`/`stop2_slack` are
  **"left from a failed experiment"**, and the code agrees: although the labeler
  is instantiated with `target2=True`, **every** `generate_results(...)` call
  evaluates with `target2=False` (`E1/E2/E4/E6_*.ipynb`, `0_Preprocessing.ipynb`)
  — v1 produced the meta-label and then did not use it in reported results. So
  D-014 stands **only as a new v2 idea** (learned meta-labeling in Phase E), not
  as a reproduction of something v1 did. The v1-faithful Phase-B labeler **drops
  `target2`/`stop2_slack`** and produces the plain three-class side label only;
  `stop2_level` is removed from `LabelResult`. See [L-006](LEARNINGS.md#l-006--v1s-target2true-is-embedded-meta-labeling--but-it-was-a-failed-experiment) (corrected), [L-017](LEARNINGS.md#l-017--reading-v1s-latest_code_and_results-notebooks-refines-does-not-overturn-several-docs), and
  PHASE_B B.1. The text below is kept for the record but is no longer load-bearing.
- **Added detail — v1 already implemented this implicitly
  [RETRACTED — see correction above].**
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
  the meta-label rule; v2 (D-014) learns it from data. ~~The v1-faithful arm
  in Phase B must reproduce both outputs, not just `target3`.~~
  **[Superseded by the correction above: `target3` is not reproduced; the
  v1-faithful arm produces the side label only.]**

## D-015 — Labeling event filter (sampling cadence)

- **Phase:** B — **Status:** Rejected
- **Scope of rejection:** this iteration only; revisit in a follow-on iteration if the B.2
  diagnostics motivate it.
- **Decision.** Honest arm samples decision points with a **symmetric CUSUM
  filter** on de-meaned 15m returns: `S⁺_t = max(0, S⁺_{t-1} + r_t − E[r_t])`,
  `S⁻_t = min(0, S⁻_{t-1} + r_t − E[r_t])`, emit a labeling event (and reset)
  when `S⁺_t ≥ κ` or `S⁻_t ≤ −κ`. v1-faithful arm: the fixed
  one-label-per-15m-close cadence ([D-002](#d-002--decision-cadence-15m-bar-close)). This layers *on top of* D-002 — D-002
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
  volatility ([D-012](#d-012--patr-definition-lock) units). The filter uses past returns only — no look-ahead.
- **Recorded alternative.** Fixed 15m-close cadence (v1, D-002) — the comparison
  arm and the default if CUSUM is descoped from this iteration.
- **Added detail — descoped.** CUSUM event sampling is **out of
  scope for this iteration**. Honest-arm cadence stays at every 15m close (D-002).
  Rationale: B.2 already produces the diagnostics (timeout fraction, average
  uniqueness / `N_eff`) that would motivate CUSUM; if those numbers reveal the
  fixed-clock cadence is hurting more than helping, the filter can be added in
  a follow-on iteration as an honest-arm refinement without disturbing the Phase-B label /
  split / weight contracts. Pinning `κ` and re-measuring is also itself a
  multi-day investigation; deferring it keeps this iteration focused.

## D-016 — Backtest geometry: walk-forward vs. CPCV

- **Phase:** C (decided in B) — **Status:** Proposed
- **Qualifier:** compute-gated. Scheme value reserved in Phase B; impl in
  Phase C (see added detail below).
- **Decision.** Primary backtester = single-path purged + embargoed
  **walk-forward** ([D-010](#d-010--walk-forward-geometry)). Run **Combinatorial Purged CV (CPCV)** in a *reduced*
  configuration — on the four baselines and a reduced-epoch model — to obtain the
  distribution of out-of-sample Sharpe across `φ = C(N−1, k−1)` paths, supplying
  the across-trial variance `V` the Deflated Sharpe needs ([D-008](#d-008--success-threshold-pre-registration)). The headline
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
- **Added detail — scheme value reserved in Phase B.** The
  `scheme="cpcv"` value is **reserved in `make_walkforward_folds`** at Phase B
  to keep the API stable; the implementation lands in Phase C and is
  compute-gated. D-008's pinned values (see its added detail) take
  trial-set estimation as the **primary** `V` source; reduced CPCV is the
  **secondary** option, run only if the trial-set estimator is too narrow.

## D-017 — Time-decay on sample weights

- **Phase:** B — **Status:** Accepted
- **Verdict in one line:** resolved to "off" — no time-decay layer in this iteration.
- **Decision.** **No time decay** in this iteration. Final weight = `class × uniqueness`
  ([D-005](#d-005--sample-uniqueness-weighting)) with de Prado's piecewise-linear decay on cumulative uniqueness disabled
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

- **Phase:** A — **Status:** Accepted
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

- **Phase:** A — **Status:** Accepted
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
- **Added detail — v1 has none of this discipline** (A.5,
  [L-015](LEARNINGS.md#l-015--minor-v1-fill-and-convention-behaviors-catch-all)). The v1 audit confirms v1 performs no archive integrity
  verification of any kind. D-019 is a v2-only discipline; no dual-arm
  probe is needed.

## D-020 — ccxt tail bars: zero-fill missing ancillary columns

- **Phase:** A — **Status:** Accepted
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
  meaningless zeros in these three columns — is documented in [L-003](LEARNINGS.md#l-003--ancillary-columns-are-unreliable-for-early-and-ccxt-sourced-bars) and must
  be guarded in Phase D.
- **Recorded alternative.** NaN / null fill — propagates unpredictably
  through floating-point indicator math; rejected in favour of an explicit
  zero that can be detected and filtered deterministically.
- **Added detail — v1 has no ccxt path** (A.5). The v1
  audit confirms v1 fetches from a single source (Binance directly) with
  no cross-source verification, and never reads the three ancillary
  columns this decision governs. D-020 is a v2-only discipline; no
  dual-arm probe.

## D-021 — OHLCV schema: 9 columns

- **Phase:** A — **Status:** Accepted
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

- **Phase:** A — **Status:** Accepted
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
- **Added detail — v1 has none of this taxonomy**
  ([L-013](LEARNINGS.md#l-013--v1-has-no-ohlc-arithmetic-check-at-any-stage), [L-014](LEARNINGS.md#l-014--v1-silently-clamps-volume--1-to-1), [L-015](LEARNINGS.md#l-015--minor-v1-fill-and-convention-behaviors-catch-all)). The v1 audit confirms v1 enforces no OHLC
  arithmetic check, no NaN OHLC check, no price-bound check, and
  silently clamps `volume < 1 → 1` rather than classifying zero-volume
  bars as either hard or soft. D-022 is a v2-only discipline (no
  separate dual-arm probe); v1-faithful reproductions inherit the lack
  of validation by construction.

## D-023 — Price sanity bounds: close ∈ [100, 1 000 000] for BTC/USDT

- **Phase:** A — **Status:** Accepted
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

- **Phase:** A — **Status:** Accepted
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
- **Added detail — operationalized as [D-036](#d-036--gap-fill-discipline-leakage-probe)**
  ([L-008](LEARNINGS.md#l-008--v1s-default-gap-interpolation-is-non-causal-and-contaminates-labels)). The v1 audit confirms v1's default
  `LinearInterpolator._estimate_ohlcv_and_insert_the_candles` synthesizes
  missing OHLCV by *non-causal* weighted average of the previous and
  next available bar — a stronger violation than this entry's
  "Recorded alternative" anticipated. D-036 turns the rule from a
  v2-only discipline into a dual-arm leakage probe: the honest arm
  enforces this entry; the v1-faithful arm reproduces v1's
  interpolation once to measure the inflation.

## D-025 — Cross-timeframe alignment check severity: grid containment HARD, spacing and coverage SOFT

- **Phase:** A — **Status:** Accepted
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
  hard-fail on the known Binance early-data timestamp anomaly ([L-001](LEARNINGS.md#l-001--early-binance-1m-data-has-sub-minute-timestamp-offsets))
  without delivering additional protection, since the anomaly is fully
  characterised and its downstream impact is bounded; rejected.
- **Added detail — reinforced by [D-039](#d-039--cross-timeframe-alignment-method-leakage-probe)**
  ([L-011](LEARNINGS.md#l-011--v1-mixes-multi-tf-samples-by-counter-walking-not-by-timestamp-join), [L-012](LEARNINGS.md#l-012--v1-silently-floor-snaps-off-grid-bars-per-timeframe-including-the-binance-quirk-window)). The v1 audit confirms v1 has no cross-timeframe
  alignment check at all and assembles multi-TF features via
  `DataMixer3._mix_train` counter-walking rather than timestamp join.
  D-025 governs the *check* discipline; D-039 makes the *join method*
  itself a dual-arm probe in Phase D. D-025 is a precondition for
  D-039's honest arm to be sound — a `merge_asof` on misaligned grids
  would produce wrong results silently. The two are complementary, not
  overlapping.

## D-026 — pATR for barriers: 15m for both target and stop (MTF kept available)

- **Phase:** B — **Status:**
  Revised (default changed to 15/15; MTF retained as an available arm)
- **Verdict in one line:**
  default to **15m pATR for both** target and stop.
  Keep MTF asymmetry as an available, off-by-default experimental arm — **not** discarded.
- **Decision.**
  The profit target and the stop are both anchored on the **15m pATR** (`patr_15`) by default.
  `make_labels` still accepts `target_patr_col` and `stop_patr_col` separately so the asymmetric multi-timeframe configuration (e.g. `patr_240` target / `patr_60` stop) can be run as an **optional experiment**;
  it is just not the default for this iteration.
- **Why the default changed.** A friend who worked on v1 advised
  directly: *"Use 15m pATR for both target and stop. Do not use 1h or 4h pATR for now."*
  Consistent with this, the `TargetExtractor3` constructor default is `target_patr=15, stop_patr=15` (`btc_feature_engineering_utils.py:968`, `:972-974`) and the notebooks in `latest_code_and_results` (`0_Preprocessing.ipynb`, `E1/E2/E4/E6_*.ipynb`) instantiate it as 15/15.
- **v1 behavior.**
  Both barriers anchored on `patr_15` in the `latest_code_and_results` config.
  The 240/60 split is a supported path; its use elsewhere in v1 is unconfirmed.
- **Verdict.** Default 15/15 for v2 (friend's recommendation).
  MTF asymmetry retained as an available, separately reported experiment.
- **Recorded alternative.**
  MTF asymmetry (`patr_240` target / `patr_60` stop) — kept as an **available experimental arm**, off by default;
  the term-structure rationale (L-007) remains valid.
  Single-timeframe on a *non-15m* native pATR is not pursued.
- **See also.** [`GLOSSARY.md`](GLOSSARY.md) →
  [MTF pATR](GLOSSARY.md#mtf-patr-multi-timeframe-asymmetry) ·
  [pATR](GLOSSARY.md#patr-percent-atr) ·
  [Profit barrier](GLOSSARY.md#profit-barrier) ·
  [Stop barrier](GLOSSARY.md#stop-barrier).

## D-027 — Entry-price convention: close of the 15m bar at `t`

- **Phase:** B — **Status:** Accepted
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
  fixed in [D-002](#d-002--decision-cadence-15m-bar-close). Anchoring on `next_open` would introduce a one-bar
  conservatism that is not in the v1 reference and would require its own
  honest-arm justification.
- **Recorded alternative.** Anchor on the open of the **next** 15m bar at
  `t+1` (no current-bar bleed in the price either) — rejected for this iteration as
  unnecessary; revisit only if leakage analysis finds the close anchor lets a
  feature-side leak survive.

## D-028 — 1m intra-bar tie-break (honest arm)

- **Phase:** B — **Status:** Accepted
- **Decision.** When a single 1m bar's high–low range contains *both*
  barriers, the honest arm resolves the order of first touch deterministically
  using the bar's net direction:
  - `close > open` → assume the **high was touched first**.
  - `close ≤ open` → assume the **low was touched first**.
  Bars where this tie-break fires are flagged `ambig_1m = True` in
  `LabelResult`; the rate is logged per fold ([D-006](#d-006--barrier-touch-resolution-source) added detail).
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

- **Phase:** B — **Status:** Accepted
- **Decision.** `make_labels` returns a `LabelResult` whose `frame` is a single
  Polars `DataFrame` aligned to the 15m decision clock — one row per 15m bar in
  `df15`, never reindexed or filtered by the labeler. Columns (full list in
  PHASE_B.md B.1):
  `open_time, rt3, first_touch_idx_1m, entry_price, profit_level,
  stop_level, ambig_15m, ambig_1m, is_complete`.
  - `rt3` is `Int8` nullable; tail rows whose horizon window is incomplete
    (and unresolvable rows under the honest D-036 / D-038 probes) carry
    `null` in `rt3` plus `is_complete = False`.
  - **`target3` / `stop2_level` are intentionally absent** — they belonged to
    v1's discarded `target2` meta-label path, which v2 does not reproduce
    ([D-014](#d-014--meta-labeling-side--size-decomposition), [L-006](LEARNINGS.md#l-006--v1s-target2true-is-embedded-meta-labeling--but-it-was-a-failed-experiment)).
    (Corrected 2026-06-11: an earlier draft of this entry listed both columns
    before the D-014/L-006 correction propagated here; the implemented schema in
    `labels/targets.py` `LABEL_SCHEMA` and PHASE_B.md B.1 are authoritative.)
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
  - Boolean `is_labelable` column with arbitrary values in `rt3`
    for unlabeled rows — rejected; `rt3.is_null()` already conveys
    unlabelability and a typed null is harder to misuse than a sentinel
    integer.
- **Added detail — typed-null is the honest-arm signal
  for [D-036](#d-036--gap-fill-discipline-leakage-probe) and [D-038](#d-038--patr-fill-policy-in-label-construction-leakage-probe).** The new probes both depend on D-029's
  typed-null mechanism: when a label's resolution would require
  synthesized data (a gap crossed by the 1m barrier walk, D-036; or a
  NaN pATR at the anchor bar, D-038), the honest arm emits
  `rt3 = null, is_complete = False`. v1's `fillna(33)`
  magic-number tail ([L-015](LEARNINGS.md#l-015--minor-v1-fill-and-convention-behaviors-catch-all)) is the v1-faithful arm's counterpart, and
  the gap between these two representations is exactly the inflation
  D-036 / D-038 measure.

## D-036 — Gap-fill discipline (leakage probe)

- **Phase:** B (primary; downstream in D) — **Status:** Accepted
- **Decision.** Leakage-probe flavor per [D-001](#d-001--dual-arm-methodology-governing-rule), now **three arms** on the
  `gap_fill` axis. *Honest arm primary*: gaps in raw OHLCV are left as
  observed ([D-024](#d-024--gap-handling-soft-observation-never-forward-fill)); barrier walks in `make_labels` that would cross an
  unfilled gap return a typed-null label ([D-029](#d-029--labelresult-schema-and-tail-sentinel-dtype)); indicator lookbacks in
  Phase D that would cross a gap return masked cells, dropped by the batch
  sampler. *v1-faithful arm* (run once, then retired): reproduce v1's
  `LinearInterpolator` non-causal weighted-average fill before labeling and
  feature compute. *Causal-ZOH comparison arm*: forward-fill
  each gap by repeating the last observed bar (zero-order hold) — **causal**, so
  no look-ahead, but still fabricates bars. It isolates how much of the
  honest-vs-v1 gap is due to *non-causality* (the weighted average reaching into
  the next real bar) versus *fabrication per se* (synthesizing any bar at all):
  ZOH removes the former while keeping the latter.
- **Why three arms.** A friend who worked on v1 suggested ZOH as the gap-fill
  improvement (Phase-B feedback B1-A), while their Phase-A note ([L-008](LEARNINGS.md#l-008--v1s-default-gap-interpolation-is-non-causal-and-contaminates-labels)) prefers
  flagging nulls and excluding them — i.e. the typed-null honest arm. The two
  are not in conflict once ZOH is positioned as a *middle* comparison point
  rather than the trusted result: honest (typed-null) stays primary, ZOH sits
  between honest and v1-noncausal, and the deltas attribute the inflation.
- **v1 behavior.** Default
  `LinearInterpolator._estimate_ohlcv_and_insert_the_candles` synthesizes
  missing OHLCV by weighted average of the *previous and next* available
  bar — non-causal. Driven by
  `BtcPreprocessor.interpolate_the_raw_data_and_add_up_first` for
  1m / 15m / 1h / 4h. A causal alternative
  (`_causal_estimate_ohlcv_and_insert_the_candles`) exists but is not
  the default. See L-008.
- **Verdict.** New (leakage probe).
- **Rationale.** Every synthesized bar's high/low is a function of the
  next real bar's OHLC. `TargetExtractor.detect_reversals` walks those
  synthesized highs/lows during barrier resolution, so the label depends
  on data after `t`. The same series feeds every TA indicator in Phase D,
  so the leak compounds on the feature side. Among all v1 audit findings,
  this is the most direct contamination of the label.
- **Recorded alternative.** Use v1's causal mode for both arms — rejected;
  v1's published numbers came from the non-causal default and the
  gap-artifact row needs to measure *that* inflation, not a reformulated
  hypothetical v1.

## D-037 — Feature-frame NaN policy (leakage probe)

- **Phase:** D — **Status:** Accepted
- **Decision.** Leakage-probe flavor per [D-001](#d-001--dual-arm-methodology-governing-rule). *Honest arm primary*: NaN
  cells in any feature column are left untouched; the model's batch
  sampler masks rows whose sample window contains NaN in any consumed
  feature (so indicator warm-up rows are excluded rather than
  back-filled). *v1-faithful arm* (run once, then retired): reproduce
  v1's blanket `btc_df.fillna(method='bfill')` at the equivalent assembly
  step.
- **v1 behavior.** All four `DataMixer` variants (`DataMixer`,
  `defDataMixer`, `NoTRFDataMixer`, `logDataMixer`) apply `bfill` to the
  entire feature frame at the end of `load_features`. See [L-009](LEARNINGS.md#l-009--v1s-datamixerload_features-applies-blanket-bfill-to-every-feature-column).
- **Verdict.** New (leakage probe).
- **Rationale.** The `bfill` runs *after* multi-TF assembly, so a single
  NaN cell can be filled from a row at a different real timestamp.
  Indicator warm-up windows (e.g., the first ~20 rows of a 20-bar SMA)
  are the most-affected region; since v1 doesn't trim warm-up rows before
  training, the earliest training samples are entirely back-filled from
  future. Distinct from [D-036](#d-036--gap-fill-discipline-leakage-probe) because the NaN source is indicator
  arithmetic, not missing data — both probes must be disabled in the
  honest arm; v1 reproduces both.
- **Recorded alternative.** Forward-fill instead — rejected; even causal
  `ffill` on indicator warm-up rows fabricates values that didn't exist
  at decision time. Honest semantics require masking, not synthesis.

## D-038 — pATR fill policy in label construction (leakage probe)

- **Phase:** B — **Status:** Accepted
- **Decision.** Leakage-probe flavor per [D-001](#d-001--dual-arm-methodology-governing-rule). *Honest arm primary*:
  barrier widths at bar `t` use only pATR realised at or before `t`. Bars
  whose pATR is NaN at `t` (series start, gap-adjacent) emit a typed-null
  label ([D-029](#d-029--labelresult-schema-and-tail-sentinel-dtype)) rather than a fabricated one. *v1-faithful arm* (run
  once, then retired): reproduce the
  `patr*.fillna('ffill').fillna('bfill')` chain v1 runs inside
  `TargetExtractor2` and `TargetExtractor3`.
- **v1 behavior.** v1's `TargetExtractor2` and `TargetExtractor3` apply
  `ffill` then `bfill` to `patr_15`, `patr_60`, `patr_240` *as part of
  the label-construction step*. See [L-010](LEARNINGS.md#l-010--v1s-patr-series-is-ffillbfilld-inside-targetextractor23).
- **Verdict.** New (leakage probe).
- **Rationale.** The pATR series scales the triple-barrier widths
  (longer-horizon for target, shorter for stop, per [D-026](#d-026--patr-for-barriers-15m-for-both-target-and-stop-mtf-kept-available)). When `bfill`
  runs inside the labeler, any bar with NaN pATR gets a barrier width
  derived from *future* pATR observations — so the label's verdict
  depends on data after `t`. Concentrated at series start (Wilder
  warm-up) and gap-adjacent rows. Distinct from [D-037](#d-037--feature-frame-nan-policy-leakage-probe) because it operates
  on the labeling pathway rather than the feature pathway, and from [D-036](#d-036--gap-fill-discipline-leakage-probe)
  because the NaN source is indicator warm-up, not missing data.
- **Recorded alternative.** Use only `ffill` for both arms — rejected;
  v1's published numbers came from the exact `ffill`+`bfill` chain and
  the gap-artifact row needs to measure *that* inflation.

## D-039 — Cross-timeframe alignment method (leakage probe)

- **Phase:** D — **Status:** Accepted
- **Decision.** Leakage-probe flavor per [D-001](#d-001--dual-arm-methodology-governing-rule). *Honest arm primary*:
  multi-TF features assembled via `merge_asof` (backward direction,
  strict) on the 15m decision clock — a higher-timeframe bar is visible
  at or after its close, never the forming bar. Any timeframe without a
  bar at or before the decision bar emits a typed-null cell. *v1-faithful
  arm* (run once, then retired): reproduce v1's `DataMixer3._mix_train`
  counter-walk over per-TF frames using integer counters `i1, i2, i3`.
- **v1 behavior.** Each timeframe loaded independently with the same
  `first_day` / `last_day` window. The mixer walks the four per-TF frames
  with integer counters and emits one row per tick. No timestamp join,
  no intersection check. See [L-011](LEARNINGS.md#l-011--v1-mixes-multi-tf-samples-by-counter-walking-not-by-timestamp-join).
- **Verdict.** New (leakage probe).
- **Rationale.** Counter-walking assumes uniform coverage across
  timeframes. Any drift — a missing day, a snap-collision drop ([L-012](LEARNINGS.md#l-012--v1-silently-floor-snaps-off-grid-bars-per-timeframe-including-the-binance-quirk-window)),
  a quirk-window realignment ([L-001](LEARNINGS.md#l-001--early-binance-1m-data-has-sub-minute-timestamp-offsets)) — causes bars from different real
  timestamps to be stitched together as if aligned, and the drift
  accumulates silently. Distinct from [D-036](#d-036--gap-fill-discipline-leakage-probe) (missing data) and [D-037](#d-037--feature-frame-nan-policy-leakage-probe)
  (NaN fill) because the leak is *misalignment*, not synthesis.
  Reinforces [D-025](#d-025--cross-timeframe-alignment-check-severity-grid-containment-hard-spacing-and-coverage-soft)'s cross-TF alignment check by making the join method
  itself the probe target.
- **Recorded alternative.** Reject v1's mixer and use only `merge_asof`
  for both arms — rejected; v1's published numbers came from the
  counter-walked mix and the gap-artifact row needs to measure *that*
  inflation.

## D-040 — v1's qualified-event filter (`consider_res`)

- **Phase:** B — **Status:** Accepted (resolved 2026-06-11; B.1-unblocking)
- **Context.** v1's `TargetExtractor3` was run with `target2=True, consider_res=True`
  in every `latest_code_and_result` notebook (E1–E6, `0_Preprocessing`). This sets a
  per-bar `qualified` flag, `qualified = int(above_d_res or above_g_res or above_d_sup)`, derived from trend-residual breakout columns (`d_resi`, `g_resi`,
  `d_supi`) and carried alongside the label
  (`btc_feature_engineering_utils.py` `TargetExtractor3._generate_the_targets_df`,
  `reversal_detector(..., qualified)`).
- **Investigation (v1 source read, 2026-06-11).** The three open questions resolve as:
  1. **What the columns encode.** `d_resi` / `g_resi` / `d_supi` are boolean
     support/resistance **breakout** flags (`open` crossing a dynamic / golden
     resistance or a dynamic support line) from
     `Indicators/trend_ta.py:1369,1402-1404`. `qualified` is their OR — i.e. "a
     support/resistance breakout occurred at this bar." It is a **trend-event
     filter**, the same family as the CUSUM filter rejected in
     [D-015](#d-015--labeling-event-filter-sampling-cadence).
  2. **Filter or annotate — both, at different stages.** Inside the labeler
     `qualified` only *annotates*: it is stored as a column and does **not** change
     which bars are labeled. The `consider_res and not qualified` branch flips only
     the **first** return value (`target3`, the meta-label) `1→0`; the **second**
     value (`rt3`, the side label) is unchanged
     (`reversal_detector`, lines 1123–1141). Downstream, however, the production
     trainer (`ModelingUtils/trainers.py:119-121`) calls
     `get_qualified_reframed_train/test/val_data()`, which **filter the sample set
     to `qualified == 1`** (`...if self.y2_*.iloc[i, qualified_idx] == 1`, line
     2568). Notebook output: ~25.4% of bars retained in the trend-residual-filter
     (TRF) arm; ~100% (no-op) in the NoTRF arm. So v1's TRF runs trained and were
     scored on a ~quarter subset.
  3. **v2 reproduction — see verdict.**
- **Verdict.** **`rt3` is provably unaffected by `consider_res`/`qualified`** — it
  flips only `target3`, the discarded meta-label v2 does not produce
  ([D-014](#d-014--meta-labeling-side--size-decomposition), [L-006](LEARNINGS.md#l-006--v1s-target2true-is-embedded-meta-labeling--but-it-was-a-failed-experiment)). Therefore **B.1's `make_labels` needs no change and is
  unblocked**: the v1-faithful labeling arm produces identical `rt3` whether or not
  the flag is modeled. The **honest arm does not adopt the qualified filter** —
  D-002's unqualified per-15m-close cadence stands, consistent with rejecting the
  analogous event filter in D-015. The `qualified` *sample-filter* is a genuine v1
  mechanism but it lives **downstream** (it needs the trend-residual breakout
  indicators, Phase D feature work, and acts at the sampler/eval stage), so it is
  **not** a labeler concern; reproducing it in the v1-faithful arm is split out to
  [D-041](#d-041--v1-faithful-qualified-sample-filter-trend-residual-gate).
- **Recorded alternative.** (a) Reproduce the qualified filter inside the B.1
  labeler — rejected; it changes no `rt3` value and the indicators it needs do not
  exist until Phase D, so it would couple the labeler to feature code for no label
  effect. (b) Ignore `consider_res` entirely, including downstream — rejected in
  favor of D-041, because v1's TRF reported numbers came from the `qualified == 1`
  subset and a valid "v1 said X" comparison must reproduce that population.
- **See also.** [L-017](LEARNINGS.md#l-017--reading-v1s-latest_code_and_results-notebooks-refines-does-not-overturn-several-docs) (where this surfaced);
  [D-002](#d-002--decision-cadence-15m-bar-close) (decision cadence);
  [D-015](#d-015--labeling-event-filter-sampling-cadence) (rejected CUSUM event filter — the honest-arm analogue);
  [D-014](#d-014--meta-labeling-side--size-decomposition) (the `target3` meta-label is not reproduced);
  [D-041](#d-041--v1-faithful-qualified-sample-filter-trend-residual-gate) (the deferred sample-filter).

---

## D-041 — v1-faithful qualified sample-filter (trend-residual gate)

- **Phase:** D→E — **Status:** Accepted (deferred implementation; split from
  [D-040](#d-040--v1s-qualified-event-filter-consider_res) 2026-06-11)
- **Decision.** Comparison/selection concern carved out of D-040. The v1-faithful
  arm **will** reproduce v1's `qualified == 1` sample-filter so that comparisons
  against v1's trend-residual-filter (TRF) reported numbers are valid, but the
  implementation is **deferred to where its inputs live**: the `d_resi` / `g_resi`
  / `d_supi` breakout indicators are built in **Phase D** (feature engineering),
  and the row-filter is applied at the **Phase E** sampler/eval stage (mirroring
  v1's `get_qualified_reframed_*_data`). The honest arm never filters on
  `qualified` (D-002 cadence; consistent with [D-015](#d-015--labeling-event-filter-sampling-cadence)).
- **Scope at acceptance (per [D-001](#d-001--dual-arm-methodology-governing-rule)).** Classify as a leakage/selection probe
  when implemented: honest primary (unfiltered), v1-faithful run to measure the
  selection effect; the qualified-subset retention rate is logged. Whether the
  honest arm also *carries* a `qualified` annotation column for analysis (without
  filtering on it) is decided in Phase D alongside the indicator build.
- **Why deferred, not done in B.** `qualified` changes no `rt3` value (D-040), and
  its indicator inputs do not exist until Phase D. Implementing it in B.1 would
  couple the labeler to feature code for zero label effect. Phase B therefore
  closes D-040 without it; D-041 carries the remaining work.
- **Recorded alternative.** Treat the filter as fully out of scope this iteration
  (annotate v1's TRF numbers as not-reproduced) — rejected per the user decision
  2026-06-11 to keep the v1-faithful comparison faithful to the population v1
  actually trained on.
- **See also.** [D-040](#d-040--v1s-qualified-event-filter-consider_res) (parent);
  [D-013](#d-013--feature-selection-scope) (Phase D feature-scope discipline);
  [D-015](#d-015--labeling-event-filter-sampling-cadence) (rejected honest-arm event filter);
  [L-017](LEARNINGS.md#l-017--reading-v1s-latest_code_and_results-notebooks-refines-does-not-overturn-several-docs).
