# v1_selenium/cleaner.py

import pandas as pd
import logging
from config import PL_RAW_PATH, BS_RAW_PATH

logger = logging.getLogger(__name__)

# ── Alias lists ───────────────────────────────────────────────────────────────
NET_PROFIT_ALIASES = [
    "net profit",
    "profit / loss",
    "profit after tax",
    "profit (loss)",
    "net income",
    "operating profit",
    "total income",
]

TOTAL_ASSETS_ALIASES = [
    "total assets",
    "assets total",
]

TOTAL_LIABILITIES_ALIASES = [
    "total liabilities",
    "liabilities total",
    "net assets",
]


# ── Header检测 ────────────────────────────────────────────────────────────────
# 原注释版：nrows=20，扫描上限太低
# 修复：改成nrows=30，兜底从row 0开始而不是崩溃
def find_data_start_row(filepath: str) -> int:
    preview = pd.read_excel(filepath, header=None, nrows=30)  # 原版20，改30
    for i, row in preview.iterrows():
        row_values = [str(x).lower() for x in row.tolist()]
        if any(kw in val for val in row_values for kw in ["account", "description"]):
            logger.info(f"Data starts at row {i} in {filepath}")
            return i
    logger.warning("Could not detect header row, defaulting to row 0")
    return 0


# ── 金额清洗 ──────────────────────────────────────────────────────────────────
# 原注释版：regex处理括号和$，但replace只处理了 '-'、''、'nan'
# 修复：加 '--'（双短横，Xero有时出现）；同时处理全角字符
def clean_amount_column(series: pd.Series) -> pd.Series:
    s = series.astype(str).str.strip()
    s = s.str.replace(r'[\$,]', '', regex=True)
    s = s.str.replace(r'^\((.+)\)$', r'-\1', regex=True)   # (1234) → -1234
    s = s.replace({'-': '0', '--': '0', '': '0', 'nan': '0', 'None': '0'})
    return pd.to_numeric(s, errors='coerce').fillna(0.0)


# ── 单值提取（原注释版没有这个函数）────────────────────────────────────────────
# 原激活版完全没有提取逻辑，workpaper_builder里的TODO就是因为这里缺失
def clean_amount(val) -> float:
    """单个值的清洗，供extract_value用"""
    s = str(val).strip().replace(",", "").replace("$", "").replace(" ", "")
    if s.startswith("(") and s.endswith(")"):
        s = "-" + s[1:-1]
    s = s.replace("--", "0").replace("-", "0") if s in ("-", "--") else s
    try:
        return float(s)
    except ValueError:
        return 0.0


def _detect_amount_col(df: pd.DataFrame) -> str:
    """扫描列，找第一个数值密度>50%的列"""
    for col in df.columns[1:]:
        numeric_count = pd.to_numeric(
            df[col].astype(str).str.replace(",", "").str.replace("$", ""),
            errors="coerce"
        ).notna().sum()
        if numeric_count > len(df) * 0.5:
            return col
    logger.warning("Could not detect amount column — using last column")
    return df.columns[-1]


def extract_value(df: pd.DataFrame, aliases: list, amount_col: str = None) -> float | None:
    """
    按alias列表搜索account name列，返回第一个非零匹配值。
    找不到返回None（不是0.0），让调用方区分"真零"和"没找到"。
    """
    if amount_col is None:
        amount_col = _detect_amount_col(df)
    name_col = df.columns[0]
    for alias in aliases:
        mask = df[name_col].astype(str).str.lower().str.contains(alias, na=False)
        matches = df[mask]
        if not matches.empty:
            val = clean_amount(matches.iloc[-1][amount_col])  # 取最后一行避开subtotal
            if val != 0.0:
                logger.debug(f"extract_value: matched '{alias}' → {val}")
                return val
    return None


# ── Account名标准化（原注释版已有，直接激活）────────────────────────────────
def standardise_account_names(series: pd.Series) -> pd.Series:
    return series.astype(str).str.strip().str.title()


# ── 合计行校验（原注释版已有，直接激活）─────────────────────────────────────
def validate_totals(df: pd.DataFrame, amount_col: str, label: str):
    total_rows = df[df.iloc[:, 0].astype(str).str.lower().str.startswith("total")]
    if total_rows.empty:
        logger.warning(f"{label}: No 'Total' rows found to validate.")
        return
    logger.info(f"{label}: Found {len(total_rows)} total row(s) — manual review recommended.")


# ── 核心清洗函数（原注释版已有，nrows扫描上限修复后可以激活）──────────────────
def clean_report(filepath: str, report_label: str) -> pd.DataFrame:
    logger.info(f"Cleaning {report_label} from {filepath}...")
    start_row = find_data_start_row(filepath)
    df = pd.read_excel(filepath, header=start_row)
    df.dropna(how="all", inplace=True)
    df.dropna(axis=1, how="all", inplace=True)
    df.reset_index(drop=True, inplace=True)
    first_col = df.columns[0]
    df[first_col] = standardise_account_names(df[first_col])
    for col in df.columns[1:]:
        df[col] = clean_amount_column(df[col])
    validate_totals(df, df.columns[1], report_label)
    logger.info(f"✓ {report_label} cleaned — {len(df)} rows")
    return df


# ── 对外接口 ──────────────────────────────────────────────────────────────────
# 原激活版：load_raw_reports()用header=None原样读入，完全不处理
# 修复后：load_raw_reports()保持原样（给write_workbook用的raw sheet）
#         load_clean_reports()走clean_report()，给reconciler和workpaper用
def load_raw_reports() -> tuple[pd.DataFrame, pd.DataFrame]:
    """给write_workbook用 — 保留原始Xero格式，不处理"""
    import os
    from config import PL_RAW_PATH, BS_RAW_PATH
    if not os.path.exists(PL_RAW_PATH):
        raise FileNotFoundError(f"P&L not found: {PL_RAW_PATH}")
    if not os.path.exists(BS_RAW_PATH):
        raise FileNotFoundError(f"BS not found: {BS_RAW_PATH}")
    raw_pl = pd.read_excel(PL_RAW_PATH, header=None)
    raw_bs = pd.read_excel(BS_RAW_PATH, header=None)
    logger.info(f"Raw P&L: {len(raw_pl)} rows | Raw BS: {len(raw_bs)} rows")
    return raw_pl, raw_bs


def load_clean_reports() -> tuple[pd.DataFrame, pd.DataFrame]:
    """给reconciler/workpaper_builder用 — 走完整清洗流程"""
    pl_df = clean_report(PL_RAW_PATH, "Profit and Loss")
    bs_df = clean_report(BS_RAW_PATH, "Balance Sheet")
    return pl_df, bs_df