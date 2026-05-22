# Assareh-v2 — Vision

## What this project is

A restart of an earlier exploration into Bitcoin price-direction prediction using
a **path-dependent triple-barrier target** (does price hit a profit level before a
stop level, within a horizon?) and **multi-timeframe inputs** (4h / 1h / 15m / 1m).

The earlier iteration of Assareh produced a working research pipeline, a
production Django/Celery service, and promising-looking accuracy numbers. This
restart builds on those ideas with sharper methodology, modern tooling, and
rigorous evaluation — and treats prior results as **hypotheses to validate**
rather than baselines to reproduce.

## Core hypothesis

A model trained on technical indicators across multiple timeframes can predict,
better than naive baselines, whether BTC will hit a 4×pATR profit target before
a 2.5×pATR stop-loss within a defined horizon (~5.3 days at the 15m decision
cadence inherited from v1).

The target is the v1 three-class scheme (`-1` short / `0` no-touch / `+1` long),
collapsed to a directional signal for headline reporting. Whether the hypothesis
holds under honest evaluation is the central question of the project.

## Why this project (for me)

In layers:

1. **Learn.** Time-series cross-validation, financial evaluation, MLOps tooling,
   Polars — by doing the thing, not by tutorials.
2. **Research.** Find out what's actually true about the v1 hypothesis.
3. **ML engineering signal.** Produce a codebase a senior engineer would respect
   — typed config, walk-forward backtest harness, tests, reproducibility, CI.
4. **(Optional) Live system.** If results justify it, a lean inference loop that
   paper-trades. No Django, no Celery, no DB wipes.

Each layer is a coherent checkpoint. The project succeeds at any layer.

## North star principles

- **Honesty over results.** A real 53% beats a leaked 86%. Every number gets
  a methodology trail. The reference bar is the **payoff-implied breakeven rate
  (38.5% pre-cost for a 4 : 2.5 reward:risk)**, never an implicit 50%.
- **Reproduce faithfully, improve transparently.** Every meaningful v1 choice is
  preserved as a runnable **comparison arm**; the project's improvements form the
  **primary arm**. Where the two cannot coexist, the primary arm wins and the v1
  alternative is recorded (and, where it isolates a leak, run deliberately to
  *measure* the inflation). The gap between the v1-faithful arm and the honest arm
  is itself a finding — see "Dual-arm methodology" in `PLAN.md`.
- **Depth over breadth.** One model rebuilt properly, evaluated rigorously,
  fully understood. Ablations are optional, not central.
- **80/20 throughout — except where it kills credibility.** Backtest design,
  split discipline, label-overlap handling, and leakage prevention get full
  rigor. Hyperparameter search, exotic architectures, and infrastructure theater
  do not.
- **Decisions are documented as they're made.** `DECISIONS.md` is updated in
  the same commit as the code that implements the decision.

## Scope

**In scope (Layer 1):**

- BTC/USDT only
- 4h / 1h / 15m / 1m timeframes (15m is the decision clock; 1m is the
  barrier-resolution substrate; 4h/1h are auxiliary feature inputs)
- The production v1 architecture (`ConvWideDeepLSTMNet`) as the rebuild target
- Walk-forward backtest with transaction costs
- Comparison against baselines (buy-and-hold, naive direction, simple TA rule,
  frequency-matched random signal)
- Comparison against v1 artifacts where the comparison is methodologically valid
  (the v1-faithful arm)

**Explicitly out of scope (Layer 1):**

- Other assets (the v1 `Available data.ipynb` lists 8 — they wait for later)
- Hyperparameter optimization beyond a sane manual sweep
- Ensembling beyond what v1 already explored
- Deep architecture search
- Any deployment or production concerns
- The full v1 ablation study (E0–E6) — optional stretch in Phase X

## Definition of done for Layer 1

A repo containing:

1. A reproducible pipeline from raw data to backtest results, runnable with a
   single command.
2. A walk-forward backtest harness with transaction costs, returning honest
   metrics on out-of-sample data, with confidence intervals that respect the
   reduced effective sample size from overlapping labels.
3. The rebuilt v1 model, evaluated under that harness, in both a v1-faithful and
   an honest configuration.
4. A comparison against at least four baselines.
5. `DECISIONS.md` capturing every meaningful choice, its rationale, and the
   recorded v1 alternative.
6. `LEARNINGS.md` capturing what was discovered along the way — including the
   measured gap between the v1-faithful and honest arms.
7. A `README.md` that explains the project, the findings, and how to reproduce
   them.

What "the findings" turn out to be is not part of the definition of done.
The methodology is.

## Naming

This project is **Assareh v2**, after my friend whose ideas seeded v1. The v1
codebase is referenced as "v1" or "prior work" throughout.
