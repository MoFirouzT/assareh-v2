# Assareh-v2 — Plan (Ambitions 1–3)

This document covers the current iteration of work — fulfilling
**Ambitions 1–3** from `VISION.md` (Learn, Honest verdict, ML engineering signal).
**Ambition 4** (the optional live system) and any further engineering polish
beyond what ships here are planned later, once this iteration produces
results worth engineering around.

> **Companion docs.**
>
> - `VISION.md` for the why and the definition of done;
> - `DECISIONS.md` for every governing choice (cited inline as `D-NNN`) and verdicts;
> - `LEARNINGS.md` for findings and dead ends;
> - `GLOSSARY.md` for project terminology and definitions.

---

## Dual-arm methodology (cross-cutting)

The single most important methodological commitment in this iteration, applied from Phase B onward.
Every place where v1 made a choice that we want to improve on, we keep **both**:

- **v1-faithful arm** — reproduces the v1 decision exactly, so any comparison against v1's reported numbers is valid.
- **Honest arm** — the methodologically correct version, which is the primary result of the project.

Both arms run through the **same** harness (Phase C).
The number we trust is the honest arm;
the number we report *alongside* it is the v1-faithful arm;
and the **gap between them is a finding** —
it quantifies how much of v1's apparent edge was leakage, optimistic fills, or selection bias rather than signal.

**Two flavors of dual-arm.**
The category is fixed when the decision is accepted:

- **Leakage probes** — honest primary;
  the v1 configuration is run *once* to measure the inflation, then retired.
  Used when the v1 choice is a defect, not a design alternative.
  Members fall into two sub-groups:
  - *Statistical-discipline probes:*
    D-004 embargo, D-006 barrier-touch resolution, D-010 walk-forward geometry, D-013 feature-selection scope.
  - *Data-handling probes* (surfaced by the v1 audit, L-008–L-011):
    D-036 gap-fill discipline, D-037 feature-frame NaN policy, D-038 pATR fill policy, D-039 cross-timeframe alignment method.
  Their inflations are the cells of the Phase E gap artifact.
- **Retained comparison arms** —
  both arms run every fold, every evaluation, indefinitely.
  Used when the v1 choice is a defensible design alternative, not a leak.
  Members:
  D-009 loss function (combined MSE+MAE vs. class-weighted BCE/focal), D-011 cost model (gross v1-faithful vs. net honest, reported as gross/net metric pairs).
  These do not retire;
  the gap they expose is a modeling trade-off, not a leak.

See `DECISIONS.md` for the governing rules.
New dual-arm decisions classify into one of these flavors at acceptance — recorded in the decision body.

---

## Phase A — Foundation: data, repo, environment

**Goal:**
Have a clean repo, a reproducible environment, and validated raw data on disk.
No modeling yet.

**Exit criteria:**
all four timeframes on disk, integrity-clean, cross-timeframe aligned; loader tests green; A-phase decisions appended to `DECISIONS.md`.

**Key deliverables:**

- Repo skeleton with `pyproject.toml` (uv-managed), `CLAUDE.md`, `VISION.md`, `DECISIONS.md`, `LEARNINGS.md`, `README.md` stub
- Raw OHLCV data for BTC/USDT (4h, 1h, 15m, 1m) downloaded from Binance, with checksum verification
1m is a first-class timeframe and the substrate for barrier-touch resolution in Phase B
- Data integrity checks:
no duplicates, no gaps unaccounted for, timezone consistent, schema documented, **cross-timeframe grid alignment verified**
- A Polars-based data loader with tests

**What's deliberately deferred:** feature engineering, target definition, indicators.
All of that is Phase B and later.

See `PHASE_A.md` for the full breakdown.

---

## Phase B — Target definition and split design

**Goal:**
Define the prediction target rigorously, design walk-forward splits
that respect the temporal structure *and* the label horizon, and lock in the
evaluation-harness skeleton *before* writing any model.

