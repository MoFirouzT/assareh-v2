# Phase C — Baselines and evaluation harness

> **DRAFT.** First pass, written just ahead of starting Phase C (per PLAN's
> "what lives where"). Module paths, signatures, and sub-phase ordering are
> proposed, not locked. Two decisions are *resolved in this phase, not before it*
> — [D-008](DECISIONS.md#d-008--success-threshold-pre-registration) Stage 2
> (cost-adjusted breakeven value + final `V` source) and
> [D-016](DECISIONS.md#d-016--backtest-geometry-walk-forward-vs-cpcv) (CPCV: implement
> or drop). Treat anything touching those as provisional until C.7 commits them.

**Goal:**
Build the evaluation harness against which *everything* downstream is measured —
the four baselines, both dual-arm configurations, and (later) the model. Baselines
first, model never (this phase). This is the methodology checkpoint: if the
harness is wrong, every number after it is meaningless, so it is built and trusted
on baselines *before* the model has any incentive to "make it work."

This phase produces no model and fits nothing. It produces the `evaluate()`
contract, the metric definitions, the cost model, and the per-arm record schema
that the Phase E gap artifact is later joined from — **not recomputed from**.

> **Hard prerequisite:**
> Phase B complete. `splits.py` is the single source of truth for fold
> membership; `make_labels` produces both label arms with typed-null sentinels;
> `make_walkforward_folds` exposes `walkforward` / `v1_single` and *reserves*
> `cpcv` (raises `NotImplementedError`); `average_uniqueness` /
> `effective_n_uniqueness` are available for overlap-aware CIs. Phase C consumes
> these without reaching back into target or split internals — that gate was
> self-reviewed at the close of B.4.

---

## ⚠️ Discrepancy raised (CLAUDE.md hard rule)

PLAN.md's Phase C section (current text) says baseline metrics carry
**"label-overlap-aware Kish-`N_eff` CIs ([D-005](DECISIONS.md#d-005--sample-uniqueness-weighting))"**
in two places. That wording predates the **B.3 correction**
([D-005](DECISIONS.md#d-005--sample-uniqueness-weighting) added detail,
[L-022](LEARNINGS.md#l-022--kish-on-the-sample-weights-does-not-measure-label-overlap--use-the-uniqueness-sum-for-cis)):
Kish `(Σw)²/Σw²` measures *weight dispersion*, not *label overlap*, and on
near-uniform uniqueness it stays ≈ `N`, yielding **over-confident** CIs — the
opposite of what VISION requires. The overlap-aware CI denominator is the
**uniqueness-sum `Σ ūᵢ`** (`effective_n_uniqueness`), already implemented and
already pinned by [D-008](DECISIONS.md#d-008--success-threshold-pre-registration)
Stage 1. **This phase follows the decision, not the stale PLAN wording:** every CI
in Phase C uses `effective_n_uniqueness`; `n_eff_kish` is logged only as a
training-weight diagnostic. **Resolved:** PLAN.md has been edited — both the
Phase B and Phase C "Kish-`N_eff`" mentions now read "uniqueness-sum `N_eff`
(`Σ ūᵢ`)", citing D-005 corrected / L-022 — so the plan and the decision agree.

---

## Module layout

Phase C introduces these modules. Pin the paths now so C.1–C.6 land in agreed
locations; Phase E imports `evaluate` and the metric schema from here.

```text
src/assareh/
  backtest/
    __init__.py
    costs.py           # C.0 — cost model (D-011): taker fee + slippage cushion
    engine.py          # C.1 — vectorized backtest: signals + prices + costs → equity curve, P&L
  metrics/
    __init__.py
    metrics.py         # C.2 — precision@threshold, Sharpe, Sortino, MDD, win rate, win/loss
    intervals.py       # C.2 — overlap-aware CIs via effective_n_uniqueness (D-005)
    dsr.py             # C.3 — Deflated Sharpe Ratio (needs N, V — D-008, D-016)
    pbo.py             # C.3 — Probability of Backtest Overfitting via CSCV
  baselines/
    __init__.py
    baselines.py       # C.4 — four baseline signal generators
  harness/
    __init__.py
    arms.py            # C.5 — the dual-arm catalogue (Arm config + registry)
    schema.py          # C.5 — MetricRecord (per-arm metric row) + parquet IO
    evaluate.py        # C.5 — evaluate(signals, prices, fold, *, arm) -> Metrics
    tracking.py        # C.5 — MLflow logging (file backend), supplies DSR's N
  splits/
    splits.py          # C.6 — extend: cpcv scheme implementation (D-016)
notebooks/
  baseline_eval.ipynb  # C.4/C.7 — baseline comparison rendered on real data
tests/
  test_costs.py        # C.0
  test_backtest.py     # C.1
  test_metrics.py      # C.2
  test_intervals.py    # C.2
  test_dsr.py          # C.3
  test_pbo.py          # C.3
  test_baselines.py    # C.4
  test_evaluate.py     # C.5
  test_cpcv.py         # C.6
  conftest.py          # extended — a synthetic signals/prices/fold fixture
```

Polars lazy-by-default for any pipeline > 2 ops; `.to_pandas()` only at the
sklearn/scipy boundary, annotated (CLAUDE.md). All paths come from `Settings`;
the MLflow URI is `Settings.mlflow_tracking_uri` (`file:./mlruns`).

---

## C.0 — Cost model (D-011)

The cost model lands **first** because the *cost-adjusted breakeven*
([D-007](DECISIONS.md#d-007--breakeven-reference-385-not-50) added detail) is
[D-008](DECISIONS.md#d-008--success-threshold-pre-registration) Stage 2's missing
number, and Stage 2 must be committed at the C/D handoff (C.7). Everything
downstream (the engine, precision-at-threshold, DSR) references it.

[D-011](DECISIONS.md#d-011--cost-model): a taker fee plus a slippage cushion sized
to sub-1m touch ambiguity. Fills resolve at the barrier price on the **1m** series,
consistent with the primary label arm
([D-006](DECISIONS.md#d-006--barrier-touch-resolution-source)). Both **gross** and
**net** P&L are reported — gross lines up with v1 (the v1-faithful arm here, since
v1 modeled no costs at all), net is the honest headline. This is a *retained
comparison arm*, not a leakage probe: the gross/net gap is a real modeling
trade-off and runs every fold, indefinitely.

```python
# src/assareh/backtest/costs.py

@dataclass(frozen=True)
class CostModel:
    """Per-trade cost in return-fraction units (D-011).

    taker_fee_bps:  exchange taker fee per side, basis points.
    slippage_bps:   slippage cushion per side, basis points — sized to the
                    residual sub-1m touch ambiguity (D-006 added detail), i.e.
                    the price can move within the 1m bar between signal and fill.
    """
    taker_fee_bps: float = 5.0      # PLACEHOLDER — pin in C.0, feeds D-008 Stage 2
    slippage_bps: float = 2.0       # PLACEHOLDER — pin in C.0

    def round_trip_fraction(self) -> float:
        """Total cost of an entry + exit as a return fraction (both sides)."""
        return 2.0 * (self.taker_fee_bps + self.slippage_bps) / 1e4


def cost_adjusted_breakeven(cost: CostModel, *, u: float = 4.0, ell: float = 2.5) -> float:
    """Net-of-cost breakeven hit rate (D-007 added detail).

    Pre-cost breakeven is ℓ/(u+ℓ) = 2.5/6.5 = 38.5%. Each round trip also pays
    `round_trip_fraction` in price terms; expressed against the pATR-scaled
    payoff this lifts the breakeven above 38.5%. The exact lift depends on the
    average pATR at entry (costs are in price %, the payoff in pATR units), so
    this returns the breakeven for a given reference pATR — pinned in C.0 and
    recorded as D-008 Stage 2's number.
    """
```

> **Open in C.0 (feeds D-008 Stage 2):** the fee/slippage values are placeholders.
> Pin them against (a) Binance taker tier actually used in v1's era and (b) the
> 1m same-bar ambiguity rate measured in B.1 (the slippage cushion should bound
> the residual). The cost→breakeven conversion needs a reference pATR — decide
> whether the cost-adjusted breakeven is reported as a single number at the median
> entry pATR or as a per-trade quantity; record the choice in D-011/D-008.

### C.0 Tests

- `round_trip_fraction` matches hand arithmetic for known bps.
- `cost_adjusted_breakeven(zero_cost) == 38.5%` to tolerance (sanity: zero cost
  recovers the pre-cost bar).
- Monotonicity: higher fees ⇒ strictly higher cost-adjusted breakeven.

---

## C.1 — Vectorized backtest engine

Takes signals + prices + a `CostModel`, returns an equity curve and the raw
P&L series both **gross and net**. No Python loop over decisions; Polars/numpy
vectorized, lazy until the `.collect()` boundary.

```python
# src/assareh/backtest/engine.py

@dataclass(frozen=True)
class BacktestResult:
    equity_gross: np.ndarray      # cumulative, per decision point
    equity_net: np.ndarray
    pnl_gross: np.ndarray         # per-trade return fraction, pre-cost
    pnl_net: np.ndarray           # per-trade, post-cost
    trade_count: int
    fill_idx_1m: np.ndarray       # 1m bar index where each fill resolved

def run_backtest(
    signals: np.ndarray,          # ŝ_t ∈ {-1, 0, +1} on the 15m clock
    labels: LabelResult,          # supplies realised barrier outcomes + 1m fills
    cost: CostModel,
    *,
    fill_on: Literal["1m", "15m"] = "1m",   # 1m = honest (D-006); 15m = v1-faithful
) -> BacktestResult:
    """Resolve each non-zero signal against the triple-barrier outcome already
    computed by make_labels (B.1), apply costs, accumulate equity.

    A signal ŝ_t ≠ 0 takes the position implied by the label geometry at t: P&L
    is +u·pATR on a correct call, −ℓ·pATR on a wrong one, and the realised
    horizon return on a no-touch (0) — read from LabelResult, never recomputed,
    so the engine and the labeler cannot drift. fill_on selects the resolution
    substrate (D-006); costs are subtracted per round trip (D-011).
    """
```

Design note: the engine **consumes** `LabelResult` rather than re-walking the
price path — the barrier outcome is the labeler's job (B.1) and duplicating it
here would let the two drift. The engine's only new responsibilities are
position-from-signal, cost subtraction, and equity accumulation. Whether P&L on
the `0` (no-touch) class is the realised horizon return or a flat zero is an
**open modeling question** — it interacts with D-014's "absorb `0` as don't-act";
default to *no position taken on ŝ_t = 0* (no trade, no cost) and record the
choice.

### C.1 Tests

- A hand-built sequence of correct calls produces a monotone-increasing gross
  equity curve; net is strictly below gross by the per-trade cost.
- A frequency-matched random signal on a no-edge synthetic path has gross equity
  ≈ flat and net equity strictly decaying (costs only).
- `trade_count` equals the number of non-zero signals that took a position.
- `fill_on="15m"` and `fill_on="1m"` agree on unambiguous paths and diverge only
  on same-bar-ambiguous decisions (the D-006 finding, mirrored on the P&L side).

---

## C.2 — Metrics module and overlap-aware CIs

All headline metrics, each referenced to the **cost-adjusted breakeven** (C.0),
never to 50% ([D-007](DECISIONS.md#d-007--breakeven-reference-385-not-50)).

`metrics.py` computes:

- **precision-at-threshold** — fraction of taken positions that were correct,
  for a decision threshold on the signal/probability; reported net-of-cost and
  judged against the cost-adjusted breakeven.
- **net & gross profit** (terminal equity, from C.1).
- **max drawdown** on the net equity curve.
- **Sharpe** and **Sortino** (per-trade, annualized to the 15m cadence with the
  realised trade frequency — document the annualization factor).
- **trade count**, **win rate**, **average win/loss ratio**.

`intervals.py` computes every CI with the **overlap-aware** effective sample
size — `effective_n_uniqueness(label_spans)` = `Σ ūᵢ`
([D-005](DECISIONS.md#d-005--sample-uniqueness-weighting) corrected,
[L-022](LEARNINGS.md#l-022--kish-on-the-sample-weights-does-not-measure-label-overlap--use-the-uniqueness-sum-for-cis)),
**not** Kish. `SE ≈ σ/√N_eff`; a precision reported without an `N_eff`-based
interval is not finished. The same machinery is applied to **baseline** metrics
as to model metrics — apples-to-apples CIs are what make VISION DoD #4's
four-baseline comparison valid. The label spans feeding `N_eff` are the spans of
exactly the decisions entering the metric (e.g. the taken-position subset for a
precision CI), confined to the relevant fold.

```python
# src/assareh/metrics/intervals.py
def precision_ci(
    correct: np.ndarray,          # bool per taken position
    label_spans: np.ndarray,      # (n,2) spans of those same positions
    *, confidence: float = 0.95,
) -> tuple[float, float, float]:
    """Return (precision, ci_lo, ci_hi) with N_eff = Σ ūᵢ as the denominator."""
```

### C.2 Tests

- Disjoint labels: `N_eff ≈ n`, CI matches the textbook binomial interval.
- Fully-overlapping labels: `N_eff → 1`, CI widens by `√n` versus the naive one
  (the overlap penalty is visible, not cosmetic).
- precision/win-rate/Sharpe on a hand-built equity curve match closed forms.
- MDD on a known drawdown path matches by inspection.

---

## C.3 — Deflated Sharpe Ratio and PBO (CSCV)

The two backtest-overfitting guards [D-008](DECISIONS.md#d-008--success-threshold-pre-registration)'s
pre-registered criterion checks against (Bailey & López de Prado 2014).

**DSR** (`dsr.py`). The DSR deflates an observed Sharpe by the number of trials
`N` and the variance of Sharpe *across* those trials `V`
([D-008](DECISIONS.md#d-008--success-threshold-pre-registration) added detail).
A single walk-forward curve supplies neither, so:

- `N` = the count of configurations logged to MLflow (C.5 supplies it from the
  tracking log — `folds × dual-arm configs × baselines`).
- `V` = the **trial-set estimator** pinned in
  [D-008](DECISIONS.md#d-008--success-threshold-pre-registration) Stage 1:
  variance of Sharpe across that same trial set. CPCV (C.6) is the *secondary*
  `V` source, used only if the trial-set estimate is too narrow — that
  decision is part of the D-016 verdict (C.7).

```python
def deflated_sharpe(
    observed_sr: float, *, n_trials: int, var_sr_across_trials: float,
    n_obs: int, skew: float, kurtosis: float,
) -> float:
    """DSR ∈ [0,1]: P(true SR > 0) after deflation. The bar is DSR > 0.95 (D-008)."""
```

**PBO via CSCV** (`pbo.py`). Combinatorially Symmetric Cross-Validation: split the
`T × n_trials` performance matrix into `S` even blocks, form every train/test
partition from `C(S, S/2)` combinations, rank configurations in-sample, and
measure how often the in-sample best underperforms the test-set median. PBO =
that frequency; the bar is **PBO < 0.2**
([D-008](DECISIONS.md#d-008--success-threshold-pre-registration)).

### C.3 Tests

- DSR of a single trial (`N=1`, `V=0`) reduces to the probabilistic Sharpe ratio
  (sanity bridge to the simpler formula).
- DSR strictly decreases as `n_trials` grows at fixed observed Sharpe (more
  trials ⇒ more deflation).
- PBO ≈ 0 on a synthetic matrix where one trial genuinely dominates every split;
  PBO ≈ 0.5 on i.i.d.-noise trials (no real edge ⇒ in-sample winner is a
  coin-flip out-of-sample).

---

## C.4 — The four baselines

Each baseline emits a signal series on the 15m clock, run through the **same**
`run_backtest` + metrics + CI path as the model will be — that identity is the
point of building the harness on baselines.

1. **Buy-and-hold** — always long; the market-return reference.
2. **Naive direction** — predict the last 15m move continues (sign of the prior
   return). The "is there any persistence?" control.
3. **Simple TA rule** — e.g. EMA(fast)/EMA(slow) crossover. Sanity check that
   *something* trades and the cost model bites; not meant to win.
4. **Frequency-matched random** — a random signal with the **same trade count**
   as the comparison target, run through the same cost model. The real "is there
   an edge?" control: any apparent edge that a frequency-matched coin-flip also
   shows is not signal.

> **Frequency match at Phase C:** there is no model yet, so #4 is matched to a
> reference trade count (parameterized; default = the simple-TA-rule count) so
> the harness and schema can be validated end-to-end. In Phase E it is **re-run
> matched to the model's realised trade count** — the match target is a
> parameter, not a constant. Record this so the Phase E re-match isn't read as a
> methodology change.

```python
# src/assareh/baselines/baselines.py
def buy_and_hold(index: pl.Series) -> np.ndarray: ...
def naive_direction(df15: pl.DataFrame) -> np.ndarray: ...
def ema_crossover(df15: pl.DataFrame, *, fast: int = 12, slow: int = 26) -> np.ndarray: ...
def frequency_matched_random(
    index: pl.Series, *, target_trades: int, seed: int,
) -> np.ndarray:
    """Random ±1/0 signal with exactly `target_trades` non-zero entries.
    Seeded from Settings.random_seed for reproducibility."""
```

All four use only data available at or before `t` (no look-ahead — the naive and
TA signals read the *prior* bar's close).

### C.4 Tests

- Each baseline produces a signal of the right length with no future leak (a
  permutation of future bars cannot change signal `t`).
- `frequency_matched_random` emits exactly `target_trades` non-zero signals and
  is reproducible under a fixed seed.
- Buy-and-hold net equity equals the cumulative market return minus one entry
  cost (it trades once).

---

## C.5 — The `evaluate()` harness, arm catalogue, and per-arm schema

The runtime form of the [D-001](DECISIONS.md#d-001--dual-arm-methodology-governing-rule)
governing rule: **one call site drives every arm.**

### The arm catalogue (`arms.py`)

`Arm` is a frozen config bundle; a registry names the full dual-arm catalogue.
Per PLAN: **8 leakage probes + 2 retained comparison arms.**

| arm | decision | kind | exercised in C? |
|-----|----------|------|-----------------|
| embargo | [D-004](DECISIONS.md#d-004--embargo-and-purging) | leakage probe (statistical) | ✅ via fold |
| barrier resolution | [D-006](DECISIONS.md#d-006--barrier-touch-resolution-source) | leakage probe (statistical) | ✅ via labels/fills |
| walk-forward geometry | [D-010](DECISIONS.md#d-010--walk-forward-geometry) | leakage probe (statistical) | ✅ via scheme |
| feature-selection scope | [D-013](DECISIONS.md#d-013--feature-selection-scope) | leakage probe (statistical) | ⛔ Phase D |
| gap-fill discipline | [D-036](DECISIONS.md#d-036--gap-fill-discipline-leakage-probe) | leakage probe (data) | ✅ via labels |
| feature-frame NaN policy | [D-037](DECISIONS.md#d-037--feature-frame-nan-policy-leakage-probe) | leakage probe (data) | ⛔ Phase D |
| pATR fill policy | [D-038](DECISIONS.md#d-038--patr-fill-policy-in-label-construction-leakage-probe) | leakage probe (data) | ✅ via labels |
| cross-TF alignment | [D-039](DECISIONS.md#d-039--cross-timeframe-alignment-method-leakage-probe) | leakage probe (data) | ⛔ Phase D |
| loss function | [D-009](DECISIONS.md#d-009--loss-function) | retained comparison | ⛔ Phase E |
| cost model gross/net | [D-011](DECISIONS.md#d-011--cost-model) | retained comparison | ✅ here |

The harness **interface** must span the whole catalogue from day one (so Phase D/E
add nothing to the call site), but Phase C can only *exercise* the arms reachable
from baselines + labels + splits: the cost arm (D-011), the barrier/gap/pATR
label arms (D-006/036/038, which change *which labels exist*), and the split arms
(D-004 embargo, D-010 geometry, via the fold). The feature-side arms (D-013/037/039)
and the loss arm (D-009) are **registered but inert** here — they carry their
identity into the schema for provenance and become live in D/E. This is
deliberate: validating the schema end-to-end on the reachable subset proves the
contract without waiting for the model.

```python
# src/assareh/harness/arms.py
@dataclass(frozen=True)
class Arm:
    arm_id: str
    cost: Literal["gross", "net"]                 # D-011 (live in C)
    barrier_resolution: Literal["1m", "15m"]      # D-006 (live in C, via labels)
    gap_fill: Literal["observed", "zoh_causal", "v1_noncausal"]  # D-036
    patr_fill: Literal["realised_only", "v1_ffill_bfill"]        # D-038
    embargo: Literal["horizon", "zero"]           # D-004 (live in C, via fold)
    geometry: Literal["walkforward", "v1_single"] # D-010 (live in C, via scheme)
    # --- registered but inert until Phase D/E ---
    feature_scope: Literal["per_fold", "global"] = "per_fold"    # D-013
    feature_nan: Literal["observed", "v1_bfill"] = "observed"    # D-037
    cross_tf: Literal["asof", "v1_counterwalk"] = "asof"         # D-039
    loss: Literal["bce_focal", "mse_mae"] = "bce_focal"          # D-009

HONEST: Arm = Arm(arm_id="honest", cost="net", barrier_resolution="1m",
                  gap_fill="observed", patr_fill="realised_only",
                  embargo="horizon", geometry="walkforward")
# plus one Arm per probe = HONEST with exactly one field flipped to its v1 value,
# and V1_FAITHFUL = every field at its v1 value (the fully-faithful arm).
REGISTRY: dict[str, Arm] = {...}
```

Each leakage probe is the honest arm with **exactly one** field flipped — so the
Phase E gap for that discipline is a clean one-variable contrast. The fully
v1-faithful arm flips all of them at once; the difference between "sum of
individual flips" and "all flipped together" is the additive-vs-interacting
finding PLAN Phase E calls out.

### The per-arm metric record schema (`schema.py`)

Every metric is emitted as one **long-format** row — this is what lets Phase E
compute the gap as a `join`, never a re-derivation:

```text
MetricRecord:
  arm_id:      str        # key into REGISTRY
  fold:        int        # Fold.fold_id, or -1 for an aggregate-over-folds row
  metric_name: str        # shared across arms — the join key with (fold)
  value:       float
  n_eff:       float      # Σ ūᵢ for this metric's label set (D-005)
  ci_lo:       float
  ci_hi:       float
```

Written to a parquet (`reports/metrics.parquet`, path from `Settings`) **and**
logged to MLflow (C.5 tracking). The four leakage-probe arms share the honest
arm's `metric_name` set exactly, so the Phase E gap is
`v1_faithful_value − honest_value` joined on `(fold, metric_name)` — the schema
*structurally prevents* the gap math from silently reweighting or redefining
anything (PLAN Phase C). Phase E's `reports/gap.parquet` is joined *from* this,
not recomputed.

### The interface (`evaluate.py`)

```python
def evaluate(
    signals: np.ndarray,
    prices: pl.DataFrame,            # 15m + 1m, enough for fills
    fold: Fold,
    *,
    arm: Arm,
    labels: LabelResult,             # already produced under arm's label config
) -> list[MetricRecord]:
    """Run one (signal set, fold, arm) through backtest → metrics → CIs and
    return the per-arm metric rows. `arm` selects the cost treatment directly
    (gross/net, D-011); the label/split arms are reflected in `labels` and `fold`
    upstream. A single call site drives every arm (D-001)."""
```

The caller loops `for arm in REGISTRY for fold in folds for baseline in baselines`
and concatenates the rows. That loop **is** the dual-arm methodology made runnable.

### MLflow tracking (`tracking.py`)

Local file backend (`Settings.mlflow_tracking_uri`). One run per
`(arm, baseline)`; per-fold metrics as steps; the config (arm fields, cost
params, fold geometry) logged as params. The **count of logged configurations is
DSR's `N`** ([D-008](DECISIONS.md#d-008--success-threshold-pre-registration)) — so
the tracking log is not just bookkeeping, it is load-bearing for the threshold.

### C.5 Tests

- `evaluate` on a fixed signal/fold/arm returns the expected `MetricRecord`
  rows; round-trip through parquet preserves dtypes.
- Honest and gross-arm rows on the same signals differ *only* where cost enters
  (net P&L, net precision) — the gross/net contrast is isolated.
- Each single-flip probe arm differs from honest on the expected metrics and
  matches it elsewhere (clean one-variable contrast).
- The gap join: `v1_faithful − honest` on `(fold, metric_name)` succeeds with no
  missing keys (schema alignment holds end-to-end).
- MLflow run count equals `len(REGISTRY) × n_baselines` (DSR's `N` is recoverable
  from the log).

---

## C.6 — CPCV in reduced configuration (D-016 verdict)

Operationalizes [D-016](DECISIONS.md#d-016--backtest-geometry-walk-forward-vs-cpcv).
The `scheme="cpcv"` slot reserved in Phase B's `make_walkforward_folds` is wired
here. Combinatorial Purged CV partitions the timeline into `N` groups, holds out
`k` at a time, and assembles `φ = C(N−1, k−1)` full-length out-of-sample **paths**
— a Sharpe *distribution*, which supplies the across-trial variance `V` the DSR
needs. Purge + embargo apply to every train/test combination exactly as in the
walk-forward case ([D-004](DECISIONS.md#d-004--embargo-and-purging)).

Runs on the **four baselines** (this phase) and, in Phase E, a **reduced-epoch**
model only — full-depth CPCV on the deep model costs `C(N,k)/k ×` the training
budget and is out of scope. The headline deep model still reports its
walk-forward point; CPCV exists to make that point's DSR interpretable.

```python
def make_cpcv_folds(
    index: pl.Series, *, n_groups: int = 8, k_test: int = 2,
    horizon_bars: int = 48, embargo_bars: int = 48,
) -> list[Fold]:
    """C(n_groups, k_test) purged+embargoed combinations; reassembled into
    φ = C(n_groups-1, k_test-1) OOS paths by path_id (D-016)."""
```

**The D-016 verdict is recorded in this phase** (PLAN Phase C exit criterion):
either CPCV is implemented and becomes the (secondary) `V` source, or it is
dropped on compute grounds and `V` stays the trial-set estimator pinned in D-008
Stage 1. Status moves `Proposed → Accepted` (implemented) or `Proposed →
Rejected` (dropped, trial-set `V` only). Either way the walk-forward remains the
primary backtester.

### C.6 Tests

- `make_cpcv_folds` returns exactly `C(n,k)` folds and `C(n−1,k−1)` reassembled
  paths; every path covers the full timeline once.
- No train index in any combination overlaps its test groups post-purge; the
  embargo gap holds (reuses the B.3 purge/embargo property tests).
- `scheme="cpcv"` no longer raises `NotImplementedError`.

---

## C.7 — Checkpoint and the C/D handoff

### Commit [D-008](DECISIONS.md#d-008--success-threshold-pre-registration) Stage 2

Stage 1 (rule *structure*) was frozen at the end of Phase B. Stage 2 locks the
remaining **values**, now that the cost model (C.0) exists and the D-016 verdict
(C.6) is in — **before any model is fit in Phase E**:

- the **numeric cost-adjusted breakeven** from C.0's `cost_adjusted_breakeven`
  (the bar the threshold actually checks; the pre-cost 38.5% stays the reference);
- confirmation of the **`V` source** per the D-016 verdict (trial-set estimator
  primary; reduced CPCV secondary iff implemented in C.6).

Appended to D-008. After this, Phase E cannot retrofit the bar.

### Record the [D-016](DECISIONS.md#d-016--backtest-geometry-walk-forward-vs-cpcv) verdict

`Proposed → Accepted/Rejected` with the compute rationale (C.6).

### Checkpoint list

- `costs.py`, `engine.py`, the metrics/dsr/pbo modules, the four baselines,
  `evaluate`, the arm registry, the per-arm schema, and (if accepted) the CPCV
  folds — all committed with green tests and CI.
- `evaluate()` runs all four baselines under every **exercisable** probe arm; the
  per-arm parquet schema is validated end-to-end on baseline output (PLAN Phase C
  exit criterion).
- `reports/metrics.parquet` written from a real baseline run; the gap join
  (`v1_faithful − honest`) demonstrated on baseline rows (the Phase E mechanism,
  proven before the model exists).
- DECISIONS.md: [D-011](DECISIONS.md#d-011--cost-model) cost values pinned;
  [D-008](DECISIONS.md#d-008--success-threshold-pre-registration) Stage 2 appended;
  [D-016](DECISIONS.md#d-016--backtest-geometry-walk-forward-vs-cpcv) verdict
  recorded.
- ✅ PLAN.md already edited to fix the **Kish→uniqueness-sum** discrepancy flagged
  at the top of this doc (done when this draft landed; re-verify it survived any
  later PLAN edits).
- LEARNINGS.md: any harness surprises (cost sensitivity, baseline behavior, PBO on
  the baseline trial set).
- Commit `C: phase complete`.
- **Self-review against the gate:** *Phase E must be able to call `evaluate()` with
  a model's signals and get a trusted number with no harness change.* If fitting
  the model would require reaching into the engine, metrics, or schema, the
  interface is wrong — fix it before D begins.

---

## What Phase C deliberately does **not** do

- **No model, no training, no features, no scalers** (Phase D/E). The harness is
  built and trusted on baselines precisely so the model can't bend it.
- **No feature-side arms wired live** — D-013, D-037, D-039 are *registered* in
  the catalogue for interface stability but exercised in Phase D; D-009 (loss) in
  Phase E. Phase C does not assemble features or fit losses to "see if the harness
  works"; the reachable label/split/cost arms already validate the schema.
- **No threshold tuned against test data.** Precision-at-threshold is computed at
  fixed reference thresholds here; the model's operating threshold is tuned on
  *validation* folds in Phase E ([D-008](DECISIONS.md#d-008--success-threshold-pre-registration)).
- **No held-out test window touched** ([D-042](DECISIONS.md#d-042--held-out-test-window-reservation)).
  The reservation mechanism exists in `splits.py`; the block is touched at most
  once, in Phase E, after the threshold is already met on the walk-forward.
- **No full-depth CPCV on a deep model** — reduced configuration only, on
  baselines here and a reduced-epoch model in E (D-016).

If you find yourself wanting any of these to "make the numbers look right," stop:
that impulse is exactly what building the harness *before* the model exists is
designed to prevent.
