# LEARNINGS

Append-only log of findings, surprises, and dead ends discovered during
research and engineering.

---

## L-001 — Early Binance 1m data has sub-minute timestamp offsets

**Discovered:** Phase A.3 — cross-timeframe alignment check
**Affected rows:** 21,602 of 4,598,701 1m bars; 81 of 306,588 15m bars; 43 of 76,660 1h bars; 0 of 19,179 4h bars

The raw Binance 1m OHLCV data for BTC/USDT contains two distinct timestamp
offsets during the period **2017-12-04 06:00 UTC → 2018-02-10 06:00 UTC**:

- **+20.799 s** (2017-12-04 – early 2018-02): affects the 1m series only.
  During this window 15m and 1h bars sit at clean minute boundaries, but the
  1m bars underneath them are shifted forward by ~21 seconds — the 1m and
  15m/1h grids are mutually misaligned.
- **+14.789 s** (2018-02-09 – 2018-02-10): affects 1m, 15m, and 1h
  consistently. The three series share the same offset, so they are mutually
  aligned with each other but are off the mathematical minute grid.

The 4h series is clean throughout.

**Implication for Phase B (barrier resolution):** the +20.799 s window means
that for roughly two months of 1m data the barrier-resolution substrate is
not synchronised with the 15m decision clock. Any 15m decisions from that
window (~Dec 2017 – Feb 2018) should be treated with caution, or excluded
from training/test folds, when precise first-touch ordering matters.

**Implication for Phase D (feature alignment):** the +14.789 s window is
internally consistent (all three affected timeframes share the offset), so
as-of joins within that window will still resolve correctly. The +20.799 s
window is not consistent and may produce one-bar alignment errors for
features derived from 1m sub-candles.

**Action:** the cross-timeframe alignment check reports these as hard
failures (off-grid opens). Since the cause is a known Binance raw-data
quirk the test acknowledges the exception rather than blocking CI. Fold
design in Phase B should ensure neither training nor test folds are anchored
to these ~2 months without explicit handling.

---

## L-002 — Real-data integrity statistics (Phase A baseline)

**Discovered:** Phase A.3 — integrity checks on all four downloaded timeframes

All four timeframes pass `check_integrity` (no hard failures). Soft
observations worth knowing before Phase B/D:

| Timeframe |       Rows | Date range                      | Gaps | Largest gap              | Zero-vol | OHLC-equal |
|:----------|-----------:|:--------------------------------|:-----|:-------------------------|---------:|-----------:|
| 1m        |  4,598,701 | 2017-08-17 → 2026-05-21         |   34 | 2,010 bars (~33.5 h)     |   24,003 |     56,731 |
| 15m       |    306,588 | 2017-08-17 → 2026-05-21         |   32 | 134 bars (~33.5 h)       |       60 |        147 |
| 1h        |     76,660 | 2017-08-17 → 2026-05-21         |   28 | 32 bars (~32 h)          |        4 |          4 |
| 4h        |     19,179 | 2017-08-17 → 2026-05-21         |    9 | 7 bars (~28 h)           |        0 |          0 |

**Gap pattern.** Most of the 34 1m gaps occur just after 02:00 UTC —
consistent with Binance scheduled maintenance. The largest gap
(2,010 1m bars, 2018-02-08 00:28 → 2018-02-09 09:59 UTC) is the same
platform event that introduced the +14.789 s timestamp offset (see L-001).

**Zero-volume 1m bars** (24,003 rows, 0.52% of series). The vast majority
are from the 2017–2019 period: low-activity minutes on a then-thinly-traded
market. They are real bars, not corruption — do not filter them.

**OHLC-equal 1m bars** (56,731 rows, 1.23% of series). These are bars where
open = high = low = close, again concentrated in early low-volume periods.
They represent genuine price stability inside a 1-minute window.

**Implication for Phase B.** The common span for all four timeframes is
2017-08-17 → 2026-05-21. The Feb 2018 33-hour gap is the most significant
discontinuity; walk-forward fold boundaries should not straddle it.

---

## L-003 — Ancillary columns are unreliable for early and ccxt-sourced bars

