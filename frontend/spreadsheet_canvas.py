"""A compact Excel-like canvas for controlled workpaper review edits.

The browser component intentionally presents the familiar spreadsheet surface;
the Python revision layer remains the authority for validation and export.
"""

from __future__ import annotations

from typing import Any

import streamlit as st


DISPLAY_FIELDS = (
    "Account",
    "ITR Ref",
    "Confidence",
    "Tab 3 decision",
    "Mapping reason",
    "Review note",
)
EDITABLE_FIELDS = ("ITR Ref", "Confidence", "Review note")

_CANVAS_HTML = """
<div id="spreadsheet-shell">
  <div class="toolbar"><span>↶</span><span>↷</span><span class="divider"></span>
    <strong>Workpaper review</strong><span class="hint">Double-click an editable cell</span></div>
  <div class="grid-wrap"><table id="spreadsheet-grid"></table></div>
  <div class="sheet-bar"><span class="sheet-tab active">Current worksheet</span></div>
</div>
"""

_CANVAS_CSS = """
:host { display: block; }
#spreadsheet-shell { border: 1px solid #cbd5e1; border-radius: 8px; overflow: hidden;
  background: #fff; box-shadow: 0 1px 3px rgba(15,23,42,.08); font-family: Arial, sans-serif; }
.toolbar { height: 38px; display: flex; align-items: center; gap: 13px; padding: 0 13px;
  background: #f8fafc; border-bottom: 1px solid #cbd5e1; color: #334155; font-size: 13px; }
.toolbar span { color: #64748b; font-size: 17px; }.toolbar .divider { height: 18px; width: 1px; background: #cbd5e1; }
.toolbar .hint { margin-left: auto; font-size: 12px; color: #64748b; }
.grid-wrap { max-height: 560px; overflow: auto; background: #fff; }
table { border-collapse: separate; border-spacing: 0; width: max-content; min-width: 100%; font-size: 13px; color: #0f172a; }
th, td { border-right: 1px solid #e2e8f0; border-bottom: 1px solid #e2e8f0; padding: 0 8px;
  height: 28px; min-width: 112px; max-width: 360px; box-sizing: border-box; white-space: nowrap;
  overflow: hidden; text-overflow: ellipsis; background: white; }
thead th { position: sticky; top: 0; z-index: 3; height: 29px; background: #f1f5f9;
  color: #475569; font-size: 11px; font-weight: 600; text-align: center; }
.row-number { position: sticky; left: 0; z-index: 2; min-width: 44px; width: 44px; max-width: 44px;
  text-align: right; color: #64748b; background: #f8fafc; font-size: 11px; }
thead .row-number { z-index: 5; }
.account { position: sticky; left: 44px; z-index: 1; min-width: 220px; width: 220px; background: #fff; }
thead .account { z-index: 4; background: #f1f5f9; }
td.editable { background: #fffdf1; cursor: cell; }
td.editable:hover { outline: 2px solid #22c55e; outline-offset: -2px; z-index: 2; }
td.editing { outline: 2px solid #2563eb; outline-offset: -2px; white-space: normal; overflow: visible; }
.sheet-bar { height: 34px; display: flex; align-items: end; gap: 6px; padding: 0 10px; background: #f8fafc; }
.sheet-tab { padding: 8px 14px 7px; font-size: 12px; border: 1px solid #cbd5e1; border-bottom: 0;
  border-radius: 5px 5px 0 0; background: #fff; color: #334155; }
.sheet-tab.active { border-top: 3px solid #16a34a; padding-top: 5px; font-weight: 600; }
"""

