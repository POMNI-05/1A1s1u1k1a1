# v1/write_workbook.py
"""Write the final Excel workbook while preserving raw report evidence values.

This writer is input-source flexible:
- P&L and BS may come from separate workbooks;
- or from different sheets in one combined workbook.

Note:
- This version preserves raw values, not original Excel styling/formulas.
- If exact source styling/formulas must be preserved, use source_path + sheet_name
  metadata from cleaner.ReportInput and copy with openpyxl from the original sheet.
"""

from __future__ import annotations

import copy
import logging
import re
from pathlib import Path

import pandas as pd
from openpyxl import Workbook, load_workbook
from openpyxl.formula.translate import Translator
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

try:
    from .cleaner import ReportInput
    from .config import (
        OUTPUT_PATH,
        SHEET_BS_RAW,
        SHEET_PL_RAW,
        SHEET_RECONCILIATION,
    )
except ImportError:  # Direct-script compatibility.
    from cleaner import ReportInput
    from config import (
        OUTPUT_PATH,
        SHEET_BS_RAW,
        SHEET_PL_RAW,
        SHEET_RECONCILIATION,
    )

logger = logging.getLogger(__name__)

TITLE_FILL = PatternFill("solid", fgColor="B4C6E7")
HEADER_FILL = PatternFill("solid", fgColor="D9EAF7")
SECTION_FILL = PatternFill("solid", fgColor="FFFF00")
REVIEW_FILL = PatternFill("solid", fgColor="FFF2CC")
RESULT_FILL = PatternFill("solid", fgColor="D9E2F3")
INPUT_FILL = PatternFill("solid", fgColor="E2F0D9")

RED_FONT = Font(color="FF0000", bold=True, size=9)
TITLE_FONT = Font(bold=True, size=9)
HEADER_FONT = Font(bold=True, size=9)
BOLD_FONT = Font(bold=True, size=9)
NOTE_FONT = Font(italic=True, color="666666", size=9)
REVIEW_NOTE_FONT = Font(size=9)

THIN_BORDER = Border(bottom=Side(style="thin", color="BFBFBF"))
THICK_BORDER = Border(bottom=Side(style="medium", color="000000"))


def _font_with_size(font_obj, size: int = 12) -> Font:
    return Font(
        name=font_obj.name,
        sz=size,
        b=font_obj.b,
        i=font_obj.i,
        u=font_obj.u,
        strike=font_obj.strike,
        color=copy.copy(font_obj.color),
        vertAlign=font_obj.vertAlign,
        charset=font_obj.charset,
        family=font_obj.family,
        scheme=font_obj.scheme,
        outline=font_obj.outline,
        shadow=font_obj.shadow,
        condense=font_obj.condense,
        extend=font_obj.extend,
    )


def _force_font_size_9(ws) -> None:
    for row in ws.iter_rows():
        for cell in row:
            cell.font = _font_with_size(cell.font, 9)


def _safe(value):
    return None if pd.isna(value) else value