**Discovered:** Phase A.2/A.3 — downloader code inspection and data audit

The columns `number_of_trades`, `taker_buy_base_volume`, and
`taker_buy_quote_volume` are zero in two distinct situations:

1. **Early Binance data (pre-~2020), 1m and 15m series.** The Binance Vision
   archives from 2017–2019 did not reliably populate these fields. Affected
   rows: ~23,792 of 24,945 1m zero-trade bars fall before 2020; ~122 of 15m.
   The values are structurally zero, not a processing artefact.

2. **ccxt-sourced tail bars (most recent ~days).** The downloader's
   `_fetch_ccxt_ohlcv` method explicitly sets these three columns to 0
   because the ccxt OHLCV response only returns OHLCV (five columns). The
   affected row count is small — at most a few hundred per interval at any
   given time.

**Implication for Phase D.** Any feature derived from `number_of_trades` or
the taker-buy columns will produce a spurious zero signal on ~0.5% of 1m
bars and on the entire early period. If these features are included, a
boolean `has_ancillary` flag (or simple `> 0` guard) is needed to avoid
treating structured zeros as genuine low-activity readings.

---

## L-004 — Loader must cast schema rather than assert exact match

**Discovered:** Phase A.3 — loader implementation

The downloader writes Parquet via pandas, which round-trips `Datetime`
timestamps at millisecond precision (`ms`), while the canonical
`OHLCV_SCHEMA` specifies microsecond precision (`us`). A strict schema
equality check would reject valid data that differs only in this precision.

**Resolution (DECISIONS.md):** the loader reads the file, validates that all
required columns are present, then casts every column to `OHLCV_SCHEMA`
types rather than asserting an exact match. This is a one-time cost at load
time and guarantees that downstream code always sees the canonical schema
regardless of how the Parquet was written.

---

## L-005 — Binance Vision CHECKSUM files are not always present

**Discovered:** Phase A.2 — downloader implementation

When fetching a monthly or daily ZIP from `data.binance.vision`, the
corresponding `.CHECKSUM` file (one-line `sha256  filename`) is not
guaranteed to exist — older archives sometimes return 404 for the checksum
URL. The downloader treats a missing checksum as a warning and proceeds
rather than hard-failing, which makes historical back-fills practical. Any
archive that *does* provide a checksum is verified and the hash is logged to
`data/raw/checksums.jsonl`.

---

## L-006 — v1's `target2=True` is embedded meta-labeling

**Discovered:** Phase B preparation — reverse-engineering the v1 TargetExtractor family

Analysis of `TargetExtractor` through `TargetExtractor4` reveals that the
`target2=True` branch is not a labeling quirk — it is a **rule-based
meta-labeling step hard-coded inside the labeler**, producing two structurally
distinct outputs:

- **`rt3`** — raw first crossing, the *side label* (primary). Answers "which
  direction did price move?" regardless of how cleanly the trade resolved.
- **`target3`** — filtered label, the *meta-label*. Set to `rt3` when the
  profit target is touched cleanly; set to `0` when `stop2` (the
  slack-expanded stop) is touched first, flagging the trade as ambiguous.
- **`stop2`** = `(1 − (m_stop + slack) × pATR) × price` is the
  **ambiguity threshold**: if price gets closer to the stop than `stop2`
  before reaching the target, the signal is downgraded to a non-event in
  the meta-label.

This maps precisely to López de Prado's **meta-labeling** framework
(AFML Ch. 3.6): `rt3` is the primary model's label (side), and `target3`
is the meta-label `m_t = 𝟙[primary's bet paid off under tighter risk control]`.
v1 implemented the meta-labeling rule in the labeler itself; v2's D-014 makes
this a learned two-stage model, but the label pair it needs (`rt3`, `target3`)
is exactly what v1 already produced.

**Implication for Phase B.** The v1-faithful arm in `make_labels` must
reproduce **both** `rt3` and `target3`, plus `stop2`. The `stop2_slack`
parameter must be configurable (default 1, matching v1). See PHASE_B.md B.1.

---

## L-007 — Multi-timeframe ATR term structure: why longer-vol for target, shorter-vol for stop

