# v1_selenium/cleaner.py

import os
import logging
import pandas as pd

from config import PL_RAW_PATH, BS_RAW_PATH

logger = logging.getLogger(__name__)

# ── Alias lists ───────────────────────────────────────────────────────────────
# 按优先级排列；extract_value 找到第一个非零匹配就返回
NET_PROFIT_ALIASES = [
    "net profit",
    "profit / loss",
    "profit after tax",
    "profit (loss)",
    "net income",
    "operating profit",
    "total income",          # 最后兜底，不理想但总比None好
]

TOTAL_ASSETS_ALIASES = [
    "total assets",
    "assets total",
]

TOTAL_LIABILITIES_ALIASES = [
    "total liabilities",
    "liabilities total",
    "net assets",            # 有时Xero BS底部只显示net assets
]

# ── 金额清洗 ──────────────────────────────────────────────────────────────────
# 原版：直接 pd.to_numeric，遇到括号负数或$符号就返回NaN
# 新版：先strip符号，把 (1,234.56) 转成 -1234.56，再转float
def clean_amount(val):
    s = str(val).strip().replace(",", "").replace("$", "").replace(" ", "")
    if s.startswith("(") and s.endswith(")"):
        s = "-" + s[1:-1]
    try:
        return float(s)
    except ValueError:
        return 0.0


# ── 动态Header检测 ────────────────────────────────────────────────────────────
# 原版：pd.read_excel(path, header=0)，写死第一行是header
# 新版：先用header=None原样读入，扫描找第一个含"Account"/"Description"的行
def _load_xero_export(path: str, label: str) -> pd.DataFrame:
    if not os.path.exists(path):
        logger.error(f"File not found: {path}")
        raise FileNotFoundError(path)

    raw = pd.read_excel(path, header=None)
    logger.info(f"{label}: loaded {len(raw)} raw rows")

    # 找header行
    header_row_idx = None
    for i, row in raw.iterrows():
        row_lower = [str(v).strip().lower() for v in row]
        if any(k in row_lower for k in ("account", "description")):
            header_row_idx = i
            break

    if header_row_idx is None:
        # 找不到标准header — 用第一行有文字的行兜底，记录警告
        logger.warning(f"{label}: no 'Account'/'Description' header found — using row 0 as fallback")
        header_row_idx = 0

    df = raw.iloc[header_row_idx + 1:].copy()
    df.columns = raw.iloc[header_row_idx].tolist()
    df = df.reset_index(drop=True)

    # 删掉全空行
    df = df.dropna(how="all").reset_index(drop=True)

    logger.info(f"{label}: {len(df)} data rows after header detection (header at row {header_row_idx})")
    return df


# ── 自动找Amount列 ────────────────────────────────────────────────────────────
# 原版：没有这个函数，extract_value假设列名固定
# 新版：扫描所有列，找第一个数值密度>50%的列作为金额列
def _detect_amount_col(df: pd.DataFrame) -> str:
    for col in df.columns[1:]:          # 跳过第一列（account name）
        numeric_count = pd.to_numeric(
            df[col].astype(str).str.replace(",", "").str.replace("$", ""),
            errors="coerce"
        ).notna().sum()
        if numeric_count > len(df) * 0.5:
            return col
    # 兜底：返回最后一列
    logger.warning("Could not detect amount column — using last column")
    return df.columns[-1]


# ── 核心提取函数 ──────────────────────────────────────────────────────────────
# 原版：extract_value(df, "net profit") 单一字符串精确匹配
# 新版：传入alias列表，逐个试，返回第一个非零匹配；找不到返回None（不是0.0）
def extract_value(df: pd.DataFrame, aliases: list, amount_col: str = None) -> float | None:
    if amount_col is None:
        amount_col = _detect_amount_col(df)

    name_col = df.columns[0]

    for alias in aliases:
        mask = df[name_col].astype(str).str.lower().str.contains(alias, na=False)
        matches = df[mask]
        if not matches.empty:
            # 取最后一行：避开subtotal，拿合计行
            val = clean_amount(matches.iloc[-1][amount_col])
            if val != 0.0:
                logger.debug(f"extract_value: matched '{alias}' → {val}")
                return val

    return None  # 明确None，让调用方区分"真零"和"没找到"


# ── 对外接口 ─────────────────────────────────────────────原有的代码里有的────────────
# main.py 调用 load_raw_reports()
# test_local_excel.py 调用 load_clean_reports()（别名，行为相同）
def load_raw_reports() -> tuple[pd.DataFrame, pd.DataFrame]:
    pl_df = _load_xero_export(PL_RAW_PATH, "P&L")
    bs_df = _load_xero_export(BS_RAW_PATH, "Balance Sheet")
    return pl_df, bs_df

def load_clean_reports() -> tuple[pd.DataFrame, pd.DataFrame]:
    # test_local_excel.py 用的是这个名字，保持兼容
    return load_raw_reports()