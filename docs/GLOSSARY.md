# Assareh-v2 — Glossary

Project-specific terminology and definitions.

**This file is reference material only.** Every "we chose X over Y" lives in
`DECISIONS.md`; every "X surprised us in this way" lives in `LEARNINGS.md`;
this file just says "X is Y." When a glossary entry is governed by a
decision, it cross-references the relevant `D-NNN`.

Scope of this initial version: triple-barrier labelling, the pATR family,
and evaluation/sample geometry. Project-arms vocabulary (`v1-faithful arm`,
`honest arm`, etc.) and v1 artifact names will be added in a later pass.

## Index

**Triple-barrier labelling.**
[First-touch resolution](#first-touch-resolution-1m-vs-15m) ·
[Horizon barrier](#horizon-barrier) ·
[Profit barrier](#profit-barrier) ·
[`rt3`](#rt3) ·
[Stop barrier](#stop-barrier) ·
[`stop2`](#stop2) ·
[`target3`](#target3) ·
[Triple-barrier target](#triple-barrier-target) ·
[`up_first` flag](#up_first-flag)

**Volatility (ATR family).**
[MTF pATR](#mtf-patr-multi-timeframe-asymmetry) ·
[pATR](#patr-percent-atr) ·
[pTR](#ptr-percent-true-range) ·
[`shift(3)` lag](#shift3-lag) ·
[Wilder smoothing](#wilder-smoothing)

**Evaluation & sample geometry.**
[Average uniqueness](#average-uniqueness--label-overlap) ·
[Effective sample size](#effective-sample-size) ·
[Embargo](#embargo) ·
[Frequency-matched random signal](#frequency-matched-random-signal) ·
[Hard failure / Soft observation](#hard-failure--soft-observation) ·
[Payoff-implied breakeven rate](#payoff-implied-breakeven-rate) ·
[Purging](#purging) ·
[Reward : risk](#reward--risk) ·
[Walk-forward CV](#walk-forward-cv)

---

## Triple-barrier labelling

### Triple-barrier target

A path-dependent label: for each entry timestamp `t`, place three barriers
ahead of `t` — a profit barrier above, a stop barrier below, and a horizon
barrier at `t + H` bars — then label the bar by **which barrier price
touches first**. Outcomes are `+1` (profit), `−1` (stop), or `0` (horizon,
no-touch). v1's three-class scheme is rebuilt cleanly in Phase B.

### Profit barrier

`profit_level = (1 + m_target × target_patr) × entry_price`

The level above the entry at which a position is considered to have hit its
take-profit. Default `m_target = 4`. The choice of `target_patr` (which
pATR timeframe scales the target) is governed by **D-026**.

### Stop barrier

`stop_level = (1 − m_stop × stop_patr) × entry_price`

The level below the entry at which the position is considered to have hit
its stop-loss. Default `m_stop = 2.5`. The choice of `stop_patr` is governed
by **D-026**.

### Horizon barrier

The time bound on the label: if neither the profit nor the stop barrier is
touched within the horizon window, the label resolves to `0` (no-touch).
Default horizon ≈ 510 bars at the 15m decision cadence (≈ 5.3 days), inherited
from v1's `TargetExtractor3`.

### First-touch resolution (1m vs 15m)

When both the profit and the stop barrier sit inside a single 15m candle's
high–low range, the order of touch is ambiguous from that bar's OHLC alone.
Two resolutions exist:

- **1m sub-candle resolution** — inspect the 1m bars *inside* the ambiguous
  15m bar to determine which barrier was touched first. This is the
  methodologically honest resolution and the primary result.
- **15m optimistic resolution** — v1's behaviour: when both barriers are in
  range, assume the favourable side was hit first. Retained as a comparison
  configuration for measuring the inflation v1's heuristic produced.

Verdict and rationale live in **D-006**.

### `up_first` flag

A per-bar directional flag derived from the 1m sub-candles inside each
higher-timeframe bar: `1` if the bar's high was reached *before* its low
(net upward intra-bar path), `0` otherwise. Makes the true range
**directional** by selecting which of the gap terms (`|H − C_prev|` vs.
`|L − C_prev|`) is "active." A v1 design choice, not standard Wilder ATR,
preserved in **D-012** and consumed by the 1m first-touch resolution
(**D-006**).

### `rt3`

The **raw first-crossing label** — the *side label*, primary. Answers
"which barrier did price touch first?" Values: `+1` profit / `0` no-touch
/ `−1` stop. Stored on `LabelResult` (**D-029**).

### `target3`

The **meta-label** — a filtered version of `rt3`. Set to `rt3` when the
profit target is touched cleanly; set to `0` when the slack-expanded stop
(see [`stop2`](#stop2)) is touched first, flagging the trade as ambiguous.
Maps onto López de Prado's meta-labeling framework (AFML Ch. 3.6) — `rt3` is
the primary label (side), `target3` is `𝟙[primary's bet paid off under
tighter risk control]`. See LEARNINGS L-006 for the discovery; **D-014**
makes the meta-labeling step a learned model in v2 while keeping `target3`
as the reproduction target on the v1 side.

### `stop2`

`stop2_level = (1 − (m_stop + slack) × stop_patr) × entry_price`

A **second, slightly-tighter stop level** (default `slack = 1.0`). If
price crosses `stop2` before reaching the profit barrier, the trade is
treated as "too close to the stop to count" and `target3` is set to `0`
even when `rt3 = +1`. This is the **ambiguity threshold** that drives
v1's embedded meta-labeling.

---

## Volatility (ATR family)

### pATR (percent ATR)

A **price-normalized form of the Average True Range** — each true-range
component is divided by a reference price, making the series a *ratio*
that is scale-invariant across price regimes. This is why pATR can be fed
directly to the model as a stationary feature and why barrier multipliers
(`4 × pATR`, `2.5 × pATR`) are dimensionless.

`pATR` is the [Wilder-smoothed](#wilder-smoothing) average of
[`pTR`](#ptr-percent-true-range) over `window = 10` bars. The v1 formula is
locked in **D-012**.

### pTR (percent true range)

The per-bar percent true range. From v1's `ta_utils.py:41`
(`p_true_range`):

```
tr1 = (high − low) / (high if up_bar else low)
tr2 = |high − prev_close| / prev_close
tr3 = |low  − prev_close| / prev_close
pTR = max(tr1, tr2, tr3)
```

`up_bar` is determined by the [`up_first`](#up_first-flag) flag.

### Wilder smoothing

Exponential moving average with decay `α = 1/n`:

```
pATR[i] = (pATR[i−1] × (n − 1) + pTR[i]) / n,   with n = 10
```

Equivalent to `EMA(pTR, span = 2n − 1)` in the standard `2 / (span + 1)`
convention. Source: J. Welles Wilder, *New Concepts in Technical Trading
Systems* (1978). Locked in **D-012**.

### MTF pATR (multi-timeframe asymmetry)

pATR computed at multiple smoothing windows (e.g. `patr_15`, `patr_60`,
`patr_240` at 15-/60-/240-minute timeframes). For barrier construction the
two barriers use **different** pATR timeframes:

- **Longer-horizon pATR scales the profit target** (slow — fires only on
  moves large relative to the medium-term volatility regime, reducing
  false positives from noise).
- **Shorter-horizon pATR scales the stop** (reactive — tightens in volatile
  regimes, widens in calm ones).

`TargetExtractor3` defaults: `target_patr = patr_240`, `stop_patr = patr_60`.
The asymmetry is deliberate (see **D-026**); the single-timeframe
configuration is retained as the `TargetExtractor1` comparison. The
underlying term-structure reasoning is in LEARNINGS L-007.

### `shift(3)` lag

Higher-timeframe pATR series are lagged by **3 bars of the higher timeframe**
before being joined onto the 15m decision clock. Prevents current-bar
bleed — the guarantee is that no row of the 15m frame sees a
higher-timeframe pATR value that depends on data from after that row's
timestamp. v1 design, preserved in **D-012**; exact mechanics of "3 bars of
which clock" are pending Q4 of PHASE_B.B.0.

---

## Evaluation & sample geometry

### Walk-forward CV

Chronological cross-validation: train on a contiguous prefix, validate on
the next chronological window, test on the window after that, then slide
the cut forward and repeat. No future data ever leaks into a fitted model.

The primary configuration is multi-fold walk-forward with an expanding
training anchor; v1's single 75 / 15 / 10 chronological split is retained
as a comparison configuration. Geometry locked in **PHASE_B.B.3**.

### Purging

Removal of training samples whose label-resolution windows (`[t, t1]`)
overlap with the validation or test windows. Prevents the model from
fitting to training labels that "know about" validation/test bars via the
forward-window dependence of triple-barrier labels.

### Embargo

A time gap inserted on each side of the validation and test windows,
during which training samples are dropped even if their label windows do
not technically overlap. Guards against subtle leakage from features and
labels that are autocorrelated across the cut. Default `embargo_bars = 511`
per side (≈ one label-horizon at 15m). See **D-004**.

### Average uniqueness / label overlap

Triple-barrier labels are computed over forward windows of up to ~510 bars,
so consecutive labels share substantial portions of their resolution windows.
**Average uniqueness** (López de Prado, *Advances in Financial Machine
Learning*) measures how much of each label's window is "uniquely" its own —
typically well below 1 for this project. Naive sample counts therefore
overstate statistical power; honest confidence intervals must use the
[effective sample size](#effective-sample-size) instead.

### Effective sample size

The number of *statistically independent* labels, derived from average
uniqueness. Drives the width of honest confidence intervals — naive CIs
treat all N samples as independent and are correspondingly too narrow.

### Payoff-implied breakeven rate

The hit rate at which a strategy with a given reward : risk ratio breaks
even, **ignoring costs**. For the project's `4 : 2.5` reward : risk:

```
breakeven = stop / (target + stop) = 2.5 / (4 + 2.5) ≈ 38.5%
```

This — not an implicit 50% — is the reference bar for "better than chance"
in headline metrics. Locked in **D-007**.

### Reward : risk

The ratio of profit-barrier distance to stop-barrier distance, both in
pATR units. v1's default — and the project default — is `4 : 2.5`, giving
a payoff-implied breakeven of ≈ 38.5% pre-cost.

### Frequency-matched random signal

A baseline that issues random `+1` / `−1` signals at **the same trade
frequency as the candidate model**, evaluated under the same backtest
harness. Catches the trivial inflation that comes from class imbalance: any
strategy with a non-zero hit rate beats "always abstain," but a real edge
must beat trading at the model's own rate by random chance.

### Hard failure / Soft observation

The two severity levels used by Phase A's integrity checks.

- **Hard failure** — condition is physically impossible or indicates corrupt
  data (duplicate or non-monotonic timestamps, NaN in OHLC, negative volume,
  grid-misaligned timestamps). The pipeline halts; the data is not usable.
- **Soft observation** — condition is anomalous but plausible in real data
  (gaps > 1 interval, zero-volume bars, NaN in volume, etc.). Recorded in
  the integrity report; the pipeline continues.

Full criteria are listed in **PHASE_A § Integrity checks**.
