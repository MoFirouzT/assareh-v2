# Assareh-v2 — Layer 1 Plan

This document covers Layer 1: the research + learning phase.
Layer 2 (ML engineering polish) and Layer 3 (optional live system) are planned later, once
Layer 1 produces results worth engineering around.

---

## Dual-arm methodology (cross-cutting)

The single most important methodological commitment in Layer 1, applied from
Phase B onward.
Every place where v1 made a choice that we want to improve on, we keep **both**:

- **v1-faithful arm** — reproduces the v1 decision exactly, so any comparison
  against v1's reported numbers is valid.
- **Honest arm** — the methodologically correct version, which is the primary
  result of the project.

Both arms run through the **same** harness (Phase C).
The number we trust is the honest arm; the number we report *alongside* it is the v1-faithful arm; and the **gap between them is a finding** — it quantifies how much of v1's apparent edge was leakage, optimistic fills, or selection bias rather than signal.

Four decisions resolve to a deliberate **leakage probe** rather than two co-existing options, because the v1 choice is a defect, not a design:
embargo, barrier-touch resolution, walk-forward geometry, and feature-selection scope.
For these, the honest arm is primary and the v1 configuration is run *once* to measure the inflation, then retired.
See `DECISIONS.md` for the governing rules.

---

## Phase A — Foundation: data, repo, environment

**Goal:**
Have a clean repo, a reproducible environment, and validated raw data on disk.
No modeling yet.

**Key deliverables:**

- Repo skeleton with `pyproject.toml` (uv-managed), `CLAUDE.md`, `VISION.md`,
  `DECISIONS.md`, `LEARNINGS.md`, `README.md` stub
- Raw OHLCV data for BTC/USDT (4h, 1h, 15m, 1m) downloaded from Binance, with checksum verification.
1m is a first-class timeframe and the substrate for barrier-touch resolution in Phase B.
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

**Key deliverables:**

- Triple-barrier target function (pATR-based, three-class `-1/0/+1`, 511-bar
  horizon, matching v1 semantics) with tests — **1m-resolved barrier ordering
  primary**, 15m-optimistic ordering retained as the v1-faithful comparison arm
- Documented target statistics:
positive rate, **timeout (no-touch) rate**, distribution over time, regime shifts; the **38.5% breakeven reference** written down explicitly
- Walk-forward CV scheme implemented and tested, with **purging + embargo (embargo ≥ 511 bars, the full label horizon)**;
the v1 single 75/15/10 chronological split retained as a comparison configuration
- **Sample-uniqueness weighting** (López de Prado average uniqueness) layered on top of v1's class-imbalance weights, plus an **effective-N adjustment** for confidence intervals on test metrics
- A `splits.py` module that's the single source of truth for what's train, val, and test for every fold
- A **pre-registered success threshold** committed before any model is trained
- Decision-log entries explaining target, no-touch handling, horizon, embargo, uniqueness, fold count, and the pre-registered bar

**Learning component:** ~8 hours reading López de Prado **chapters 3 (labeling), 4 (sample weights / uniqueness), and 7 (cross-validation in finance)** before implementing, plus a skim of **chapters 11–12 (backtest overfitting, CSCV/PBO, Deflated Sharpe Ratio)** to inform the success threshold and reporting.
This is the most important learning investment in Layer 1.

See `PHASE_B.md` for the full breakdown.

---

## Phase C — Baselines and evaluation harness

**Goal:** Build the evaluation harness against which everything will be measured.
Baselines first, model later — this is the methodology checkpoint.

**Key deliverables:**

- Vectorized backtest function: takes signals + prices + cost assumptions,
  returns equity curve and metrics. Fills resolved on **1m** (consistent with the
  primary label arm); both **gross and net** P&L reported (gross lines up with
  v1, net is the honest number)
- Cost model: taker fee + slippage cushion sized to sub-1m touch ambiguity
  (v1 had none — gross-only is therefore the v1-faithful arm here)
