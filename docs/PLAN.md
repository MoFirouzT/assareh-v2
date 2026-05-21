# Assareh-v2 — Layer 1 Plan

This document covers Layer 1: the research + learning phase. Layer 2 (ML
engineering polish) and Layer 3 (optional live system) are planned later, once
Layer 1 produces results worth engineering around.

Hour estimates are ranges. Lower bound: things go smoothly. Upper bound:
reasonable friction. Steps flagged ⚠ are **high-variance** — they can blow
past the upper bound depending on what's found.

---

## Phase A — Foundation: data, repo, environment

**Goal:** Have a clean repo, a reproducible environment, and validated raw data
on disk. No modeling yet.

**Estimate:** 8–14 hours

**Key deliverables:**
- Repo skeleton with `pyproject.toml` (uv-managed), `CLAUDE.md`, `VISION.md`,
  `DECISIONS.md`, `LEARNINGS.md`, `README.md` stub
- Raw OHLCV data for BTC/USDT (4h, 1h, 15m, 1m) downloaded from Binance,
  validated against v1 artifacts where dates overlap
- Data integrity checks: no duplicates, no gaps unaccounted for, timezone
  consistent, schema documented
- A Polars-based data loader with tests

**What's deliberately deferred:** feature engineering, target definition,
indicators. All of that is Phase B and later.

---

## Phase B — Target definition and split design

**Goal:** Define the prediction target rigorously, design train/val/test splits
that respect the temporal structure, and lock in the evaluation harness skeleton
*before* writing any model.

**Estimate:** 12–18 hours (⚠ high-variance — depends on how deep you go on CV theory)

**Key deliverables:**
- Path-dependent target function (PATR-based, matching v1 semantics) with tests
- Documented target statistics: positive rate, distribution over time, regime
  shifts
- Walk-forward CV scheme implemented and tested (with purging + embargo)
- A `splits.py` module that's the single source of truth for what's train,
  val, and test for every fold
- Decision log entry explaining split choices, embargo size, fold count

**Learning component:** ~6 hours reading Lopez de Prado chapters 4 and 7 before
implementing. This is the most important learning investment in Layer 1.

---

## Phase C — Baselines and evaluation harness

**Goal:** Build the evaluation harness against which everything will be measured.
Baselines first, model later — this is the methodology checkpoint.

**Estimate:** 10–14 hours

**Key deliverables:**
- Vectorized backtest function: takes signals + prices + cost assumptions,
  returns equity curve and metrics
- Metrics module: precision-at-threshold, profit with costs, max drawdown,
  Sharpe, Sortino, trade count, win rate, average win/loss ratio
- Three baselines implemented and benchmarked:
  - Buy-and-hold
  - Naive direction (predict last move continues)
  - Simple TA rule (e.g., EMA crossover) — sanity check that *something* trades
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
- Multi-timeframe alignment: 21-step lookback windows for 4h/1h/15m, aligned
  on common timestamps with no future bleed
- Scaler discipline: MinMaxScaler fit only on training fold, applied to val/test
- Feature selection: Pearson correlation filter as in v1, but rerun honestly
  per fold (not globally)
- Sample tensor matching v1's `(batch, 1, 21, 220)` shape
- Tests asserting no future timestamps appear in any training sample's feature
  window
- Comparison against v1 scalers/feature lists where applicable

**The leakage trap to watch:** any indicator that uses a "lookback that includes
the current bar's close" combined with a target that depends on the current
bar's close. Easy to miss, fatal if wrong.

---

## Phase E — Model rebuild and training

**Goal:** Rebuild the production `ConvWideDeepLSTMNet` cleanly, train it under
walk-forward CV, evaluate it against baselines under the harness.

**Estimate:** 14–20 hours

**Key deliverables:**
- `models/cwdn.py`: the ConvWideDeepLSTMNet architecture, with a clean device
  abstraction (`mps` / `cpu` / `cuda` — MPS for your M4)
- Training loop with deterministic seeds, early stopping, AdamW, combined
  MSE+MAE loss (matching v1 to enable comparison)
- Threshold optimization on *validation* folds (not test)
- Per-fold metrics logged to MLflow
- Aggregate out-of-sample metrics across all folds
- Comparison plot: model vs. each baseline on the same backtest

**The first moment of truth.** The numbers that come out of this phase are the
project's core finding.

---

## Phase F — Synthesis and write-up

**Goal:** Lock in findings, polish the repo, ship Layer 1.

**Estimate:** 6–10 hours

**Key deliverables:**
- README.md: project overview, headline findings, how to reproduce
- DECISIONS.md and LEARNINGS.md complete and readable
- A `notebooks/results.ipynb` with the final comparison plots and analysis
- `make reproduce` or equivalent: one command that runs the whole pipeline
- Repo cleaned up, dead code removed, tests passing, CI green (if Layer 2 not
  yet started, basic GitHub Actions running tests is fine)

---

## Phase X (optional) — Honest ablations

**Goal:** Re-run the v1 ablation study (E0–E6) under the rigorous harness.

**Estimate:** 10–16 hours

**When to do this:** only if Phase E produces interesting results *and* you're
still curious. Skip if the model fails honestly — there's nothing to ablate.
This is also an excellent Layer 2 candidate, since by then re-running
experiments is cheap.

**Key deliverables:**
- Each E* experiment from v1 rerun with the new harness
- Comparison table: v1 reported number vs. honest number vs. baseline
- Conclusions: which design choices actually matter

---

## Totals

| Phase | Range (hours) |
|---|---|
| A — Foundation | 8–14 |
| B — Target & splits | 12–18 |
| C — Baselines & harness | 10–14 |
| D — Features | 14–22 |
| E — Model | 14–20 |
| F — Synthesis | 6–10 |
| **Layer 1 total** | **64–98** |
| X — Ablations (optional) | 10–16 |

At 10 hours/week, Layer 1 lands in 7–10 weeks. At 4 hours/week, ~16–24 weeks.

## Sequencing rules

- Phases A → B → C → D → E → F are mostly sequential. Some overlap is fine
  (e.g., learning Polars during Phase A while reading Lopez de Prado for Phase B).
- **C must complete before E.** Never train a model before the evaluation
  harness is trusted.
- **B must complete before D.** Splits must be locked before any fitting
  (including scalers in D) touches data.
- If a phase blows past its upper bound by more than 50%, stop and reassess
  scope before continuing. Update DECISIONS.md with what you cut and why.

## What lives where

- `VISION.md` — this file's sibling. Rarely changes.
- `PLAN.md` — this file. Updated when scope changes; superseded by Layer 2/3
  plans when Layer 1 completes.
- `DECISIONS.md` — append-only log of design decisions. Updated in the same
  commit as the code implementing the decision.
- `LEARNINGS.md` — append-only log of findings, surprises, bugs, dead ends.
- `CLAUDE.md` — repo root, picked up by Claude Code. Project conventions,
  hard rules (never random-split time series, always walk-forward, etc.).