**Discovered:** Phase B preparation — analyzing TargetExtractors 2–4

The MTF pATR design (longer ATR for the profit target, shorter ATR for the
stop) is an application of **volatility term structure** reasoning:

- A **slow, long-horizon ATR** (e.g., 240-min pATR) is smooth and wide. It
  scales the profit target to the medium-term volatility regime, so the target
  only fires on moves that are large relative to normal baseline swings — not
  transient spikes. This reduces false positives from noise.
- A **fast, short-horizon ATR** (e.g., 60-min pATR) is reactive. It scales
  the stop to recent (fast) volatility, so the stop tightens in volatile
  regimes and widens in calm ones. This is consistent with cutting losses
  quickly when the market is choppy and giving room when conditions are stable.

Using a *single* pATR for both barriers creates a systematic mismatch: a
slow ATR makes the stop too wide in high-volatility regimes (losses compound
before the stop fires); a fast ATR makes the target too tight in low-volatility
regimes (false wins on small bounces). The asymmetric MTF design avoids both
failure modes and reduces the timeout (`0`) fraction compared to a
single-timeframe configuration.

This reasoning is captured as a design decision in **D-026**.

---

## L-008 — v1's default gap interpolation is non-causal and contaminates labels

**Discovered:** v1 data-handling audit (handed off to a Claude session with v1 repo access)
**Affected:** every gap-crossing label in v1's training window (2017-08-28 onward), all four timeframes

v1's `BtcPreprocessor` runs `LinearInterpolator` on each timeframe before
anything else touches the data. When a bar is missing,
`LinearInterpolator._estimate_ohlcv_and_insert_the_candles` synthesizes the
missing OHLCV by a **weighted average of the previous and the next available
bar** — non-causal. A causal alternative
(`_causal_estimate_ohlcv_and_insert_the_candles`) exists but is not the
default path; the bar-repeating `ZeroOrderHold` class is also available but
not used by `BtcPreprocessor`.

The synthesized bars then flow into `TargetExtractor.detect_reversals`,
which walks forward through `temp_df.high` and `temp_df.low` to decide
which barrier is touched first. Whenever the forward walk crosses a
synthesized bar, the high/low it reads is a function of the *next real*
bar's OHLC — i.e., the label's resolution is informed by data outside its
causal window.

**v1 code references:**

- `LinearInterpolator._estimate_ohlcv_and_insert_the_candles` —
  v1: `btc_feature_engineering_utils.py:396-415`
- `_impute_the_missing_candle` (caller) — v1: `:366`
- `BtcPreprocessor.interpolate_the_raw_data_and_add_up_first` —
  v1: `:148-152` (runs on 1m / 15m / 1h / 4h)
- `TargetExtractor.detect_reversals` (consumer) — v1: `:710`
- Causal alternative (default off) — v1: `:386-394`

**Scale of impact.** v1's training window starts 2017-08-28
(`0_Preprocessing.ipynb`, `first_day='2017-08-28 16:00:00'`); v2's L-002
records 34 gaps in the 1m series, the largest 33.5 h around 2018-02-08–09.
Every gap is synthesized in v1, then walked by every label whose horizon
spans it. The 511-bar (~5.3-day) horizon is wider than every observed gap
except the largest, so essentially every label issued within ~5 days of a
maintenance gap is contaminated.

**Implication for v2 Phase B.** The dual-arm framework requires both:

- *v1-faithful arm* — reproduce the non-causal weighted interpolation
  before label construction, so v1's reported numbers are reproducible.
- *honest arm* — leave gaps observed (per D-024); barrier walks that would
  cross an unfilled gap return a typed-null label (no decision) for that
  sample.

The gap between the two arms quantifies how much of v1's apparent labeling
edge comes from synthesized future leaking into the target. This is the
primary candidate for a new leakage-probe DECISIONS.md entry
(D-036, to follow).

**Implication for v2 Phase D.** The same interpolated series is the input
to every TA indicator (ATR, BB, Donchian, momentum). Any indicator whose
lookback window crosses a synthesized bar in v1 reads future-informed
values, so the leakage compounds on the feature side as well — the
gap-fill discipline arm is a feature-and-label probe, not a label-only one.