**Exit criteria:** label modules, splits, and held-out reservation tested; D-008 Stage 1 (threshold structure) appended; D-014 ratification queued for Phase E; **D-040 (qualified-event filter) resolved to Accepted/Rejected**; B-phase decision entries in DECISIONS.md.

**Key deliverables:**

- **Multi-timeframe [pATR](GLOSSARY.md#patr-percent-atr) module** (`features/patr.py`) producing `patr_15`,
  `patr_60`, `patr_240` on the 15m clock — prerequisite for B.1
  (D-012, D-026, D-031)
- Triple-barrier target function with tests — **1m-resolved barrier ordering
  primary** (honest arm), 15m-optimistic ordering retained as the v1-faithful
  comparison arm (D-006). Barriers anchored on the 15m close (D-027); 1m
  intra-bar tie-break by `close > open` direction (D-028); **both barriers use
  15m pATR** by default (D-026 revised — friend's recommendation + the inspected
  v1 config; MTF asymmetry kept available, off by default); horizon defaults to
  ~48 bars (two-TF-higher rule, D-003; 511 reproduces v1)
- **Data-handling leakage probes wired into label construction**
  (L-008, L-010). The v1-faithful labeling arm additionally reproduces
  *(i)* v1's non-causal `LinearInterpolator` gap fill on the 1m
  resolution substrate before barrier walking (D-036) and
  *(ii)* the `patr*.fillna('ffill').fillna('bfill')` chain inside
  `TargetExtractor` (D-038). The honest arm leaves gaps observed (D-024)
  and uses only pATR realised at or before `t`; bars where either is
  unresolvable emit typed-null labels (D-029) rather than fabricated ones
- **Side label only (D-014 gate).** `make_labels` returns `rt3`, the three-class
  side label. v1's embedded `target2`/`target3`/`stop2` meta-label path is **not
  reproduced** — it was a discarded v1 experiment (L-006 corrected, L-017).
  Learned meta-labeling is a *new* v2 idea (D-014): whether a separate meta-model
  is trained on top of `rt3` in Phase E is **D-014's open question, ratified
  before Phase E begins**
- **Resolve v1's qualified-event filter (D-040, open).** v1 ran `consider_res=True`
  (a `qualified` flag from trend-residual columns gating labeling events). Decide
  before B.1 is locked whether the v1-faithful arm reproduces it and whether the
  honest arm carries a `qualified` column; until then the default is D-002's
  unqualified per-15m-close cadence (L-017, D-040)
- `LabelResult` as a single Polars DataFrame on the 15m decision clock with
  typed-null tail sentinels (D-029); per-arm same-bar ambiguity rates logged
  at both 15m and 1m grain
- Documented target statistics: positive rate, **timeout (no-touch) rate**,
  distribution over time, regime shifts; the **38.5% breakeven reference**
  (cost-free) written down explicitly (D-007); the cost-adjusted variant
  lands at the C/D handoff once D-011's cost model is fixed, feeding the
  success threshold's Stage 2 (below)
- Walk-forward CV scheme implemented and tested, with **purging + embargo
  (embargo = `horizon_bars`, the full label horizon — 48 by default, 511
  v1-faithful)** (D-004), concretely sized
  to **8 folds, ~2y initial anchor, ~1 quarter test per fold, ~6w val per
  fold** (D-010 added detail); the v1 single 75/15/10 chronological split
  retained as a comparison configuration; `cpcv` scheme value reserved in
  the splits API for Phase C (D-016)
- **Sample-uniqueness weighting** (López de Prado average uniqueness,
  computed on training-fold labels only) layered on top of v1's
  class-imbalance weights, renormalized per fold to sum to `N`; **Kish-N_eff**
  for confidence intervals on test metrics; no time decay (D-005, D-017)
- A `splits.py` module that's the single source of truth for what's train,
  val, and test for every fold
- **Held-out test window reservation** (VISION deferred decision). A
  contiguous block of data is set aside and excluded from every walk-forward
  fold — never touched by CV, scalers, feature selection, or threshold
  optimization. Geometry (length, position — tail vs. interior) and the
  rule for *if and when* it gets evaluated are committed to a new D-NNN
  before Phase E begins. It is touched at most *once*, as a final sanity
  check after the pre-registered success threshold (D-008) is already met
  on the walk-forward; it does not substitute for the threshold itself
- A **pre-registered success threshold** committed in two stages, both
  before any honest-arm metric is computed (VISION line 29):
  **Stage 1 — structure** (end of Phase B, before D begins) locks the
  rule shape — net-of-cost precision above the cost-adjusted breakeven
  with an `N_eff`-based CI excluding it, on **at least 5 of 8** test folds,
  with **[DSR](GLOSSARY.md#deflated-sharpe-ratio-dsr) > 0.95** and
  **PBO < 0.2** (PBO not yet in GLOSSARY — Bailey & López de Prado 2014,
  CSCV).
  **Stage 2 — values** (C/D handoff, before any model is fit in E) locks
  the numbers — the cost-adjusted breakeven once D-011's cost model lands,
  and the `V` source per D-016 (reduced-config CPCV if implemented,
  trial-set estimator over `folds × dual arms × baselines` as the recorded
  fallback). Both stages appended to D-008
- Decision-log entries D-027 … D-033 reflecting the new B-phase choices
  (entry-price convention, intra-bar tie-break, `LabelResult` schema, module
  layout, pATR module location, `label_spans` representation, forward-walk
  vectorization)
- **CI scaffold** (VISION DoD #6 — CI green on every change). A minimal
  GitHub Actions workflow runs `uv sync`, `uv run ruff check .`,
  `uv run mypy src/`, and `uv run pytest` on every push and PR. Lands in
  Phase B because A's test surface was small enough to skip it and F is
  too late — VISION's per-change guarantee needs CI live before the
  leakage-sensitive code paths (labels, splits, weights) merge. Workflow
  file: `.github/workflows/ci.yml`

**Out of scope for this iteration:** CUSUM event filter (D-015 — Rejected; revisit
in a follow-on iteration). CPCV implementation lands in Phase C (D-016).

**Learning component:** read López de Prado **chapters 3 (labeling), 4 (sample weights / uniqueness), and 7 (cross-validation in finance)** before implementing, plus a skim of **chapters 11–12 (backtest overfitting, CSCV/PBO, Deflated Sharpe Ratio)** to inform the success threshold and reporting.
This is the most important learning investment in this iteration.

See `PHASE_B.md` for the full breakdown.

---

## Phase C — Baselines and evaluation harness

**Goal:** Build the evaluation harness against which everything will be measured.
Baselines first, model later — this is the methodology checkpoint.

**Exit criteria:** `evaluate()` runs all four baselines under every probe arm; per-arm parquet schema validated end-to-end on baseline output; D-008 Stage 2 (cost-adjusted breakeven value + `V` source) appended; D-016 CPCV verdict (implement or drop) recorded.

**Key deliverables:**

- Vectorized backtest function: takes signals + prices + cost assumptions,
  returns equity curve and metrics. Fills resolved on **1m** (consistent
  with the primary label arm, D-006); both **gross and net** P&L reported
  (gross lines up with v1, net is the honest number)
- Cost model (D-011): taker fee + slippage cushion sized to sub-1m touch
  ambiguity (v1 had none — gross-only is therefore the v1-faithful arm
  here; gross/net pair retained per the dual-arm catalogue above)
- Metrics module: precision-at-threshold (referenced to the 38.5% breakeven,
  not 50%), profit with costs, max drawdown, Sharpe, Sortino, trade count, win
  rate, average win/loss ratio, **Deflated Sharpe Ratio** (with `N` taken
  from MLflow's configuration log and `V` per D-016 — see CPCV bullet
  below), and **Probability of Backtest Overfitting (PBO) via CSCV** — the
  bar Phase B's pre-registered success criterion (D-008) checks against
- **CPCV (combinatorial purged CV) in reduced configuration** —
  operationalizes D-016. The `scheme="cpcv"` slot reserved in Phase B's
  splits API is wired here. Runs on the four baselines and a *reduced-epoch*
  model only; full-depth CPCV on the deep model is too expensive
  (`C(N, k)/k ×` the training budget). Produces a Sharpe distribution across
  `φ = C(N−1, k−1)` paths, supplying the across-trial variance `V` the DSR
  formula requires (D-008). The headline deep model still reports its
  walk-forward point — CPCV exists to make that point's DSR interpretable.
  **Fallback** (D-016 recorded alternative, if CPCV is dropped on compute
  grounds): `V` estimated from the trial set
  `folds × dual arms × baselines`. The chosen `V` source is committed to
  D-008 before any model is fit in Phase E
- Four baselines implemented and benchmarked:
  - Buy-and-hold
  - Naive direction (predict last move continues)
  - Simple TA rule (e.g., EMA crossover) — sanity check that *something* trades
  - **Frequency-matched random signal** — same trade count as the model, run
    through the same cost model; the real "is there an edge" control
- Baseline numbers logged to MLflow (local file backend), with the same
  label-overlap-aware Kish-`N_eff` CIs (D-005) applied to baseline metrics
  as to model metrics — comparability with VISION DoD #4 requires
  apples-to-apples CIs
- **Per-arm metric record schema** (enables the Phase E headline finding).
  Every metric is emitted as a row
  `(arm_id, fold, metric_name, value, n_eff, ci_lo, ci_hi)`. The four
  leakage-probe arms (D-004 embargo, D-006 barrier resolution, D-010
  geometry, D-013 feature scope) share the honest arm's `metric_name` set,
  so the honest-vs-v1 gap is computed as a join on `(fold, metric_name)`
  rather than a re-derivation. Prevents the gap math from silently
  reweighting or redefining anything.
- A reusable `evaluate(signals, prices, fold, *, arm) -> Metrics` interface;
  `arm` selects which configuration is active across the full dual-arm
  catalogue — **8 leakage probes** (statistical-discipline: D-004
  embargo, D-006 barrier-touch resolution, D-010 walk-forward geometry,
  D-013 feature-selection scope; data-handling: D-036 gap-fill, D-037
  NaN policy, D-038 pATR fill, D-039 cross-TF alignment) plus **2
  retained comparison arms** (D-009 loss function, D-011 cost model
  gross/net). A single call site drives every arm — the runtime form of
  the D-001 governing rule

**Why this comes before the model:** if the harness is wrong, every number that
follows is meaningless. Building it on baselines forces the interface to be
right before the model has any incentive to "make it work."

---

## Phase D — Feature engineering and preprocessing

**Goal:** Reproduce v1's feature pipeline cleanly, with leakage prevention
built in.

**Risk note:** TA library quirks, multi-timeframe alignment, and scaler-fit discipline are all easy to get subtly wrong — budget for surprises here.

**Exit criteria:** v1-shaped feature tensor `(batch, 1, 21, 220)` produced per fold; no-future-leak tests and per-fold scaler-discipline tests green; feature-selection-leakage probe (v1 global vs. per-fold) results recorded.

**Key deliverables:**

- Indicator module: VolumeIndicator, TrendIndicator, VolatilityIndicator,
  MomentumIndicator equivalents, vectorized in Polars or pandas-ta
- Multi-timeframe alignment: 21-step lookback windows for 4h/1h/15m, aligned on
  the 15m decision clock via **backward as-of joins** (a higher-timeframe bar is
  only visible at/after its close; never the forming bar)
- Scaler discipline: MinMaxScaler fit only on the training fold, applied to
  val/test
- Feature selection: Pearson correlation filter (0.95) + MI ranking as in v1,
  but **rerun per fold on training rows only** (honest arm); v1's single global
  selection on 90% of data retained as a **selection-leakage probe** (D-013)
- **Data-handling leakage probes wired into feature assembly**
  (L-008, L-009, L-011). The v1-faithful feature arm additionally
  reproduces *(i)* v1's non-causal `LinearInterpolator` gap fill on
  every input timeframe before indicator compute (D-036, downstream
  side), *(ii)* the blanket `DataMixer.*.load_features` `bfill` on the
  assembled feature frame (D-037), and *(iii)* the
  `DataMixer3._mix_train` counter-walked multi-TF mix (D-039) in place of
  the `merge_asof` join above. The honest arm leaves NaN cells untouched
  and excludes affected rows in the batch sampler
- Sample tensor matching v1's `(batch, 1, 21, 220)` shape
- Tests asserting no future timestamps appear in any training sample's feature
  window
- Comparison against v1 scalers/feature lists where applicable

**The leakage trap to watch:** any indicator that uses a "lookback that includes
the current bar's close" combined with a target that depends on the current
bar's close. Easy to miss, fatal if wrong. (v1's `shift(3)` on higher-timeframe
pATR is the existing guard — keep it.)

---

## Phase E — Model rebuild and training

**Goal:** Rebuild the production `ConvWideDeepLSTMNet` cleanly, train it under
walk-forward CV, evaluate it against baselines under the harness.

**Exit criteria:** D-014 verdict appended; gap artifact written to `reports/gap.parquet`; success-threshold check executed and the verdict (pass / null) recorded; aggregate per-arm metrics logged to MLflow.

**Gate before any model is fit — D-014 ratification.**
Resolve whether this iteration includes meta-labeling. Two paths:

- **Ratified.** Add a binary meta-model for bars where the primary takes a
  position (`ŝ_t ≠ 0`), trained on the **derived** meta-label
  `m_t = 1[ŝ_t = rt3_t]` (was the primary's call correct) — computed at train
  time from `rt3`, *not* read from a v1 `target3` column (which is no longer
  produced; L-006 corrected, L-017). Action threshold = cost-adjusted breakeven
  (D-007); sizing by conviction above breakeven (de Prado's probability→size map,
  recentred on breakeven, not 0.5). Primary tuned for recall, meta-model supplies
  precision.
- **Deferred (follow-on iteration).** No meta-model this iteration. Phase E's
  directional collapse (`rt3 → {long, no-trade, short}` with `0` folded into
  "no-trade") carries the iteration. D-009's loss arms remain the dual-arm.

The verdict is appended to D-014 (Proposed → Accepted or Superseded) and to D-008's Stage 2 commit, before any model is fit.

**Key deliverables:**

- `models/cwdn.py`: the ConvWideDeepLSTMNet architecture, with a clean device
  abstraction (`mps` / `cpu` / `cuda` — MPS for the M4). **MPS reproducibility is
  best-effort**; the canonical `make reproduce` result runs on CPU. Document the
  limit in `LEARNINGS.md`.
- Training loop with deterministic seeds, early stopping, AdamW, and **two loss
  arms**: v1's combined `0.7·MSE + 0.3·MAE` on a scalar output (v1-faithful) and
  a class-weighted **BCE / focal** classifier (honest arm, motivated by the 9.3%
  positive rate). Weights combine class-imbalance × sample-uniqueness.
- Threshold optimization on *validation* folds (not test), referenced to the
  38.5% breakeven
- Per-fold metrics logged to MLflow; aggregate out-of-sample metrics across all
  folds with effective-N confidence intervals and Deflated Sharpe
- Comparison plot: model (both arms) vs. each baseline on the same backtest
- **The honest-vs-v1-faithful gap artifact** — the project's headline
  finding per VISION DoD #5. A table with one row per leakage discipline
  and one column per headline metric (net-of-cost precision-at-threshold,
  net P&L, DSR), grouped into two sub-blocks:
  - *Statistical-discipline probes:* D-004 embargo, D-006 barrier
    resolution, D-010 walk-forward geometry, D-013 feature-selection
    scope.
  - *Data-handling probes:* D-036 gap-fill discipline, D-037
    feature-frame NaN policy, D-038 pATR fill policy, D-039
    cross-timeframe alignment method.

  Each cell holds `v1_faithful − honest` with a label-overlap-aware
  (`N_eff`-based) CI. A second view reports cumulative inflation when
  probes are stacked vs. applied individually — the difference
  distinguishes additive leaks from interacting ones, and the
  cross-block interaction (do data-handling leaks dominate or compound
  the statistical ones?) is the most likely structural finding.
  Stored as `reports/gap.parquet`, joined from the Phase C per-arm schema
  (not recomputed), and rendered in `notebooks/results.ipynb`

**The first moment of truth.** The numbers that come out of this phase are the
project's core finding. They are checked against the success threshold
pre-registered in Phase B.

---

## Phase F — Synthesis and write-up

**Goal:** Lock in findings, polish the repo, ship this iteration.

**Exit criteria:** README leads with the gap artifact; `make reproduce` runs end-to-end from raw data to `reports/gap.parquet`; CI green on every change; DECISIONS.md and LEARNINGS.md complete.

**Key deliverables:**

- README.md: project overview, **honest-vs-v1-faithful gap artifact as the
  headline finding** (VISION DoD #5), full per-arm results table, how to
  reproduce. The gap leads; the absolute honest-arm numbers come second
- DECISIONS.md and LEARNINGS.md complete and readable; the narrative behind
  the gap artifact lives in LEARNINGS.md (VISION DoD #8)
- A `notebooks/results.ipynb` that loads `reports/gap.parquet` and renders
  the gap artifact (per-discipline inflation table and stacked-vs-individual
  view), plus per-arm comparison plots against the four baselines
- `make reproduce` or equivalent: one command that runs the whole pipeline
- Repo cleaned up, dead code removed, tests passing, CI green (if no follow-on
  iteration is yet started, basic GitHub Actions running tests is fine)

---

## Phase X (optional) — Honest ablations

**Goal:** Re-run the v1 ablation study (E0–E6) under the rigorous harness.

**Exit criteria:** comparison table published; conclusions appended to LEARNINGS.md; any design choice that shifts under ablation evidence gets a follow-up DECISIONS.md entry referencing the original.

**When to do this:** only if Phase E produces interesting results *and* you're
still curious. Skip if the model fails honestly — there's nothing to ablate.
This is also an excellent follow-on-iteration candidate, since by then re-running
experiments is cheap.

**Key deliverables:**

- Each E* experiment from v1 rerun with the new harness
- Comparison table: v1 reported number vs. honest number vs. baseline
- Conclusions: which design choices actually matter
- All findings (including null results) appended to LEARNINGS.md; the
  ablation loop closes back into DECISIONS.md when evidence revises an
  earlier choice

---

## Sequencing rules

- Phases A → B → C → D → E → F are mostly sequential. Some overlap is fine
  (e.g., learning Polars during Phase A while reading Lopez de Prado for Phase B).
- **C must complete before E.** Never train a model before the evaluation
  harness is trusted.
- **B must complete before D.** Splits must be locked before any fitting
  (including scalers and feature selection in D) touches data.
- **The success threshold must be pre-registered (Phase B) before E begins.**
- If a phase grows substantially beyond its listed deliverables, stop and
  reassess scope before continuing. Update DECISIONS.md with what you cut
  or added and why.

## What lives where

- `VISION.md` — this file's sibling. Rarely changes.
- `PLAN.md` — this file. Updated when scope changes; superseded by
  follow-on-iteration plans when this iteration completes.
- `PHASE_A.md`, `PHASE_B.md`, … — per-phase breakdowns, written just ahead of
  starting each phase.
- `DECISIONS.md` — append-only log of design decisions. Updated in the same
  commit as the code implementing the decision. Each entry records the verdict,
  the rationale, and the v1 alternative.
- `LEARNINGS.md` — append-only log of findings, surprises, bugs, dead ends.
- `CLAUDE.md` — repo root, picked up by Claude Code. Project conventions,
  hard rules (never random-split time series, always walk-forward, etc.).
