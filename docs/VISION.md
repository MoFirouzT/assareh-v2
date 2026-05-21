# Assareh-v2 — Vision

## What this project is

A restart of an earlier exploration into Bitcoin price-direction prediction using
a **path-dependent binary target** (does price hit a profit level before a stop
level?) and **multi-timeframe inputs** (4h / 1h / 15m / 1m).

The earlier iteration of Assareh produced a working research pipeline, a
production Django/Celery service, and promising-looking accuracy numbers. This
restart builds on those ideas with sharper methodology, modern tooling, and
rigorous evaluation — and treats prior results as **hypotheses to validate**
rather than baselines to reproduce.

## Core hypothesis

A model trained on technical indicators across multiple timeframes can predict,
better than naive baselines, whether BTC will hit a 4×PATR profit target before
a 2.5×PATR stop-loss within a defined horizon.

Whether this hypothesis holds under honest evaluation is the central question
of the project.

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
  a methodology trail.
- **Depth over breadth.** One model rebuilt properly, evaluated rigorously,
  fully understood. Ablations are optional, not central.
- **80/20 throughout — except where it kills credibility.** Backtest design,
  split discipline, and leakage prevention get full rigor. Hyperparameter
  search, exotic architectures, and infrastructure theater do not.
- **Decisions are documented as they're made.** `DECISIONS.md` is updated in
  the same commit as the code that implements the decision.

## Scope

**In scope (Layer 1):**

- BTC/USDT only
- 4h / 1h / 15m / 1m timeframes
- The production v1 architecture (`ConvWideDeepLSTMNet`) as the rebuild target
- Walk-forward backtest with transaction costs
- Comparison against baselines (buy-and-hold, naive direction, simple TA rule)
- Comparison against v1 artifacts where the comparison is methodologically valid

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
   metrics on out-of-sample data.
3. The rebuilt v1 model, evaluated under that harness.
4. A comparison against at least three baselines.
5. `DECISIONS.md` capturing every meaningful choice and its rationale.
6. `LEARNINGS.md` capturing what was discovered along the way.
7. A `README.md` that explains the project, the findings, and how to reproduce
   them.

What "the findings" turn out to be is not part of the definition of done.
The methodology is.

## Naming

This project is **Assareh v2**, after my friend whose ideas seeded v1. The v1
codebase is referenced as "v1" or "prior work" throughout.