_CANVAS_JS = """
export default function({ parentElement, data, setStateValue }) {
  const root = parentElement.querySelector('#spreadsheet-shell');
  const table = parentElement.querySelector('#spreadsheet-grid');
  const rows = data?.rows || [];
  const fields = data?.fields || [];
  const editable = new Set(data?.editable_fields || []);
  const edits = new Map(Object.entries(data?.edits || {}));
  const identity = JSON.stringify({ rows, fields, edits: Object.fromEntries(edits) });
  if (root.dataset.identity === identity) return;
  root.dataset.identity = identity;
  table.replaceChildren();

  const letter = (index) => {
    let value = index + 1, result = '';
    while (value) { const rest = (value - 1) % 26; result = String.fromCharCode(65 + rest) + result; value = Math.floor((value - 1) / 26); }
    return result;
  };
  const thead = document.createElement('thead'); const header = document.createElement('tr');
  const corner = document.createElement('th'); corner.className = 'row-number'; header.appendChild(corner);
  fields.forEach((field, index) => { const th = document.createElement('th'); th.textContent = `${letter(index)}  ${field}`; if (field === 'Account') th.className = 'account'; header.appendChild(th); });
  thead.appendChild(header); table.appendChild(thead);
  const tbody = document.createElement('tbody');
  rows.forEach((row) => {
    const tr = document.createElement('tr'); const rowNumber = document.createElement('td'); rowNumber.className = 'row-number'; rowNumber.textContent = row['Excel row']; tr.appendChild(rowNumber);
    fields.forEach((field) => {
      const cell = document.createElement('td'); const key = `${row['Excel row']}::${field}`;
      cell.textContent = edits.has(key) ? edits.get(key) : (row[field] ?? '');
      cell.title = cell.textContent;
      if (field === 'Account') cell.classList.add('account');
      if (editable.has(field)) {
        cell.classList.add('editable');
        cell.ondblclick = () => { cell.contentEditable = 'true'; cell.classList.add('editing'); cell.focus(); };
        cell.onkeydown = (event) => { if (event.key === 'Enter') { event.preventDefault(); cell.blur(); } if (event.key === 'Escape') { cell.textContent = edits.has(key) ? edits.get(key) : (row[field] ?? ''); cell.blur(); } };
        cell.onblur = () => { cell.contentEditable = 'false'; cell.classList.remove('editing'); const next = cell.textContent.trim(); const base = String(row[field] ?? '').trim(); if (next === base) edits.delete(key); else edits.set(key, next); setStateValue('edits', Object.fromEntries(edits)); };
      }
      tr.appendChild(cell);
    });
    tbody.appendChild(tr);
  });
  table.appendChild(tbody);
}
"""

_spreadsheet_canvas = st.components.v2.component(
    "workpaper_spreadsheet_canvas",
    html=_CANVAS_HTML,
    css=_CANVAS_CSS,
    js=_CANVAS_JS,
)


def merge_canvas_edits(
    rows: list[dict[str, Any]],
    edits: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    """Apply only known editable canvas fields to a copy of review rows."""

    merged = [dict(row) for row in rows]
    by_row = {str(row["Excel row"]): row for row in merged}
    for key, value in (edits or {}).items():
        try:
            row_id, field = str(key).split("::", maxsplit=1)
        except ValueError:
            continue
        row = by_row.get(row_id)
        if row is not None and field in EDITABLE_FIELDS:
            row[field] = str(value or "").strip()
    return merged


def render_spreadsheet_canvas(
    rows: list[dict[str, Any]],
    *,
    key: str,
) -> list[dict[str, Any]]:
    """Render the spreadsheet surface and return locally edited review rows."""

    state = st.session_state.get(key, {})
    previous_edits = state.get("edits", {}) if isinstance(state, dict) else {}
    result = _spreadsheet_canvas(
        key=key,
        data={
            "rows": rows,
            "fields": list(DISPLAY_FIELDS),
            "editable_fields": list(EDITABLE_FIELDS),
            "edits": previous_edits,
        },
        default={"edits": previous_edits},
        # Streamlit v2 accepts a default state only when its corresponding
        # callback is declared. The state itself is read from Session State on
        # the next rerun; no Python-side mutation is needed here.
        on_edits_change=lambda: None,
        height=640,
    )
    result_edits = getattr(result, "edits", previous_edits)
    return merge_canvas_edits(rows, result_edits)
