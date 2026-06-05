# Assareh-v2 — Vision

## What this project is

Assareh-v2 is a methodology-focused portfolio project: a second attempt at
predicting Bitcoin price-direction using a **path-dependent triple-barrier
target** (does price hit a profit level before a stop level, within a horizon?)
and **multi-timeframe inputs** (4h / 1h / 15m / 1m).

The deliverable is a reproducible research pipeline, a walk-forward backtest
harness, and an evaluation report comparing a v1-faithful arm against an
honest arm — with the gap between them treated as a finding.

The starting point is an earlier iteration of Assareh ("v1") — a research
pipeline, a Django/Celery production service, and reported accuracy results.
This restart builds on v1's ideas and treats those results as **hypotheses to
validate** rather than baselines to reproduce.

## Core hypothesis

Whether a model trained on technical indicators across multiple timeframes can
predict, at a hit-rate above the payoff-implied breakeven (≈38.5% pre-cost for a
4 : 2.5 reward:risk), whether BTC will hit a 4×pATR profit target before a
2.5×pATR stop-loss within a horizon of ~510 bars at the 15m decision cadence
inherited from v1 (≈5.3 days) — by a margin that survives honest evaluation,
label-overlap-aware confidence intervals, and transaction costs.

`pATR` = **percent ATR** — a price-normalized (ratio) form of the Average
True Range, scale-invariant across price regimes. The precise definition and
computation are locked in D-012 and implemented in Phase B (B.0).

The target is the v1 three-class scheme (`-1` short / `0` no-touch / `+1` long),
collapsed to a directional signal for headline reporting.

The specific "meaningful edge" threshold (effect size, CI width, post-cost
adjustment) will be **fixed and recorded in `DECISIONS.md` before any honest-arm
metrics are computed**, to prevent post-hoc target adjustment.
Until then, the honest answer to "how much better than baseline counts as success?"
is: *we will decide, on the record, before we know*.

Whether the hypothesis holds under honest evaluation is the central question of the project.

## Why this project

In ambitions:

1. **Learn.** Time-series cross-validation, financial evaluation, MLOps tooling.
2. **Research.** Find out what's actually true about the v1 hypothesis.
3. **ML engineering signal.** Produce a codebase a senior engineer would respect
   — typed config, walk-forward backtest harness, tests, reproducibility, CI.
4. **(Optional) Live system.** If results justify it, a lean inference loop that
   paper-trades.
   No Django, no Celery, no DB wipes.

Each ambition is a coherent checkpoint. The project succeeds at any ambition.

## North star principles

- **Honesty over results.**
A real 53% beats a leaked 86%.
Every number gets a methodology trail.
The reference bar is the **payoff-implied breakeven rate (38.5% pre-cost for a 4 : 2.5 reward:risk)**, never an implicit 50%.
- **Reproduce faithfully, improve transparently.**
Every meaningful v1 choice is preserved as a runnable **comparison arm**.
The project's improvements form the **primary arm**.
Where the two cannot coexist, the primary arm wins and the v1 alternative is recorded (and, where it isolates a leak, run deliberately to *measure* the inflation).
The gap between the v1-faithful arm and the honest arm is itself a finding — see "Dual-arm methodology" in `PLAN.md`.
Concretely, the honest arm differs from the v1-faithful arm in (at minimum): purged/embargoed walk-forward, no future-looking feature engineering, label-overlap-aware confidence intervals, and post-cost evaluation.
The v1-faithful arm intentionally retains v1's choices on each.
- **A null result is a successful outcome.**
If no edge survives honest evaluation, that finding — documented with the methodology trail that produced it — fulfills the research ambition.
This is the most important guard against motivated reasoning.
- **Depth over breadth.**
One model rebuilt properly, evaluated rigorously, fully understood.
Ablations are optional, not central.
Alternate architectures require a written rationale in `DECISIONS.md` before work starts.
- **80/20 throughout — except where it kills credibility.**
Backtest design, split discipline, label-overlap handling, and leakage prevention get full rigor.
Hyperparameter search, exotic architectures, and infrastructure theater do not.
- **Decisions are documented as they're made.**
`DECISIONS.md` is updated along the project advancement.

## Scope

**In scope (Ambitions 1–3):**

- BTC/USDT only
- 4h / 1h / 15m / 1m timeframes
(15m is the decision clock; 1m is the barrier-resolution substrate; 4h/1h are auxiliary feature inputs)
- The production v1 architecture (`ConvWideDeepLSTMNet`) as the rebuild target
- Walk-forward backtest with transaction costs
- Comparison against baselines (buy-and-hold, naive direction, simple TA rule,
  frequency-matched random signal)

**Explicitly out of scope (Ambitions 1–3):**

- Other assets (the v1 lists 8 — they wait for later)
- Hyperparameter optimization beyond a sane manual sweep
- Ensembling beyond what v1 already explored
- Deep architecture search
- Any deployment or production concerns
- The full v1 ablation study (E0–E6) — optional stretch in Phase X

**Deferred decisions (recorded in `DECISIONS.md` when made):**

- Held-out test window — set before honest-arm evaluation.
- Transaction-cost model (fee assumption, slippage model, spread treatment) — set before honest-arm evaluation; sensitivity reported.
- Pre-registered "meaningful edge" threshold — set before any honest-arm metrics are computed.

## Definition of done (Ambitions 1–3)

Per-ambition DoDs live in `PLAN.md`. The list below covers Ambitions 1–3 of the *Why this project* section — the optional live system (Ambition 4) has its own DoD if it's pursued.

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
   measured gap between the v1-faithful and honest arms, broken down by which
   methodological discipline closes which portion of it.
7. A `README.md` that explains the project, the findings, and how to reproduce
   them.

What "the findings" turn out to be is not part of the definition of done.
The methodology is.

## Naming

This project is **Assareh v2**, after my friend whose ideas seeded v1.
The v1 codebase is referenced as "v1" or "prior work" throughout.
