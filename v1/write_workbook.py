# v1/write_workbook.py
"""Write the final Excel workbook while preserving raw Xero evidence sheets."""

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

from config import (
    BS_RAW_PATH,
    OUTPUT_PATH,
    PL_RAW_PATH,
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

RED_FONT = Font(color="FF0000", bold=True, size=12)
TITLE_FONT = Font(bold=True, size=12)
HEADER_FONT = Font(bold=True, size=12)
BOLD_FONT = Font(bold=True, size=12)
NOTE_FONT = Font(italic=True, color="666666", size=12)

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


def _copy_sheet_to_workbook(src_path: str | Path, dst_wb: Workbook, title: str):
    src_wb = load_workbook(src_path, data_only=False)
    src_ws = src_wb.worksheets[0]
    dst_ws = dst_wb.create_sheet(title)

    for row in src_ws.iter_rows():
        for src_cell in row:
            _copy_cell(src_cell, dst_ws.cell(src_cell.row, src_cell.column))

    for col_letter, dim in src_ws.column_dimensions.items():
        dst_ws.column_dimensions[col_letter].width = dim.width

    for row_idx, dim in src_ws.row_dimensions.items():
        dst_ws.row_dimensions[row_idx].height = dim.height

    for merged_range in src_ws.merged_cells.ranges:
        dst_ws.merge_cells(str(merged_range))

    return dst_ws


def _copy_report_area(
    src_path: str | Path,
    dst_ws,
    start_row: int,
    start_col: int,
    copy_formulas: bool = True,
) -> tuple[int, int]:
    src_wb = load_workbook(src_path, data_only=False)
    src_ws = src_wb.worksheets[0]

    for row in src_ws.iter_rows():
        for src_cell in row:
            dst_cell = dst_ws.cell(
                start_row + src_cell.row - 1,
                start_col + src_cell.column - 1,
            )

            if copy_formulas and isinstance(src_cell.value, str) and src_cell.value.startswith("="):
                dst_cell.value = Translator(
                    src_cell.value,
                    origin=src_cell.coordinate,
                ).translate_formula(dst_cell.coordinate)
            else:
                dst_cell.value = src_cell.value

            _copy_style(src_cell, dst_cell)

    for col_idx in range(1, src_ws.max_column + 1):
        src_letter = get_column_letter(col_idx)
        dst_letter = get_column_letter(start_col + col_idx - 1)
        dst_ws.column_dimensions[dst_letter].width = src_ws.column_dimensions[src_letter].width or 12

    for row_idx, dim in src_ws.row_dimensions.items():
        dst_ws.row_dimensions[start_row + row_idx - 1].height = dim.height

    for merged_range in src_ws.merged_cells.ranges:
        min_col, min_row, max_col, max_row = merged_range.bounds
        dst_ws.merge_cells(
            start_row=start_row + min_row - 1,
            start_column=start_col + min_col - 1,
            end_row=start_row + max_row - 1,
            end_column=start_col + max_col - 1,
        )

    return start_row + src_ws.max_row - 1, start_col + src_ws.max_column - 1


def _safe(value):
    return None if pd.isna(value) else value


def _is_number(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _write_side_labels(
    ws,
    labelled_df: pd.DataFrame,
    source_start_row: int,
    itr_col: int,
    review_col: int,
) -> None:
    ws.cell(source_start_row, itr_col, "ITR Ref")
    ws.cell(source_start_row, review_col, "Review note")

    for cell in (ws.cell(source_start_row, itr_col), ws.cell(source_start_row, review_col)):
        cell.font = RED_FONT
        cell.fill = HEADER_FILL
        cell.alignment = Alignment(horizontal="center", wrap_text=True)

    for _, row in labelled_df.iterrows():
        source_row = row.get("Source Row")

        if pd.isna(source_row):
            continue

        row_type = str(row.get("Row Type", "")).lower()
        if row_type not in {"account", "total"}:
            continue

        itr_ref = str(row.get("ITR Ref", "") or "").strip()
        review_note = str(row.get("Review Note", "") or "").strip()
        label_reason = str(row.get("Label Reason", "") or "").strip()
        confidence = str(row.get("Confidence", "") or "").lower()

        if not itr_ref and not review_note and not label_reason:
            continue

        excel_row = source_start_row + int(source_row) - 1

        visible_note = review_note
        if label_reason and confidence in {"medium", "low"}:
            visible_note = f"{review_note} {label_reason}".strip()

        itr_cell = ws.cell(excel_row, itr_col, itr_ref)
        note_cell = ws.cell(excel_row, review_col, visible_note)

        if itr_ref:
            itr_cell.font = RED_FONT

        if confidence in {"medium", "low"}:
            itr_cell.fill = REVIEW_FILL
            note_cell.fill = REVIEW_FILL

        note_cell.alignment = Alignment(wrap_text=True, vertical="top")


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
        cell.alignment = Alignment(horizontal="center", wrap_text=True)

    for r_idx, (_, row) in enumerate(df.iterrows(), start=header_row + 1):
        line_type = str(row.get("Line Type", "")).lower()

        for c_idx, col_name in enumerate(display_cols):
            value = _safe(row[col_name])
            cell = ws.cell(r_idx, start_col + c_idx, value)
            cell.alignment = Alignment(vertical="top", wrap_text=True)

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


def _write_simple_table(
    ws,
    df: pd.DataFrame,
    title: str,
    start_row: int,
    start_col: int,
    input_table: bool = False,
) -> tuple[int, int]:
    if df is None or df.empty:
        ws.cell(start_row, start_col, title)
        return start_row, start_col

    last_col = start_col + len(df.columns) - 1

    for col in range(start_col, last_col + 1):
        ws.cell(start_row, col).fill = TITLE_FILL
        ws.cell(start_row, col).font = TITLE_FONT

    ws.cell(start_row, start_col, title)

    header_row = start_row + 1

    for idx, col_name in enumerate(df.columns):
        cell = ws.cell(header_row, start_col + idx, str(col_name))
        cell.fill = HEADER_FILL
        cell.font = HEADER_FONT
        cell.alignment = Alignment(horizontal="center", wrap_text=True)

    for r_idx, (_, row) in enumerate(df.iterrows(), start=header_row + 1):
        for c_idx, col_name in enumerate(df.columns):
            value = _safe(row[col_name])
            cell = ws.cell(r_idx, start_col + c_idx, value)
            cell.alignment = Alignment(vertical="top", wrap_text=True)
            cell.border = THIN_BORDER

            if input_table and value is None:
                cell.fill = INPUT_FILL

            if _is_number(value):
                cell.number_format = '$#,##0.00;($#,##0.00);-'

    for c_idx, col_name in enumerate(df.columns, start=start_col):
        ws.column_dimensions[get_column_letter(c_idx)].width = min(max(12, len(str(col_name)) + 4), 28)

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


def write_workbook(raw_pl_df, raw_bs_df, workpaper) -> None:
    logger.info("Writing workbook to %s", OUTPUT_PATH)

    wb = Workbook()
    wb.remove(wb.active)

    _copy_sheet_to_workbook(PL_RAW_PATH, wb, SHEET_PL_RAW)
    _copy_sheet_to_workbook(BS_RAW_PATH, wb, SHEET_BS_RAW)

    ws = wb.create_sheet(SHEET_RECONCILIATION)

    pl_start_row = 1
    pl_last_row, pl_last_col = _copy_report_area(PL_RAW_PATH, ws, pl_start_row, 1, copy_formulas=True)

    bs_start_row = pl_last_row + 3
    bs_last_row, bs_last_col = _copy_report_area(BS_RAW_PATH, ws, bs_start_row, 1, copy_formulas=True)

    raw_last_col = max(pl_last_col, bs_last_col)

    itr_col = raw_last_col + 2
    review_col = raw_last_col + 3

    _write_side_labels(ws, workpaper.labelled_pl, pl_start_row, itr_col, review_col)
    _write_side_labels(ws, workpaper.labelled_bs, bs_start_row, itr_col, review_col)

    _write_bs_checks(ws, workpaper.bs_checks, bs_last_row + 2, 1)

    tax_start_col = review_col + 3
    _, tax_last_col = _write_tax_reconciliation_table(
        ws,
        workpaper.tax_reconciliation,
        "Tax Reconciliation",
        1,
        tax_start_col,
    )

    support_start_col = tax_last_col + 2

    current_row, _ = _write_simple_table(
        ws,
        workpaper.carry_forward_losses,
        "Carry Forward Losses",
        1,
        support_start_col,
        input_table=True,
    )

    current_row, _ = _write_simple_table(
        ws,
        workpaper.rd_breakdown,
        "R&D Breakdown",
        current_row + 3,
        support_start_col,
        input_table=True,
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

    _format_sheet(ws, raw_last_col)
    _force_font_size_9(ws)

    wb.calculation.fullCalcOnLoad = True
    wb.calculation.forceFullCalc = True
    wb.calculation.calcMode = "auto"

    Path(OUTPUT_PATH).parent.mkdir(parents=True, exist_ok=True)
    wb.save(OUTPUT_PATH)

    logger.info("Workbook saved: %s", OUTPUT_PATH)