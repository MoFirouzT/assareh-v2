"""Label construction (Phase B.1) and diagnostics (Phase B.2)."""

from assareh.labels.diagnostics import breakeven_precost, target_stats
from assareh.labels.targets import LABEL_SCHEMA, LabelResult, make_labels

__all__ = [
    "LABEL_SCHEMA",
    "LabelResult",
    "breakeven_precost",
    "make_labels",
    "target_stats",
]
