# v1_selenium/write_workbook.py
# Writes final accountant-style workbook

import logging
import pandas as pd

from openpyxl import load_workbook
from openpyxl.styles import Font, PatternFill, Alignment
from openpyxl.utils import get_column_letter

from config import OUTPUT_PATH

logger = logging.getLogger(__name__)


def write_workbook(raw_pl_df, raw_bs_df, tax_rec_df, checks_df=None):
    """
    Write final workbook.

    Raw Xero sheets are preserved.
    Tax reconciliation is written separately.
    """

    logger.info(f"Writing workbook to {OUTPUT_PATH}...")

    with pd.ExcelWriter(OUTPUT_PATH, engine="openpyxl") as writer:
        raw_pl_df.to_excel(writer, sheet_name="Xero PL Raw", index=False, header=False)
        raw_bs_df.to_excel(writer, sheet_name="Xero BS Raw", index=False, header=False)
        tax_rec_df.to_excel(writer, sheet_name="Tax Reconciliation", index=False)

        if checks_df is not None:
            checks_df.to_excel(writer, sheet_name="Checks", index=False)

    format_output_workbook()

    logger.info(f"✓ Workbook saved: {OUTPUT_PATH}")


def format_output_workbook():
    """
    Basic formatting only.
    Does not change raw data values.
    """

    wb = load_workbook(OUTPUT_PATH)

    header_fill = PatternFill("solid", fgColor="D9EAF7")
    warning_fill = PatternFill("solid", fgColor="FFCCCC")
    header_font = Font(bold=True)

    for ws in wb.worksheets:
        ws.freeze_panes = "A2"

        # Do NOT format row 1 as header on raw Xero sheets
        if ws.title not in ["Xero PL Raw", "Xero BS Raw"]:
            for cell in ws[1]:
                cell.font = header_font
                cell.fill = header_fill
                cell.alignment = Alignment(horizontal="left")

        for col in ws.columns:
            max_len = max(
                (len(str(cell.value)) for cell in col if cell.value is not None),
                default=10,
            )
            ws.column_dimensions[get_column_letter(col[0].column)].width = min(max_len + 4, 60)

        for row in ws.iter_rows():
            for cell in row:
                if cell.value and "⚠" in str(cell.value):
                    for r in row:
                        r.fill = warning_fill

    wb.save(OUTPUT_PATH)