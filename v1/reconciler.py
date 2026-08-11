# v1/reconciler.py
"""Backward-compatible facade for older scripts."""
from __future__ import annotations

try:
    from .workpaper_builder import build_workpaper
    from .write_workbook import write_workbook
except ImportError:  # Direct-script compatibility.
    from workpaper_builder import build_workpaper
    from write_workbook import write_workbook


def build_reconciliation(pl_df=None, bs_df=None):
    """Deprecated: returns the tax_reconciliation block from build_workpaper()."""
    return build_workpaper().tax_reconciliation
