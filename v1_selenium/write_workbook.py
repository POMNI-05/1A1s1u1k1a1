import logging
import pandas as pd
from openpyxl import load_workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

from config import OUTPUT_PATH

logger = logging.getLogger(__name__)

HEADER_FILL = PatternFill("solid", fgColor="D9EAF7")
REVIEW_FILL = PatternFill("solid", fgColor="FFF2CC")
HEADER_FONT = Font(bold=True)
BOLD_FONT = Font(bold=True)
THIN_BORDER = Border(bottom=Side(style="thin", color="BFBFBF"))


def write_workbook(raw_pl_df, raw_bs_df, tax_rec_df):
    logger.info(f"Writing simplified workbook to {OUTPUT_PATH}...")

    with pd.ExcelWriter(OUTPUT_PATH, engine="openpyxl") as writer:
        raw_pl_df.to_excel(
            writer,
            sheet_name="Xero PL Raw",
            index=False,
            header=False,
        )

        raw_bs_df.to_excel(
            writer,
            sheet_name="Xero BS Raw",
            index=False,
            header=False,
        )

        tax_rec_df.to_excel(
            writer,
            sheet_name="Tax Reconciliation",
            index=False,
        )

    _format_workbook()
    logger.info(f"Workbook saved: {OUTPUT_PATH}")


def _format_workbook():
    wb = load_workbook(OUTPUT_PATH)

    for ws in wb.worksheets:
        is_raw = ws.title in ("Xero PL Raw", "Xero BS Raw")

        if not is_raw:
            for cell in ws[1]:
                cell.font = HEADER_FONT
                cell.fill = HEADER_FILL
                cell.alignment = Alignment(horizontal="left")

        ws.freeze_panes = "A2"

        for row in ws.iter_rows():
            row_text = " ".join(str(cell.value or "") for cell in row)

            if "Review" in row_text or "manual adjustment" in row_text.lower():
                for cell in row:
                    cell.fill = REVIEW_FILL

            if "Taxable Income" in row_text or "Estimated Tax Payable" in row_text:
                for cell in row:
                    cell.font = BOLD_FONT
                    cell.border = THIN_BORDER

        for col in ws.columns:
            max_len = max(
                (len(str(cell.value)) for cell in col if cell.value is not None),
                default=10,
            )
            ws.column_dimensions[get_column_letter(col[0].column)].width = min(max_len + 4, 60)

        for row in ws.iter_rows():
            for cell in row:
                cell.alignment = Alignment(vertical="top", wrap_text=True)

    wb.save(OUTPUT_PATH)