- Metrics module: precision-at-threshold (referenced to the 38.5% breakeven,
  not 50%), profit with costs, max drawdown, Sharpe, Sortino, trade count, win
  rate, average win/loss ratio, and **Deflated Sharpe Ratio**
- Four baselines implemented and benchmarked:
  - Buy-and-hold
  - Naive direction (predict last move continues)
  - Simple TA rule (e.g., EMA crossover) — sanity check that *something* trades
  - **Frequency-matched random signal** — same trade count as the model, run
    through the same cost model; the real "is there an edge" control
- Baseline numbers logged to MLflow (local file backend)
- A reusable `evaluate(signals, prices, fold) -> Metrics` interface

**Why this comes before the model:** if the harness is wrong, every number that
follows is meaningless. Building it on baselines forces the interface to be
right before the model has any incentive to "make it work."

---

## Phase D — Feature engineering and preprocessing

**Goal:** Reproduce v1's feature pipeline cleanly, with leakage prevention
built in.

**Estimate:** 14–22 hours (⚠ high-variance — TA library, multi-timeframe
alignment, scaler-fit discipline are all easy to get subtly wrong)

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
  selection on 90% of data retained as a **selection-leakage probe**
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
- The **honest-vs-v1-faithful gap table**: for embargo, barrier resolution,
  geometry, and feature scope, the inflation each contributed

**The first moment of truth.** The numbers that come out of this phase are the
project's core finding. They are checked against the success threshold
pre-registered in Phase B.

---

## Phase F — Synthesis and write-up

**Goal:** Lock in findings, polish the repo, ship Layer 1.

**Key deliverables:**

- README.md: project overview, headline findings, how to reproduce
- DECISIONS.md and LEARNINGS.md complete and readable
- A `notebooks/results.ipynb` with the final comparison plots and analysis,
  including the honest-vs-v1-faithful gap
- `make reproduce` or equivalent: one command that runs the whole pipeline
- Repo cleaned up, dead code removed, tests passing, CI green (if Layer 2 not
  yet started, basic GitHub Actions running tests is fine)

---

## Phase X (optional) — Honest ablations

**Goal:** Re-run the v1 ablation study (E0–E6) under the rigorous harness.

**When to do this:** only if Phase E produces interesting results *and* you're
still curious. Skip if the model fails honestly — there's nothing to ablate.
This is also an excellent Layer 2 candidate, since by then re-running
experiments is cheap.

**Key deliverables:**

- Each E* experiment from v1 rerun with the new harness
- Comparison table: v1 reported number vs. honest number vs. baseline
- Conclusions: which design choices actually matter

---

## Sequencing rules

- Phases A → B → C → D → E → F are mostly sequential. Some overlap is fine
  (e.g., learning Polars during Phase A while reading Lopez de Prado for Phase B).
- **C must complete before E.** Never train a model before the evaluation
  harness is trusted.
- **B must complete before D.** Splits must be locked before any fitting
  (including scalers and feature selection in D) touches data.
- **The success threshold must be pre-registered (Phase B) before E begins.**
- If a phase blows past its upper bound by more than 50%, stop and reassess
  scope before continuing. Update DECISIONS.md with what you cut and why.

## What lives where

- `VISION.md` — this file's sibling. Rarely changes.
- `PLAN.md` — this file. Updated when scope changes; superseded by Layer 2/3
  plans when Layer 1 completes.
- `PHASE_A.md`, `PHASE_B.md`, … — per-phase breakdowns, written just ahead of
  starting each phase.
- `DECISIONS.md` — append-only log of design decisions. Updated in the same
  commit as the code implementing the decision. Each entry records the verdict,
  the rationale, and the v1 alternative.
- `LEARNINGS.md` — append-only log of findings, surprises, bugs, dead ends.
- `CLAUDE.md` — repo root, picked up by Claude Code. Project conventions,
  hard rules (never random-split time series, always walk-forward, etc.).