---

## L-009 — v1's `DataMixer.load_features` applies blanket `bfill` to every feature column

**Discovered:** v1 data-handling audit
**Affected:** every NaN cell in every feature column across v1's feature matrix

After per-timeframe indicators are computed, v1 assembles the multi-TF
feature frame in four parallel `DataMixer` variants
(`DataMixer`, `defDataMixer`, `NoTRFDataMixer`, `logDataMixer`). Each calls
`btc_df.fillna(method='bfill')` on the entire frame before returning it.
This is a **silent look-ahead bias** across the feature matrix: any NaN
that survived earlier stages (whether from an indicator's warm-up window,
a propagated NaN OHLC, or a NaN volume) gets the *next-bar* value.

**v1 code references:**

- `DataMixer.load_features` `bfill` — v1: `btc_feature_engineering_utils.py:1548`
- `defDataMixer.load_features` `bfill` — v1: `:1601`
- `NoTRFDataMixer.load_features` `bfill` — v1: `:1654`
- `logDataMixer.load_features` `bfill` — v1: `:1707`

**Scope.** All four variants are reachable from `0_Preprocessing.ipynb`
depending on the experimental configuration. The `bfill` runs *after* TF
join, so a single missing cell can pull from a bar at a different
timestamp than the row's nominal index. Indicator warm-up windows
(e.g., the first ~20 rows of a 20-bar SMA) are the most-affected region;
since v1 doesn't trim warm-up rows before passing to the model, the
model's earliest training samples are entirely back-filled from future.

**Implication for v2 Phase D.** Dual-arm split:

- *v1-faithful arm* — reproduce the `bfill` at the equivalent assembly
  step so v1's reported numbers are reproducible.
- *honest arm* — leave NaN cells untouched; mask them in the model's
  batch sampler so warm-up rows are excluded rather than back-filled.

The gap is the inflation v1's blanket `bfill` introduced. This is the
second new leakage-probe candidate (D-037, to follow).

**Relationship to L-008.** L-008's interpolated bars and L-009's `bfill`
operate on different NaN sources but compound: a gap creates NaN cells
that the interpolator fills with future-weighted synthetics, and any NaN
that slips through gets `bfill`'d at the `DataMixer` stage. Both must be
disabled in the honest arm; the v1-faithful arm reproduces both.

---

## L-010 — v1's `patr*` series is `ffill`+`bfill`'d *inside* `TargetExtractor2/3`

**Discovered:** v1 data-handling audit
**Affected:** label resolution wherever a pATR cell was NaN at compute time

The triple-barrier label depends on `patr_15`, `patr_60`, `patr_240`
(per D-026: longer-horizon for the profit target, shorter for the stop).
v1's `TargetExtractor2` and `TargetExtractor3` apply `ffill` followed by
`bfill` to these pATR series *as part of the label-construction step* —
so any pATR cell that was NaN at label time gets filled, and the fill
includes `bfill` from future observations.

This is the most direct labeling leak the audit surfaced: **barrier widths
in v1 depend on future pATR observations** whenever a pATR cell was NaN at
the label's anchor bar. Because pATR uses a Wilder-smoothed lookback, the
NaN region is concentrated at series start, so the labels most affected
are the earliest training samples — exactly the rows v1's reported numbers
treat as honest out-of-sample bars.

**v1 code references** (every line is a `patr*.fillna(method='ffill').fillna(method='bfill')` chain or equivalent inside a `TargetExtractor` method):

- v1: `btc_feature_engineering_utils.py:802`, `:817-820`
- v1: `:993`, `:1016-1019`
- v1: `:1224`, `:1247-1250`
- v1: `:1438`

**Implication for v2 Phase B.** Dual-arm split:

- *v1-faithful arm* — reproduce the `ffill`+`bfill` on the pATR series
  consumed by `make_labels`.
- *honest arm* — barriers anchored at bar `t` use only pATR realised at
  or before `t`. Bars with NaN pATR (series start, gap-adjacent) emit a
  typed-null label, not a fabricated one.