def _is_number(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _write_raw_df_to_sheet(wb: Workbook, raw_df: pd.DataFrame, title: str):
    ws = wb.create_sheet(title)
    for r_idx, row in enumerate(raw_df.itertuples(index=False, name=None), start=1):
        for c_idx, value in enumerate(row, start=1):
            ws.cell(r_idx, c_idx, _safe(value))

    for col_idx in range(1, ws.max_column + 1):
        ws.column_dimensions[get_column_letter(col_idx)].width = 14

    return ws


def _copy_raw_df_area(
    raw_df: pd.DataFrame,
    dst_ws,
    start_row: int,
    start_col: int,
) -> tuple[int, int]:
    for r_idx, row in enumerate(raw_df.itertuples(index=False, name=None), start=start_row):
        for c_idx, value in enumerate(row, start=start_col):
            dst_ws.cell(r_idx, c_idx, _safe(value))

    last_row = start_row + max(len(raw_df), 1) - 1
    last_col = start_col + max(len(raw_df.columns), 1) - 1

    for col_idx in range(start_col, last_col + 1):
        dst_ws.column_dimensions[get_column_letter(col_idx)].width = 14

    return last_row, last_col

def _get_source_ws(report_input: ReportInput):
    src_wb = load_workbook(report_input.source_path, data_only=False)

    if report_input.sheet_name in src_wb.sheetnames:
        return src_wb, src_wb[report_input.sheet_name]

    try:
        idx = int(report_input.sheet_name)
        return src_wb, src_wb.worksheets[idx]
    except Exception as exc:
        raise KeyError(
            f"Could not find sheet {report_input.sheet_name!r} in {report_input.source_path}"
        ) from exc


def _copy_style(src, dst) -> None:
    if src.has_style:
        dst.font = copy.copy(src.font)
        dst.fill = copy.copy(src.fill)
        dst.border = copy.copy(src.border)
        dst.alignment = copy.copy(src.alignment)
        dst.number_format = src.number_format
        dst.protection = copy.copy(src.protection)


def _copy_cell(src, dst) -> None:
    dst.value = src.value
    _copy_style(src, dst)

    if src.hyperlink:
        dst._hyperlink = copy.copy(src.hyperlink)

    if src.comment:
        dst.comment = copy.copy(src.comment)


def _copy_cell_translated(src, dst, copy_formulas: bool = True) -> None:
    if copy_formulas and isinstance(src.value, str) and src.value.startswith("="):
        dst.value = Translator(
            src.value,
            origin=src.coordinate,
        ).translate_formula(dst.coordinate)
    else:
        dst.value = src.value

    _copy_style(src, dst)

    if src.hyperlink:
        dst._hyperlink = copy.copy(src.hyperlink)

    if src.comment:
        dst.comment = copy.copy(src.comment)


def _copy_merged_ranges(src_ws, dst_ws, row_offset: int = 0, col_offset: int = 0) -> None:
    for merged_range in src_ws.merged_cells.ranges:
        min_col, min_row, max_col, max_row = merged_range.bounds

        dst_ws.merge_cells(
            start_row=min_row + row_offset,
            start_column=min_col + col_offset,
            end_row=max_row + row_offset,
            end_column=max_col + col_offset,
        )

def _looks_like_generated_column(src_ws, col_idx: int) -> bool:
    """
    Detect generated helper columns from old output files.

    If a user accidentally uploads a prior generated workbook, we do not want
    the copied Profit and Loss / Balance Sheet evidence tabs to include:
    - ITR Label
    - ITR Ref
    - Review note
    - ITR Totals
    - yellow summary blocks
    """
    values = []

    for row_idx in range(1, min(src_ws.max_row, 40) + 1):
        value = src_ws.cell(row_idx, col_idx).value
        if value is None:
            continue
        values.append(str(value).strip().lower())

    joined = " | ".join(values)

    generated_markers = [
        "itr label",
        "itr ref",
        "itr totals",
        "review note",
        "tax reconciliation",
        "total income",
        "total expenses",
        "pre tax profit",
        "pre tax profit/(loss)",
    ]

    return any(marker in joined for marker in generated_markers)

def _copy_sheet_to_workbook(report_input: ReportInput, dst_wb: Workbook, title: str):
    """
    Copy selected original source sheet into output workbook.

    This version keeps the raw evidence sheet clean. If the source file is
    accidentally a previous generated output workbook, it skips generated
    helper columns such as ITR Label / ITR Totals / Review note.
    """
    _, src_ws = _get_source_ws(report_input)
    dst_ws = dst_wb.create_sheet(title)

    allowed_cols = [
        col_idx
        for col_idx in range(1, src_ws.max_column + 1)
        if not _looks_like_generated_column(src_ws, col_idx)
    ]

    col_map = {
        old_col_idx: new_col_idx
        for new_col_idx, old_col_idx in enumerate(allowed_cols, start=1)
    }

    for row in src_ws.iter_rows():
        for src_cell in row:
            if src_cell.column not in col_map:
                continue

            dst_cell = dst_ws.cell(src_cell.row, col_map[src_cell.column])
            _copy_cell(src_cell, dst_cell)

    for old_col_idx, new_col_idx in col_map.items():
        src_letter = get_column_letter(old_col_idx)
        dst_letter = get_column_letter(new_col_idx)
        dst_ws.column_dimensions[dst_letter].width = (
            src_ws.column_dimensions[src_letter].width or 12
        )

    for row_idx, dim in src_ws.row_dimensions.items():
        if dim.height is not None:
            dst_ws.row_dimensions[row_idx].height = dim.height

    # Do not copy merged ranges here, because generated columns may be skipped
    # and old merged ranges can become invalid. Raw values/styles are enough.
    dst_ws.freeze_panes = src_ws.freeze_panes
    dst_ws.sheet_view.showGridLines = src_ws.sheet_view.showGridLines

    return dst_ws


def _copy_report_area(
    report_input: ReportInput,
    dst_ws,
    start_row: int,
    start_col: int,
    copy_formulas: bool = True,
) -> tuple[int, int]:
    """Copy selected original report sheet into the reconciliation sheet."""
    _, src_ws = _get_source_ws(report_input)

    row_offset = start_row - 1
    col_offset = start_col - 1

    for row in src_ws.iter_rows():
        for src_cell in row:
            dst_cell = dst_ws.cell(
                row=start_row + src_cell.row - 1,
                column=start_col + src_cell.column - 1,
            )
            _copy_cell_translated(src_cell, dst_cell, copy_formulas=copy_formulas)

    for col_idx in range(1, src_ws.max_column + 1):
        src_letter = get_column_letter(col_idx)
        dst_letter = get_column_letter(start_col + col_idx - 1)
        dst_ws.column_dimensions[dst_letter].width = (
            src_ws.column_dimensions[src_letter].width or 12
        )

    # Preserve source row heights only. Do not auto-resize row height.
    for row_idx, dim in src_ws.row_dimensions.items():
        if dim.height is not None:
            dst_ws.row_dimensions[start_row + row_idx - 1].height = dim.height

    _copy_merged_ranges(src_ws, dst_ws, row_offset=row_offset, col_offset=col_offset)

    return start_row + src_ws.max_row - 1, start_col + src_ws.max_column - 1

def should_highlight_mapping(mapping: dict, report_type: str = "") -> bool:
    itr_ref = str(mapping.get("ITR Ref", "") or "").strip()
    treatment = str(mapping.get("Treatment", "") or "").lower().strip()
    confidence = str(mapping.get("Confidence", "") or "").lower().strip()

    if itr_ref == "Review":
        return True

    if confidence == "low":
        return True

    if report_type == "balance_sheet" and treatment == "support_only":
        return False

    if treatment == "review_only":
        return True

    return False

def _write_side_labels(
    ws,
    labelled_df: pd.DataFrame,
    source_start_row: int,
    itr_col: int,
    review_col: int,
    report_type: str = "",
) -> None:
    ws.cell(source_start_row, itr_col, "ITR Label")
    ws.cell(source_start_row, review_col, "Review note")

    for cell in (ws.cell(source_start_row, itr_col), ws.cell(source_start_row, review_col)):
        cell.font = RED_FONT
        cell.fill = HEADER_FILL
        cell.alignment = Alignment(horizontal="center", vertical="top", wrap_text=False)

    if labelled_df is None or labelled_df.empty:
        return

    for _, row in labelled_df.iterrows():
        source_row = row.get("Source Row")

        if pd.isna(source_row):
            continue

        row_type = str(row.get("Row Type", "") or "").lower().strip()
        if row_type not in {"account", "total"}:
            continue

        itr_ref = str(row.get("ITR Ref", "") or "").strip()
        review_note = str(row.get("Review Note", "") or "").strip()
        label_reason = str(row.get("Label Reason", "") or "").strip()
        confidence = str(row.get("Confidence", "") or "").lower().strip()

        if not itr_ref and not review_note and not label_reason:
            continue

        excel_row = source_start_row + int(source_row) - 1

        visible_note = review_note
        if label_reason and confidence in {"medium", "low"}:
            visible_note = f"{review_note} {label_reason}".strip()

        label_cell = ws.cell(excel_row, itr_col, itr_ref)
        note_cell = ws.cell(excel_row, review_col, visible_note)

        label_cell.font = RED_FONT if itr_ref else REVIEW_NOTE_FONT
        label_cell.alignment = Alignment(vertical="top", wrap_text=False)

        note_cell.font = REVIEW_NOTE_FONT
        note_cell.alignment = Alignment(vertical="top", wrap_text=False)

        if should_highlight_mapping(row.to_dict(), report_type=report_type):
            label_cell.fill = REVIEW_FILL
            note_cell.fill = REVIEW_FILL

def _write_tax_reconciliation_table(
    ws,
    df: pd.DataFrame,
    title: str,
    start_row: int,
    start_col: int,
) -> tuple[int, int]:
    display_cols = [c for c in df.columns if c != "Line Type"]
    last_col = start_col + len(display_cols) - 1

    for col in range(start_col, last_col + 1):
        ws.cell(start_row, col).fill = TITLE_FILL
        ws.cell(start_row, col).font = TITLE_FONT

    ws.cell(start_row, start_col, title)

    header_row = start_row + 1

    for idx, col_name in enumerate(display_cols):
        cell = ws.cell(header_row, start_col + idx, col_name)
        cell.fill = HEADER_FILL
        cell.font = HEADER_FONT
        cell.alignment = Alignment(horizontal="center", wrap_text=False)

    for r_idx, (_, row) in enumerate(df.iterrows(), start=header_row + 1):
        line_type = str(row.get("Line Type", "")).lower()

        for c_idx, col_name in enumerate(display_cols):
            value = _safe(row[col_name])
            cell = ws.cell(r_idx, start_col + c_idx, value)
            cell.alignment = Alignment(vertical="top", wrap_text=False)

            if _is_number(value):
                cell.number_format = '$#,##0.00;($#,##0.00);-'

            if col_name == "ITR Ref" and str(value or "").strip():
                cell.font = RED_FONT

        if line_type == "heading":
            for c in range(start_col, last_col + 1):
                ws.cell(r_idx, c).fill = SECTION_FILL
                ws.cell(r_idx, c).font = BOLD_FONT

        elif line_type == "placeholder":
            for c in range(start_col, last_col + 1):
                ws.cell(r_idx, c).font = NOTE_FONT

        elif line_type == "subtotal":
            for c in range(start_col, last_col + 1):
                ws.cell(r_idx, c).font = BOLD_FONT
                ws.cell(r_idx, c).border = THIN_BORDER

        elif line_type == "result":
            for c in range(start_col, last_col + 1):
                ws.cell(r_idx, c).font = BOLD_FONT
                ws.cell(r_idx, c).border = THICK_BORDER
            ws.cell(r_idx, start_col).fill = RESULT_FILL

        elif line_type == "note":
            for c in range(start_col, last_col + 1):
                ws.cell(r_idx, c).font = NOTE_FONT

    for col in range(start_col, last_col + 1):
        header = str(ws.cell(header_row, col).value or "")
        letter = get_column_letter(col)

        if header == "Description":
            ws.column_dimensions[letter].width = 34
        elif header == "Review note":
            ws.column_dimensions[letter].width = 32
        elif re.search(r"20\d{2}|30 June|30 Jun", header):
            ws.column_dimensions[letter].width = 14
        else:
            ws.column_dimensions[letter].width = 12

    return header_row + len(df), last_col
PL_INCOME_SUMMARY_LABELS = [
    "Inc - 6A",
    "Inc - 6B",
    "Inc - 6C",
    "Inc - 6D",
    "Inc - 6E",
    "Inc - 6X",
    "Inc - 6F",
    "Inc - 6G",
    "Inc - 6H",
    "Inc - 6I",
    "Inc - 6Q",
    "Inc - 6J",
    "Inc - 6R",
]

PL_EXPENSE_SUMMARY_LABELS = [
    "Exp - 6A",
    "Exp - 6C",
    "Exp - 6D",
    "Exp - 6E",
    "Exp - 6F",
    "Exp - 6I",
    "Exp - 6H",
    "Exp - 6V",
    "Exp - 6J",
    "Exp - 6U",
    "Exp - 6W",
    "Exp - 6X",
    "Exp - 6Y",
    "Exp - 6Z",
    "Exp - 6G",
    "Exp - 6S",
]

def _find_main_amount_col(ws, start_row: int, last_row: int, last_col: int) -> int:
    """
    Find the main numeric amount column in the copied report block.

    Usually this is column B, but this is safer than hard-coding B.
    """
    best_col = 2
    best_count = -1

    for col_idx in range(1, last_col + 1):
        count = 0

        for row_idx in range(start_row, last_row + 1):
            value = ws.cell(row_idx, col_idx).value

            if _is_number(value):
                count += 1

        if count > best_count:
            best_count = count
            best_col = col_idx

    return best_col


def _write_pl_formula_summary_table(
    ws,
    title: str,
    start_row: int,
    start_col: int,
    label_col: int,
    amount_col: int,
    data_start_row: int,
    data_last_row: int,
) -> tuple[int, int]:
    """
    Write P&L ITR totals using Excel formulas.

    Formula pattern:
    =SUMIF($<label_col>$start:$<label_col>$end, <summary_label_cell>, $<amount_col>$start:$<amount_col>$end)
    """
    label_letter = get_column_letter(label_col)
    amount_letter = get_column_letter(amount_col)

    label_range = f"${label_letter}${data_start_row}:${label_letter}${data_last_row}"
    amount_range = f"${amount_letter}${data_start_row}:${amount_letter}${data_last_row}"

    label_out_col = start_col
    amount_out_col = start_col + 1

    # Title/header
    ws.cell(start_row, label_out_col, title)
    ws.cell(start_row, label_out_col).fill = SECTION_FILL
    ws.cell(start_row, label_out_col).font = BOLD_FONT

    ws.cell(start_row, amount_out_col, "Amount")
    ws.cell(start_row, amount_out_col).fill = SECTION_FILL
    ws.cell(start_row, amount_out_col).font = BOLD_FONT

    current_row = start_row + 2

    income_amount_cells = []
    expense_amount_cells = []

    # Income section
    ws.cell(current_row, label_out_col, "Income")
    ws.cell(current_row, label_out_col).font = BOLD_FONT
    current_row += 1

    for label in PL_INCOME_SUMMARY_LABELS:
        label_cell = ws.cell(current_row, label_out_col, label)
        amount_cell = ws.cell(current_row, amount_out_col)

        amount_cell.value = f"=SUMIF({label_range},{label_cell.coordinate},{amount_range})"
        amount_cell.number_format = '$#,##0.00;($#,##0.00);-'

        income_amount_cells.append(amount_cell.coordinate)
        current_row += 1

    total_income_row = current_row
    ws.cell(total_income_row, label_out_col, "TOTAL INCOME")
    ws.cell(total_income_row, label_out_col).font = BOLD_FONT
    ws.cell(total_income_row, amount_out_col, f"=SUM({','.join(income_amount_cells)})")
    ws.cell(total_income_row, amount_out_col).number_format = '$#,##0.00;($#,##0.00);-'
    ws.cell(total_income_row, amount_out_col).font = BOLD_FONT

    current_row += 3

    # Expense section
    ws.cell(current_row, label_out_col, "Expenses")
    ws.cell(current_row, label_out_col).font = BOLD_FONT
    current_row += 1

    for label in PL_EXPENSE_SUMMARY_LABELS:
        label_cell = ws.cell(current_row, label_out_col, label)
        amount_cell = ws.cell(current_row, amount_out_col)

        amount_cell.value = f"=SUMIF({label_range},{label_cell.coordinate},{amount_range})"
        amount_cell.number_format = '$#,##0.00;($#,##0.00);-'

        expense_amount_cells.append(amount_cell.coordinate)
        current_row += 1

    total_expense_row = current_row
    ws.cell(total_expense_row, label_out_col, "TOTAL EXPENSES")
    ws.cell(total_expense_row, label_out_col).font = BOLD_FONT
    ws.cell(total_expense_row, amount_out_col, f"=SUM({','.join(expense_amount_cells)})")
    ws.cell(total_expense_row, amount_out_col).number_format = '$#,##0.00;($#,##0.00);-'
    ws.cell(total_expense_row, amount_out_col).font = BOLD_FONT

    current_row += 2

    # Pre-tax profit
    pre_tax_row = current_row
    ws.cell(pre_tax_row, label_out_col, "PRE TAX PROFIT/(LOSS)")
    ws.cell(pre_tax_row, label_out_col).font = BOLD_FONT
    ws.cell(
        pre_tax_row,
        amount_out_col,
        f"={ws.cell(total_income_row, amount_out_col).coordinate}-{ws.cell(total_expense_row, amount_out_col).coordinate}",
    )
    ws.cell(pre_tax_row, amount_out_col).number_format = '$#,##0.00;($#,##0.00);-'
    ws.cell(pre_tax_row, amount_out_col).font = BOLD_FONT

    # Format yellow block
    for row_idx in range(start_row, pre_tax_row + 1):
        for col_idx in range(label_out_col, amount_out_col + 1):
            ws.cell(row_idx, col_idx).fill = SECTION_FILL

    ws.column_dimensions[get_column_letter(label_out_col)].width = 18
    ws.column_dimensions[get_column_letter(amount_out_col)].width = 16

    return pre_tax_row, amount_out_col

def _write_label_summary_table(
    ws,
    df: pd.DataFrame,
    title: str,
    start_row: int,
    start_col: int,
) -> tuple[int, int]:
    """
    Write P&L or BS label summary table.

    This is the system-generated equivalent of the old yellow SUMIF table,
    but safer because it comes from labelled dataframe results rather than
    hard-coded Excel column letters like E:E or F:F.
    """
    if df is None or df.empty:
        ws.cell(start_row, start_col, title)
        ws.cell(start_row + 1, start_col, "No labels detected")
        ws.cell(start_row, start_col).fill = TITLE_FILL
        ws.cell(start_row, start_col).font = TITLE_FONT
        return start_row + 1, start_col

    display_df = df.copy()

    last_col = start_col + len(display_df.columns) - 1

    for col in range(start_col, last_col + 1):
        ws.cell(start_row, col).fill = TITLE_FILL
        ws.cell(start_row, col).font = TITLE_FONT

    ws.cell(start_row, start_col, title)

    header_row = start_row + 1

    for idx, col_name in enumerate(display_df.columns):
        cell = ws.cell(header_row, start_col + idx, col_name)
        cell.fill = HEADER_FILL
        cell.font = HEADER_FONT
        cell.alignment = Alignment(horizontal="center", vertical="top", wrap_text=False)

    for r_idx, (_, row) in enumerate(display_df.iterrows(), start=header_row + 1):
        for c_idx, col_name in enumerate(display_df.columns):
            value = _safe(row[col_name])
            cell = ws.cell(r_idx, start_col + c_idx, value)
            cell.alignment = Alignment(vertical="top", wrap_text=False)
            cell.border = THIN_BORDER

            if col_name == "Amount" and _is_number(value):
                cell.number_format = '$#,##0.00;($#,##0.00);-'

            if col_name == "ITR Ref" and str(value or "").strip():
                cell.font = RED_FONT

            confidence = str(row.get("Confidence", "") or "").lower()
            treatment = str(row.get("Treatment", "") or "").lower()

            if confidence in {"low", "medium"} or treatment == "review_only":
                cell.fill = REVIEW_FILL

    for c_idx, col_name in enumerate(display_df.columns, start=start_col):
        letter = get_column_letter(c_idx)

        if col_name in {"ITR Label", "Review Note"}:
            ws.column_dimensions[letter].width = 34
        elif col_name == "Source Rows":
            ws.column_dimensions[letter].width = 18
        elif col_name == "Amount":
            ws.column_dimensions[letter].width = 16
        else:
            ws.column_dimensions[letter].width = 14

    return header_row + len(display_df), last_col

def _write_simple_table(
    ws,
    df: pd.DataFrame,
    title: str,
    start_row: int,
    start_col: int,
    input_table: bool = False,
) -> tuple[int, int]:
    if df is None or df.empty:
        title_cell = ws.cell(start_row, start_col, title)
        title_cell.fill = TITLE_FILL
        title_cell.font = TITLE_FONT
        return start_row, start_col

    last_col = start_col + len(df.columns) - 1

    for col in range(start_col, last_col + 1):
        cell = ws.cell(start_row, col)
        cell.fill = TITLE_FILL
        cell.font = TITLE_FONT

    ws.cell(start_row, start_col, title)

    header_row = start_row + 1

    for idx, col_name in enumerate(df.columns):
        cell = ws.cell(header_row, start_col + idx, str(col_name))
        cell.fill = HEADER_FILL
        cell.font = HEADER_FONT
        cell.alignment = Alignment(horizontal="center", vertical="top", wrap_text=False)

    for r_idx, (_, row) in enumerate(df.iterrows(), start=header_row + 1):
        for c_idx, col_name in enumerate(df.columns):
            value = _safe(row[col_name])
            cell = ws.cell(r_idx, start_col + c_idx, value)
            cell.alignment = Alignment(vertical="top", wrap_text=False)
            cell.border = THIN_BORDER

            if input_table and value is None:
                cell.fill = INPUT_FILL

            if _is_number(value):
                cell.number_format = '$#,##0.00;($#,##0.00);-'

    for c_idx, col_name in enumerate(df.columns, start=start_col):
        letter = get_column_letter(c_idx)
        lower = str(col_name).strip().lower()

        if lower in {"review note", "reason", "label reason"}:
            ws.column_dimensions[letter].width = 38
        elif lower in {"description", "account", "workpaper label", "itr label"}:
            ws.column_dimensions[letter].width = 30
        elif lower == "source rows":
            ws.column_dimensions[letter].width = 16
        else:
            ws.column_dimensions[letter].width = 14

    return header_row + len(df), last_col

def _write_bs_checks(ws, bs_checks: pd.DataFrame, start_row: int, start_col: int = 1) -> int:
    if bs_checks is None or bs_checks.empty:
        return start_row

    end_row, _ = _write_simple_table(ws, bs_checks, "Balance Sheet Test Checks", start_row, start_col)

    for row in range(start_row + 2, end_row + 1):
        for col in range(start_col, start_col + len(bs_checks.columns)):
            value = ws.cell(row, col).value
            if _is_number(value) and abs(value) > 1:
                ws.cell(row, col).fill = REVIEW_FILL

    return end_row


def _format_sheet(ws, raw_block_last_col: int) -> None:
    ws.freeze_panes = "A2"
    ws.sheet_view.showGridLines = True

    for col_idx in range(raw_block_last_col + 1, ws.max_column + 1):
        letter = get_column_letter(col_idx)
        current = ws.column_dimensions[letter].width or 10
        ws.column_dimensions[letter].width = min(max(current, 10), 40)

    for col_idx in range(raw_block_last_col + 2, raw_block_last_col + 4):
        ws.column_dimensions[get_column_letter(col_idx)].width = 22


def write_workbook(reports, workpaper) -> None:
    logger.info("Writing workbook to %s", OUTPUT_PATH)

    wb = Workbook()
    wb.remove(wb.active)

    # First two sheets: copy the selected original source sheets.
    _copy_sheet_to_workbook(reports.pl_input, wb, SHEET_PL_RAW)
    _copy_sheet_to_workbook(reports.bs_input, wb, SHEET_BS_RAW)

    ws = wb.create_sheet(SHEET_RECONCILIATION)

        # ------------------------------------------------------------------
    # 1. P&L block with side labels
    # ------------------------------------------------------------------
        # ------------------------------------------------------------------
    # 1. P&L block with ITR labels immediately beside P&L
    # ------------------------------------------------------------------
    pl_start_row = 1

    pl_last_row, pl_last_col = _copy_report_area(
        reports.pl_input,
        ws,
        pl_start_row,
        1,
        copy_formulas=True,
    )

    pl_itr_col = pl_last_col + 2
    pl_review_col = pl_last_col + 3

    ws.column_dimensions[get_column_letter(pl_itr_col)].width = 14
    ws.column_dimensions[get_column_letter(pl_review_col)].width = 42

    _write_side_labels(
        ws,
        workpaper.labelled_pl,
        pl_start_row,
        pl_itr_col,
        pl_review_col,
        report_type="profit_and_loss",
    )

    # Formula summary table goes beside the same P&L block.
    # It does not depend on BS length.
    pl_amount_col = _find_main_amount_col(
        ws,
        start_row=pl_start_row,
        last_row=pl_last_row,
        last_col=pl_last_col,
    )

    pl_summary_col = pl_review_col + 2

    pl_summary_last_row, pl_summary_last_col = _write_pl_formula_summary_table(
        ws,
        title="ITR Totals",
        start_row=pl_start_row,
        start_col=pl_summary_col,
        label_col=pl_itr_col,
        amount_col=pl_amount_col,
        data_start_row=pl_start_row,
        data_last_row=pl_last_row,
    )

    # ------------------------------------------------------------------
    # 2. BS block underneath P&L
    # ------------------------------------------------------------------
    bs_start_row = max(pl_last_row, pl_summary_last_row) + 4

    bs_last_row, bs_last_col = _copy_report_area(
        reports.bs_input,
        ws,
        bs_start_row,
        1,
        copy_formulas=True,
    )

    bs_itr_col = bs_last_col + 2
    bs_review_col = bs_last_col + 3

    ws.column_dimensions[get_column_letter(bs_itr_col)].width = 14
    ws.column_dimensions[get_column_letter(bs_review_col)].width = 42

    _write_side_labels(
        ws,
        workpaper.labelled_bs,
        bs_start_row,
        bs_itr_col,
        bs_review_col,
        report_type="balance_sheet",
    )

    # ------------------------------------------------------------------
    # 3. BS checks underneath BS
    # ------------------------------------------------------------------
    bs_checks_start_row = bs_last_row + 3

    bs_checks_last_row = _write_bs_checks(
        ws,
        workpaper.bs_checks,
        bs_checks_start_row,
        1,
    )

    # ------------------------------------------------------------------
    # 4. Final tax reconciliation table underneath BS checks
    # ------------------------------------------------------------------
    tax_start_row = bs_checks_last_row + 4

    tax_last_row, tax_last_col = _write_tax_reconciliation_table(
        ws,
        workpaper.tax_reconciliation,
        "Final Tax Reconciliation",
        tax_start_row,
        1,
    )

    # ------------------------------------------------------------------
    # 5. Support tables beside final tax reconciliation
    # ------------------------------------------------------------------
    support_start_col = tax_last_col + 2

    current_row = tax_start_row - 3

    if workpaper.carry_forward_losses is not None and not workpaper.carry_forward_losses.empty:
        current_row, _ = _write_simple_table(
            ws,
            workpaper.carry_forward_losses,
            "Carry Forward Losses",
            current_row + 3,
            support_start_col,
            input_table=True,
        )

    if workpaper.rd_breakdown is not None and not workpaper.rd_breakdown.empty:
        current_row, _ = _write_simple_table(
            ws,
            workpaper.rd_breakdown,
            "R&D Breakdown",
            current_row + 3,
            support_start_col,
            input_table=True,
        )

    for title, table in getattr(workpaper, "support_tables", {}).items():
        if table is None or table.empty:
            continue
        current_row, _ = _write_simple_table(
            ws,
            table,
            title,
            current_row + 3,
            support_start_col,
            input_table=True,
        )

    proposed = getattr(workpaper, "proposed_adjustments", None)
    if proposed is not None and not proposed.empty:
        current_row, _ = _write_simple_table(
            ws,
            proposed,
            "Proposed Tax Adjustments - Not Posted Unless Approved",
            current_row + 3,
            support_start_col,
            input_table=False,
        )

    if getattr(workpaper, "review_items", None) is not None and not workpaper.review_items.empty:
        _write_simple_table(
            ws,
            workpaper.review_items,
            "Review Items",
            current_row + 3,
            support_start_col,
            input_table=False,
        )

    raw_last_col = max(
        pl_last_col,
        bs_last_col,
        pl_summary_last_col,
        tax_last_col,
    )

    _format_sheet(ws, raw_last_col)
    
    wb.calculation.fullCalcOnLoad = True
    wb.calculation.forceFullCalc = True
    wb.calculation.calcMode = "auto"

    Path(OUTPUT_PATH).parent.mkdir(parents=True, exist_ok=True)
    wb.save(OUTPUT_PATH)

    logger.info("Workbook saved: %s", OUTPUT_PATH)
