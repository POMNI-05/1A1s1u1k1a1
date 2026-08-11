# Tax Workpaper Generator / 税务工作底稿生成器

Automated draft tax-workpaper pipeline for Australian accounting practices.
面向澳大利亚会计事务所的税务工作底稿草稿生成工具。

This tool generates a structured tax workpaper from Profit & Loss and Balance Sheet reports. 

It maps account lines to ATO ITR references and produces a reconciliation from accounting profit to taxable income, ready for review.

---

## Project scope

This tool generates a working draft for tax-return preparation.
本工具仅生成用于报税准备的工作草稿。

All outputs, proposed adjustments, tax-rate selections and year-specific rules must be reviewed by a qualified accountant before use.
所有输出、建议调节、税率选择及年度规则均须由合资格会计师审核后方可使用。
<img width="613" height="708" alt="image" src="https://github.com/user-attachments/assets/13838326-f0c9-4524-8890-6b14128d03de" />

## What this tool does

- Loads 2 raw Xero Excel exports (P&L and Balance Sheet)  
- Cleans and parses reports (detects headers, amount columns, and row types automatically)  
- Labels each account line against ATO ITR references (e.g. 6C, 7W, 7F)  
- Builds a tax reconciliation:
  - Accounting profit → taxable income (Item 7 adjustments)  
  - Rule-detected adjustments are shown as **proposals only** and are not posted automatically
  - Reviewed manual adjustments can be supplied through `config.py`
  - Indicative tax is calculated only after selecting 25% or 30%; this is not a final liability calculation

规则识别的税务调节只作为建议展示，不会自动改变应税收入。只有确认税率后才计算指示性税额，该金额并非最终应缴税款。

---
## Output

The tool generates a formatted Excel workbook containing:

1. Two Original Reports (preserved and unchanged)
2. Reconciliation sheet with labelled P&L and Balance Sheet
3. Tax reconciliation table (Item 7) and also: 
- Balance sheet equation checks  
- Carry-forward losses and R&D input tables (where needed) 
- Review items flagged for accountant attention  

---
## How to use

1. Export P&L and Balance Sheet reports from Xero (Excel format)  
2. Upload the Excel file(s) in the web interface  
3. Click **Generate Workpaper**  
4. Download the generated Excel file


## First-time setup

1. Install Python 3.11, 3.12 or 3.13
2. Unzip this folder  
3. Double-click `run_app.bat`  
4. Wait for the browser app to open

---
## Notes for setting up

- VS Code is not required  
- Do not close the command window while the app is running  
- If the browser does not open automatically, copy the local URL into Chrome  
- Xero API integration is not required — manual Excel export is sufficient  

## Safety design

- Every generation runs in an isolated UUID job directory.
- Temporary job inputs, configuration, outputs and logs are deleted after the final workbook is copied.
- Previous workpapers are scoped to the current Streamlit session rather than globally listed.
- Uploaded workbooks, generated workpapers, logs and job directories are ignored by Git.
- AI review is optional and does not determine tax treatment.

- 每次生成任务均使用独立 UUID 目录。
- 最终工作簿复制完成后，临时输入、配置、输出和日志会被删除。
- 历史工作底稿按当前 Streamlit 会话隔离，不再向所有用户全局展示。
- 上传文件、输出、日志及任务目录均不会提交到 Git。
- AI 审核为可选功能，不负责决定最终税务处理。

## Tax-rate confirmation

The 25% option must only be selected after confirming the company is a base rate entity. The UI records the user's decision; it does not infer eligibility from the company name or profile. If the rate is not confirmed, tax remains blank.

只有确认公司符合 base rate entity 条件后才可选择 25%。系统仅记录用户选择，不会根据公司名称或简介自动判断资格。未确认税率时，税额保持空白。

## Deterministic calculator layer / 确定性计算器层

The root-level `tax_calculators/` package now separates regulated arithmetic from AI review and workbook generation. It includes company tax, reconciliation, depreciation, Division 7A minimum yearly repayment, and tax-loss utilisation primitives. Year-specific ATO constants are held in reviewed JSON source files for 2024–2026.

仓库根目录下的 `tax_calculators/` 包现已将受规则约束的算术与 AI 审核、工作簿生成分离。该层包含公司税、税务调节、折旧、Division 7A 最低年度还款及税务亏损使用等基础计算；2024–2026 各年度 ATO 常量保存在经核对的 JSON 来源文件中。

The live workbook path now reads company rates and year-specific thresholds from this registry and uses its decimal company-tax calculator. The other specialist calculators remain isolated until their required facts and review interfaces are added. Human confirmations are required for judgement-dependent inputs, and unconfirmed rules fail closed. See [`tax_calculators/README.md`](tax_calculators/README.md) for interfaces and limitations.

当前工作簿流程已从该注册表读取公司税率和年度门槛，并使用 Decimal 公司税计算器；其他专项计算器会在补齐必要事实和复核界面后再接入。涉及专业判断的输入必须由人工确认，未确认规则会安全停止。接口及限制详见 [`tax_calculators/README.md`](tax_calculators/README.md)。

## Policy-year limits / 政策年度限制

The 2024, 2025 and 2026 mappings follow their year-specific ATO return structure. The enacted $20,000 instant asset write-off threshold is stored separately for each supported income year; eligibility is never inferred from an account name. PSI, R&D and other sensitive items remain accountant-review matters. Confirm client facts and applicable schedules before lodgment.

2024、2025 与 2026 映射采用各年度的 ATO 申报结构。已立法的 $20,000 即时资产核销门槛按年度分别保存，系统不会仅凭账户名称推断资格；PSI、R&D 等敏感事项仍须由会计师审核。申报前必须核对客户事实及适用附表。

## Automated checks

Run:

```bash
python -m unittest discover -s tests -v
```

The suite covers year routing, calculator source validation, reconciliation approval safety, signed adjustments, calculator formulas, session-scoped outputs, job cleanup and a synthetic end-to-end workbook.

测试覆盖年度路由、计算器来源验证、调节审批安全、金额正负号、计算公式、会话级输出隔离、任务清理及合成 Excel 端到端流程。

## AI API

AI is disabled by default. The current optional face-check supports Gemini and requires a separate provider API key. ChatGPT Business access is not used as an application API credential. Never commit API keys or place them in workbook metadata.

AI 默认关闭。当前可选 face-check 支持 Gemini，并需要单独的服务商 API key。ChatGPT Business 登录不能直接作为应用 API 凭证。切勿把 API key 提交到 Git 或写入工作簿元数据。

## Official references

- [ATO company tax rates](https://www.ato.gov.au/tax-rates-and-codes/company-tax-rates)
- [ATO Company tax return 2024 instructions](https://www.ato.gov.au/forms-and-instructions/company-tax-return-2024-instructions)
- [ATO Company tax return 2025 instructions](https://www.ato.gov.au/forms-and-instructions/company-tax-return-2025-instructions)
- [ATO Company tax return 2026](https://iorder.com.au/publication/publicationdetails.aspx?pid=0656-6.2026)
- [ATO Guide to depreciating assets 2025](https://www.ato.gov.au/law/view/document?LocID=%22SAV%2FDEPRECIATING%2FATCARLIMIT%22&PiT=99991231235958)
- [ATO TR 2022/3 — personal services income](https://www.ato.gov.au/law/view/document?LocID=%22TXR%2FTR20223%2FNAT%2FATO%2F00001%22&PiT=99991231235958)
- [OpenAI API developer quickstart](https://developers.openai.com/api/docs/quickstart)