This is structurally similar to L-009's `DataMixer` `bfill` but operates
on the *labeling pathway* rather than the feature pathway, so the inflation
appears in the target distribution rather than the feature matrix.
DECISIONS.md entry D-038 will own it.

---

## L-011 — v1 mixes multi-TF samples by counter-walking, not by timestamp join

**Discovered:** v1 data-handling audit
**Affected:** every multi-TF training sample produced by `DataMixer3._mix_train`

v1's multi-TF assembly is index-arithmetic, not a timestamp join. Each
timeframe is loaded independently in `DataMixer.load_features` with the
same `first_day` / `last_day` window. The mixer then walks the four
per-TF frames using integer counters `i1, i2, i3, i4` and emits one row
per tick — `merge_asof`, intersection of indices, or any explicit
timestamp check is absent.

The assumption baked in is that coverage is uniform across timeframes.
If even one timeframe has more or fewer bars than expected — because of
a missing day, a snapped row dropped (L-012), or a quirk-window
realignment (L-001) — the counters drift relative to wall-clock time and
**bars from different real timestamps get stitched together as if
aligned**. The drift is silent and cumulative.

**v1 code references:**

- Per-TF independent load — v1: `btc_feature_engineering_utils.py:1545-1548`
- Counter-walk mixer (`DataMixer3._mix_train` and friends) —
  v1: `:2108-2133`

**Implication for v2 Phase D.** Dual-arm split:

- *v1-faithful arm* — reproduce the counter-walked mix.
- *honest arm* — assemble multi-TF features via `merge_asof` on the 15m
  decision clock (backward direction, strict; per D-030's existing
  alignment rules). Any timeframe that doesn't have a bar at or before
  the decision bar emits a typed-null cell.

Distinct from L-008 and L-009: the gap-fill and `bfill` probes are about
*missing* data, while this probe is about *misaligned* data. DECISIONS.md
entry D-039 will own it.

---

## L-012 — v1 silently floor-snaps off-grid bars per-timeframe, including the Binance quirk window

**Discovered:** v1 data-handling audit
**Affected:** the same off-grid rows v2's L-001 documents (~21k 1m bars,
~81 15m bars, ~43 1h bars in 2017-12-04 → 2018-02-10)

v1's `LinearInterpolator._adjust_dataframe_indices` walks each timeframe
and snaps off-grid timestamps to the floor of the timeframe boundary
(e.g., a 1m bar opening at 15:00:20.799 is moved to 15:00:00). When the
snap creates a collision with an existing on-grid bar, the snapped
duplicate is moved out past `last_day` and dropped, counted in
`number_of_candles_with_two_index`. The check runs **independently per
timeframe** with no cross-TF consistency verification.

Two consequences for v1's training window (`first_day='2017-08-28 16:00'`
covers the entire Binance-quirk period):

1. **Silent realignment.** The Dec 2017 → Feb 2018 quirk window
   (L-001) is silently flattened in each timeframe separately. v1 has
   no awareness that during the +20.799s window the 1m grid was
   misaligned to the 15m/1h grid above it.
2. **Silent row-drops.** Some bars are dropped after the snap collides.
   The count is recorded internally (`number_of_candles_with_two_index`)
   but never surfaced as a hard failure.

**v1 code references:**

- `_adjust_dataframe_indices` (per-TF floor-snap + collision drop) —
  v1: `btc_feature_engineering_utils.py:326-348`
- Training window start — v1: `0_Preprocessing.ipynb` cells using
  `first_day='2017-08-28 16:00:00'`; default
  `TimeStamps.start = '2017-08-17 00:00:00'` at v1: `:30`

**Implication for v2.** Reinforces both:

- D-025 (cross-TF alignment check severity) — v2's hard-failure mode on
  off-grid opens is the right default; the L-001 quirk window is the
  one documented exception.
- D-039 (cross-TF alignment method, to follow) — the per-TF independent
  snap is a defect, not just a fill choice, because it gives v1's
  counter-walk mixer (L-011) the illusion that the four timeframes are
  aligned when they aren't.

