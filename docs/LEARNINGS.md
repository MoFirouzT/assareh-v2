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
