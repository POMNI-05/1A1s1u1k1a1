# Calculator layer / 计算器层

This package contains deterministic calculation primitives. It does not call an AI model,
choose tax treatments, or write to workbooks. The live workbook path uses the versioned rule
registry and company-tax calculator; the specialist calculators remain opt-in until their
required facts and review interfaces are available.


## Safety model / 安全模型

- Monetary arithmetic uses `Decimal` and returns values rounded to cents.
- Year-specific constants are stored in `sources/*.json` as strings to avoid float drift.
- A rule marked `review_required` raises `ReviewRequiredError` rather than guessing.
- The 25% company rate, Division 7A terms, instant write-off conditions, and tax-loss
  eligibility require explicit confirmation.
- Reconciliation posts approved adjustments only and preserves signed amounts.

- 金额运算使用 `Decimal`，结果按分取整。
- 各年度常量以字符串形式保存在 `sources/*.json`，避免浮点误差。
- 标记为 `review_required` 的规则会抛出 `ReviewRequiredError`，不会自行猜测。
- 25% 公司税率、Division 7A 条款、即时资产核销条件及税务亏损资格均须明确确认。
- 税务调节仅计入已批准项目，并保留输入金额的正负号。

## Important limits / 重要限制

These functions perform arithmetic, not tax advice. In particular, the Division 7A function
implements the minimum-yearly-repayment formula for a standard 30 June income year only. Use
the ATO calculator for dated repayments, interest, closing balances, or substituted accounting
periods. Depreciation does not choose an effective life, and the tax-loss function does not test
continuity or business-continuity rules.

这些函数只负责算术，不构成税务建议。Division 7A 函数仅实现标准 6 月 30 日结算年度的最低年度还款公式；
如涉及分日期还款、利息、期末余额或替代会计期间，应使用 ATO 官方计算器。折旧函数不会替用户选择有效寿命，
税务亏损函数也不会判断所有权连续性或业务连续性规则。

## Annual rule-pack workflow

1. Create a new `sources/<income-year>.json` with every section set to
   `review_required` until its law or ATO guidance is verified.
2. Record the income-year period, verification date, exact decimal-string values and
   primary source URL. Never inherit a temporary concession implicitly.
3. Change a section to `enacted` only after review, add boundary tests, and run the full
   end-to-end workbook test.
4. Keep account-name matches as proposals. A rule-pack update may change arithmetic or
   labels, but it must not infer client eligibility or approve a tax adjustment.

## Official sources / 官方来源

- [ATO company tax rates](https://www.ato.gov.au/tax-rates-and-codes/company-tax-rates)
- [ATO depreciation and capital allowances](https://www.ato.gov.au/businesses-and-organisations/income-deductions-and-concessions/depreciation-and-capital-expenses-and-allowances)
- [ATO Division 7A benchmark interest rate](https://www.ato.gov.au/tax-rates-and-codes/division-7a-benchmark-interest-rate)
- [ATO Division 7A calculator](https://www.ato.gov.au/calculators-and-tools/division-7a-calculator-and-decision-tool)
- [ITAA 1936 s109E](https://www.ato.gov.au/law/view/document?LocID=%22PAC%2F19360027%2F109E%281%29%22)
- [ATO instant asset write-off](https://www.ato.gov.au/businesses-and-organisations/income-deductions-and-concessions/depreciation-and-capital-expenses-and-allowances/simpler-depreciation-for-small-business/instant-asset-write-off)