No standalone probe; this finding feeds the D-039 implementation and the
Phase B fold-design discipline ("fold boundaries should not straddle the
quirk window") already noted in L-001.

---

## L-013 — v1 has no OHLC arithmetic check at any stage

**Discovered:** v1 data-handling audit
**Affected:** any bar where `high < max(open, close)` or `low > min(open, close)`

v1's pipeline never validates that the OHLC fields obey the relationship
`low ≤ min(open, close) ≤ max(open, close) ≤ high`. The audit confirmed
the absence by reading `btc_feature_engineering_utils.py`,
`kafgir/models.py`, and the `Indicators/` directory — no assertion of
this shape exists.

Consequences for v1's pipeline:

- **Feature distortion.** ATR, Bollinger bands, Donchian channels, and
  the alternative-candle `tr_percent` / `ho_percent` / `co_percent` /
  `oc_percent` / `lo_percent` columns all consume `high` and `low`
  directly. A broken bar propagates into every window that touches it.
- **Label distortion.** `TargetExtractor.detect_reversals`
  (v1: `btc_feature_engineering_utils.py:710`) walks `temp_df.high` and
  `temp_df.low` to determine which barrier is touched first.
  An out-of-order high/low silently changes which barrier wins.

**Implication for v2.** v2's `check_integrity` already hard-fails on
OHLC arithmetic violations (D-022); v2's loaded data has zero such bars
(L-002). The finding doesn't motivate a new probe — it's a quality bar
v1 didn't enforce and v2 does. Worth a row in the gap artifact's
"data-quality discipline" column if any v1 bar turns out to violate the
relation; otherwise the entry stands as documentation that v2's hard
check is a real divergence from v1's permissive flow.

---

## L-014 — v1 silently clamps `volume < 1` to 1

**Discovered:** v1 data-handling audit
**Affected:** every zero-volume or sub-1 bar in v1's training data

v1's `LinearInterpolator` (and the `ZeroOrderHold` alternative) sets
`self.df.volume[self.df.volume < 1] = 1` after running the gap
interpolator. The clamp runs on all four timeframes via
`BtcPreprocessor.interpolate_the_raw_data_and_add_up_first`. No log of
how many bars are clamped, no flag column.

The mechanical reason is downstream `log(volume)` — the clamp makes
`log_volume = 0` for clamped bars rather than `-inf` or NaN. The
practical consequence is that **every legitimate zero-volume minute in
2017–2019** (~24k bars in v2's L-002 count, ~0.52% of the 1m series)
reads as `log_volume = 0` in v1's feature matrix, indistinguishable from
a bar with `volume = 1`.

**v1 code references:**

- `LinearInterpolator` clamp — v1: `btc_feature_engineering_utils.py:420-421`
- `ZeroOrderHold` clamp — v1: `:551-553`
- Driver — v1: `BtcPreprocessor.interpolate_the_raw_data_and_add_up_first`
  at `:148-152`

**Implication for v2 Phase D.** Volume-derived features in v2's honest
arm should *not* clamp; either use `numpy.log1p` on raw volume (still
defined at 0) or emit a `has_volume` flag alongside `log_volume`. The
v1-faithful arm reproduces the clamp at the equivalent step so v1's
volume features are reproducible. Not a leakage probe — a feature-value
distortion — so doesn't warrant a new D-NNN, but the dual-arm split
should be applied at the indicator level for volume-based features.

---

## L-015 — Minor v1 fill and convention behaviors (catch-all)

**Discovered:** v1 data-handling audit (cross-cutting observations)

Bundled here are smaller v1 behaviors documented for completeness; each
is either subsumed by an earlier L-NNN finding or has low independent
impact, but they're recorded so a future v1 re-audit doesn't re-discover
them as surprises.

- **Silent duplicate-drop on snap collision** (v1's #1 detection). When
  `_adjust_dataframe_indices` snaps a bar to the floor of its
  timeframe and the snap collides with an existing on-grid bar, the
  snapped duplicate is moved past `last_day` and dropped, counted in
  `number_of_candles_with_two_index`. No hard fail. Subsumed by L-012.
  v1: `btc_feature_engineering_utils.py:326-348`.
- **Silent sort after interpolation.** v1 calls `sort_index(inplace=True)`
  after interpolation steps; ordering is auto-corrected rather than
  validated. v1: `:317`, `:460`; initial CSV ingest at `:70`.
- **Silent `bfill` of NaN OHLC and NaN volume.** Any NaN that survives
  the interpolator is back-filled at the `DataMixer.load_features`
  stage (L-009). For NaN volume specifically: the `volume < 1` clamp
  in L-014 doesn't catch NaN (since `NaN < 1` is False), so a NaN
  volume row flows past the clamp into the `bfill`.
- **Timezone-naïve timestamps throughout.** CSV ingest parses
  `pd.to_datetime(..., format="%Y-%m-%d %H:%M:%S")` with no tz
  awareness (v1: `:69`, `:89`, `:583`). Production stores epoch
  seconds derived from Binance ms timestamps (v1:
  `kafgir/models.py:222`, `:236`). The seed script
  `add_kick_start_data_to_db.py:49` calls `.timestamp()` on a
  tz-naïve datetime, treating it as local time before epoch
  conversion — so if the seed ran on a non-UTC server the entire
  `time_stamp` axis is shifted by the local UTC offset. Django
  `TIME_ZONE = 'UTC'` is set but only governs the ORM layer.
  v2 enforces UTC at the loader (D-021).
- **`_create_log_alternative_candles` first-row `fillna('backfill')`.**
  `log_diff.shift(1).fillna(method='backfill')` ensures the first row
  of log-stationary features is populated — by *future* data. Look-ahead
  on row 0 of every series. Independent of L-009's `DataMixer` `bfill`
  because it runs earlier in the pipeline. v1: `:183-189`.
- **Sentinel `fillna(value=33)` for target frames.** v1's target
  pipeline writes `df.fillna(value=33, inplace=True)` to mark
  no-decision bars (v1: `:706`, `:883`, `:1096`, `:1321`, `:1486`).
  Functional in v1; v2 uses typed-null sentinels (D-029) instead.
  Worth knowing if v1's reported metrics include or exclude
  sentinel rows.
- **`v1 confirmed non-issues` (no action in v2).** Per the audit:
  v1 never reads `number_of_trades` / `taker_buy_*` (#17 — D-020's
  honest-arm guard has no v1 counterpart), v1 has no archive
  integrity verification (#18), and v1 fetches from a single source
  with no cross-verification (#21). These are v2-only disciplines.

---

## L-016 — Binance Vision CSVs use mixed timestamp encodings

**Discovered:** Phase A.2 — downloader implementation

Binance Vision klines archives do not use a single fixed timestamp encoding
across the dataset. Some files encode `open_time` / `close_time` as 13-digit
milliseconds; others use 16-digit microseconds; a small set of edge cases
use 10-digit seconds. Pinning the parser to `unit='ms'` would silently
corrupt every microsecond-encoded row by misinterpreting its scale by a
factor of ~31,556 (epoch 2010-01-01 in `ms` becomes year 41,950 if read as
`us`, etc.) — no exception, just plausible-looking but wildly wrong dates.

**Resolution.** The downloader's
`_parse_vision_csv._to_datetime_series`
(scripts/data_downloader.py:134-167) detects encoding by numeric range,
column-wide:

- `[1.26e12, 3.25e13]` → milliseconds
- `[1.26e15, 3.25e16]` → microseconds
- `[1.26e9,  3.25e10]` → seconds

Each range spans roughly 2010 → year 3000, the three are non-overlapping,
and the check uses `.between(...).all()` because a single Vision CSV
always uses one consistent encoding for the whole file. The parser tries
ms first, then us, then s; a fall-through tries `unit='ms'` one more time
and raises with a 10-value sample if even that fails. The ccxt path is
unaffected — `ccxt.fetch_ohlcv` always returns milliseconds and is
documented as such (scripts/data_downloader.py:378).

**Implication.** No silent corruption on historical back-fills regardless
of which encoding Binance happened to publish for a given archive. The
guard is local to Vision CSV parsing; no downstream code needs to be aware
of it, because `OHLCV_SCHEMA` pins the final dtype at the loader boundary
(D-034).
