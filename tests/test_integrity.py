import pytest

from assareh.config import Settings
from assareh.data.integrity import check_integrity
from assareh.data.loader import load_ohlcv


# ---------------------------------------------------------------------------
# Synthetic data — hard failures
# ---------------------------------------------------------------------------

def test_clean_passes(synthetic_ohlcv):
    report = check_integrity(synthetic_ohlcv(), "1m")
    assert report.passed
    assert report.hard_failures == []


def test_duplicate_is_hard_failure(synthetic_ohlcv):
    report = check_integrity(synthetic_ohlcv(issues={"duplicate"}), "1m")
    assert not report.passed
    assert report.n_duplicates > 0
    assert any("duplicate" in f.lower() for f in report.hard_failures)


def test_non_monotonic_is_hard_failure(synthetic_ohlcv):
    report = check_integrity(synthetic_ohlcv(issues={"non_monotonic"}), "1m")
    assert not report.passed
    assert any("non-monotonic" in f.lower() or "monotonic" in f.lower() for f in report.hard_failures)


def test_ohlc_violation_is_hard_failure(synthetic_ohlcv):
    report = check_integrity(synthetic_ohlcv(issues={"ohlc_violation"}), "1m")
    assert not report.passed
    assert report.ohlc_violation_count > 0
    assert any("ohlc" in f.lower() or "violation" in f.lower() for f in report.hard_failures)


def test_negative_volume_is_hard_failure(synthetic_ohlcv):
    report = check_integrity(synthetic_ohlcv(issues={"negative_volume"}), "1m")
    assert not report.passed
    assert any("negative" in f.lower() for f in report.hard_failures)


def test_nan_in_close_is_hard_failure(synthetic_ohlcv):
    report = check_integrity(synthetic_ohlcv(issues={"nan_in_close"}), "1m")
    assert not report.passed
    assert any("close" in f.lower() for f in report.hard_failures)


def test_price_out_of_bounds_is_hard_failure(synthetic_ohlcv):
    report = check_integrity(synthetic_ohlcv(issues={"price_out_of_bounds"}), "1m")
    assert not report.passed
    assert any("bound" in f.lower() or "price" in f.lower() for f in report.hard_failures)


# ---------------------------------------------------------------------------
# Synthetic data — soft observations (must not flip passed)
# ---------------------------------------------------------------------------

def test_gap_is_soft(synthetic_ohlcv):
    report = check_integrity(synthetic_ohlcv(rows=20, issues={"gap"}), "1m")
    assert report.passed
    assert len(report.gaps) == 1
    assert report.gaps[0].n_missing == 1


def test_nan_in_volume_is_soft(synthetic_ohlcv):
    report = check_integrity(synthetic_ohlcv(issues={"nan_in_volume"}), "1m")
    assert report.passed
    assert report.nan_counts.get("volume", 0) > 0


def test_report_counts_are_zero_on_clean(synthetic_ohlcv):
    report = check_integrity(synthetic_ohlcv(), "1m")
    assert report.n_duplicates == 0
    assert report.ohlc_violation_count == 0
    assert report.zero_volume_count == 0
    assert report.gaps == []


# ---------------------------------------------------------------------------
# Real data — loads and passes integrity
# ---------------------------------------------------------------------------

@pytest.mark.skipif(
    not (Settings().raw_dir / "btcusdt_15m.parquet").exists(),
    reason="Real 15m Parquet not present",
)
def test_real_15m_passes_integrity():
    settings = Settings()
    df = load_ohlcv("15m", settings)
    report = check_integrity(df, "15m")

    print(f"\n15m integrity: {report.n_rows} rows, "
          f"{len(report.gaps)} gap(s), "
          f"zero-vol={report.zero_volume_count}, "
          f"ohlc-equal={report.ohlc_equal_count}")
    if report.gaps:
        print(f"  Largest gap: {max(g.n_missing for g in report.gaps)} missing bars")

    assert report.passed, (
        f"15m integrity failed — document in LEARNINGS.md:\n{report.hard_failures}"
    )
