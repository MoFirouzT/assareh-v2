# Assareh-v2 — Vision

## What this project is

Assareh-v2 is a methodology-focused portfolio project:
a second attempt at predicting Bitcoin price-direction using a **path-dependent triple-barrier target**
(does price hit a profit level before a stop level, within a horizon?)
and **multi-timeframe inputs** (4h / 1h / 15m / 1m).

The deliverable is a reproducible research pipeline, a walk-forward backtest harness, and an evaluation report comparing a v1-faithful arm against an honest arm — with the gap between them treated as a finding.

The starting point is an earlier iteration of Assareh ("v1") —
a research pipeline, a Django/Celery production service, and reported accuracy results.
This restart builds on v1's ideas and treats those results as **hypotheses to validate** rather than baselines to reproduce.

## Core hypothesis

Whether a model trained on technical indicators across multiple timeframes can predict, at a hit-rate above the payoff-implied breakeven
(≈38.5% pre-cost for a 4 : 2.5 reward:risk),
whether BTC will hit a 4×pATR profit target before a 2.5×pATR stop-loss within a horizon of ~510 bars at the 15m decision cadence inherited from v1 (≈5.3 days) —
by a margin that survives honest evaluation, label-overlap-aware confidence intervals, and transaction costs.

`pATR` = **percent ATR** —
a price-normalized (ratio) form of the Average True Range, scale-invariant across price regimes.
The precise definition and computation are locked in [D-012](DECISIONS.md#d-012--patr-definition-lock) and implemented in Phase B (B.0).

The target is the v1 three-class scheme (`-1` short / `0` no-touch / `+1` long), collapsed to a directional signal for headline reporting.

The specific "meaningful edge" threshold (effect size, confidence-interval (CI) width, post-cost adjustment) will be **fixed and recorded in `DECISIONS.md` before any honest-arm metrics are computed**, to prevent post-hoc target adjustment.
Until then, the honest answer to "how much better than baseline counts as success?" is: *we will decide, on the record, before we know*.

Whether the hypothesis holds under honest evaluation is the central question of the project.

## Why this project

In ambitions:

1. **Learn.** This project is the curriculum for three skill areas:
   - **time-series methodology** (walk-forward CV, purging, embargo, label-overlap-aware confidence intervals, leakage discipline);
   - **financial evaluation** (payoff-implied breakeven, dual-arm comparison, cost-aware metrics, Sharpe / DSR / drawdown vocabulary);
   - **modern Python + MLOps** (Polars, typed configuration, reproducible experiment tracking, walk-forward backtest harness, CI).

   Building rigorously *is* the curriculum — the other ambitions are downstream of doing this part well.
2. **Honest verdict.** Reach a methodologically defended answer on whether the v1 design has a real edge under leakage-aware evaluation.
   Where evidence shows a v1 choice is a problem, improve it; where there is a credible reason to expect a small, targeted variation could do better, run it as an honest-arm variant and let the harness — not the hunch — decide; otherwise, defer to v1's design.
   The methodology trail underwrites the verdict, the variations, and any improvements that earn adoption.
3. **ML engineering signal.** Produce the artifact that makes the honest verdict (Ambition 2) defensible to a third-party reviewer.
   Every load-bearing claim is traceable to code, every meaningful choice to `DECISIONS.md`, every surprise to `LEARNINGS.md`.
   Typed configuration, single-command reproducibility, tests on the leakage-sensitive paths (label construction, split discipline, scaler scope), CI green on every change, and the dual-arm methodology encoded as runnable comparisons rather than rhetorical claims.
   The bar: a senior engineer reading the repo cold can locate the load-bearing decisions and trust the numbers.
4. **(Optional) Live system.** Gated on Ambition 2 returning a positive verdict ([D-008](DECISIONS.md#d-008--success-threshold-pre-registration)'s pre-registered threshold is met).
   If so: a lean paper-trading loop — single-process, single-module, no orchestration layer, no database — that pulls live OHLCV, runs the trained model, and logs simulated decisions (no real money) to disk.
   Success = the loop runs continuously for an agreed window without crashing or silent drift, with every decision reproducible from the logged inputs.
   **No Django, no Celery, no DB wipes** — the v1 production complexity is a deliberate non-goal.

Together they form a chain:
the curriculum (1) produces the verdict (2); the artifact (3) makes the verdict defensible to anyone else; the live loop (4) is the optional consequence if the verdict is positive.

## North star principles

- **Honesty over results.**
A real 53% beats a leaked 86%.
Every number gets a methodology trail.
The reference bar is the **payoff-implied breakeven rate (38.5% pre-cost for a 4 : 2.5 reward:risk)**, never an implicit 50%.
- **Methodology is the artifact; the result is a byproduct.**
The deliverable is a defensible methodology — the actual finding (edge / no edge / partial edge) is whatever the methodology produces.
A robust pipeline that returns "no edge" is more valuable than an unrepeatable pipeline that returns "53%."
- **Reproduce faithfully, improve transparently.**
Every meaningful v1 choice is preserved as a runnable **comparison arm**; the project's improvements form the **primary arm**; the gap between them is itself a finding.
The mechanism — and the specific disciplines the honest arm enforces (purged/embargoed walk-forward, no future-looking feature engineering, label-overlap-aware confidence intervals, post-cost evaluation) — lives in `PLAN.md`.
- **A null result is a successful outcome.**
If no edge survives honest evaluation, that finding — documented with the methodology trail that produced it — fulfills the honest-verdict ambition.
This is the most important guard against motivated reasoning.
- **Depth over breadth.**
One model rebuilt properly, evaluated rigorously, fully understood.
Ablations are optional, not central.
Alternate architectures require a written rationale in `DECISIONS.md` before work starts.
- **80/20 throughout — except where it kills credibility.**
Backtest design, split discipline, label-overlap handling, and leakage prevention get full rigor.
Hyperparameter search, exotic architectures, and infrastructure theater do not.
- **Decisions are documented as they're made.**
Not reconstructed afterward — reconstruction lets the author rationalize the path taken, which is how the methodology trail gets quietly corrupted.
`DECISIONS.md` is updated as the code implements the decision.

## Scope

**In scope (Ambitions 1–3):**

- BTC/USDT only
- 4h / 1h / 15m / 1m timeframes
(15m is the decision clock; 1m is the barrier-resolution substrate; 4h/1h are auxiliary feature inputs)
- The production v1 architecture (`ConvWideDeepLSTMNet`) as the rebuild target
- Walk-forward backtest with transaction costs
- **Dual-arm methodology** — every meaningful v1 choice runs as a comparison arm alongside the honest-arm primary, evaluated under the same harness (mechanism in `PLAN.md`)
- Comparison against baselines (buy-and-hold, naive direction, simple TA rule,
  frequency-matched random signal)

**Explicitly out of scope (Ambitions 1–3):**

- Other assets (the v1 lists 8 — they wait for later)
- Hyperparameter optimization beyond a sane manual sweep
- Ensembling beyond what v1 already explored
- Deep architecture search
- Deployment or production infrastructure (the optional Ambition-4 paper-trading loop is a research artifact, not a production deployment)
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
5. The **honest-vs-v1-faithful gap artifact** — a table or plot showing how
   much of v1's apparent edge each methodological discipline (purging, embargo,
   walk-forward geometry, feature-selection scope) closed. This is the
   project's headline finding.
6. Tests on the leakage-sensitive paths (label construction, split discipline,
   scaler scope) and CI green on every change.
7. `DECISIONS.md` capturing every meaningful choice, its rationale, and the
   recorded v1 alternative — including each deferred decision (held-out
   window, cost model, success threshold) recorded **before** any honest-arm
   metric was reported.
8. `LEARNINGS.md` capturing what was discovered along the way — including the
   narrative behind the gap artifact (item 5) and other findings, surprises,
   and dead ends.
9. A `README.md` that explains the project, the findings, and how to reproduce
   them.

## Naming

This project is **Assareh v2**, after my friend whose ideas seeded v1.
The v1 codebase is referenced as "v1" or "prior work" throughout.
