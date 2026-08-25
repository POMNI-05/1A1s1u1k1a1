# Tax Workpaper Generator
## An automated draft tax-workpaper pipeline for Australian accounting practices

[English](#english) · [中文](#中文)

<a id="english"></a>

This project creates a review-ready workpaper from Profit & Loss, Balance Sheet
and optional supporting schedules. It maps account lines to ATO income-tax-return
references and builds a deterministic reconciliation from accounting profit to
preliminary taxable income.

### Scope and accountant review

This tool produces a working draft for tax-return preparation. It is not a
lodgment system and does not replace a qualified accountant. All outputs,
proposed adjustments, tax-rate selections, year-specific rules and supporting
schedules must be reviewed before use.

The calculation engine is deterministic. AI review is optional and display-only:
it can explain or flag evidence, but cannot change tax treatment, workbook
formulas, classifications or approved adjustments.

### What it does
<img width="229" height="617" alt="image" src="https://github.com/user-attachments/assets/b1ae2914-ae2c-4643-a9f5-24f573a1eb61" />

- Loads Xero Excel exports for Profit & Loss and Balance Sheet reports.
- Detects headers, periods, amount columns and row types with fail-closed input
  checks.
- Maps account lines to ATO ITR references such as 6C, 7W and 7F.
<img width="1248" height="591" alt="image" src="https://github.com/user-attachments/assets/06b382da-d0c0-4cf4-bd92-a6d1329a8006" />
<img width="1315" height="258" alt="image" src="https://github.com/user-attachments/assets/31c93c72-a0e8-45fd-8169-ed55afd365b8" />

- Builds a concise Tab 3 bridge: accounting profit, applicable ADD/SUBTRACT
  items, formula-based totals and preliminary Item 7T.
<img width="858" height="571" alt="image" src="https://github.com/user-attachments/assets/eab58c15-d97b-411d-b087-855d82e05b6f" />
- Uses a matching, non-zero tax-depreciation schedule as preliminary 7F
  evidence; wrong-year or zero schedules remain support evidence only.
- Preserves uploaded source sheets before generated review sheets. A supplied
  Fixed Assets/tax-depreciation source is placed third in the output workbook.
- Provides controlled browser review and exports a new revision workbook without
  overwriting the original.
- Groups workpapers by saved client name, with a conservative filename fallback
  for older generated files.
<img width="479" height="297" alt="image" src="https://github.com/user-attachments/assets/fc309ab2-07d9-41ea-b6ed-3b27179e3c60" />


### Output workbook

Generated workbooks can contain:

1. Original source reports, preserved and unchanged.
2. An optional Fixed Assets/tax-depreciation source sheet.
3. Tax Reconciliation with live Excel formulas for totals and preliminary 7T.
4. Inputs & Overrides, Checks and other generated review/support sheets.

The workbook is a pre-calculation and review aid. A reviewer must confirm the
final tax treatment before lodgment.

### Quick start

1. Install Python 3.11, 3.12 or 3.13.
2. Export the relevant Xero reports as Excel files.
3. From the project root, start the Streamlit app:

   ```bash
   streamlit run frontend/app.py
   ```

4. Open the local URL shown by Streamlit.
5. Enter the client/engagement name, select the income year and upload the
   source workbooks.
6. Select only relevant review schedules, then click **Generate workpaper**.
7. Download the generated Excel file and complete the accountant review.

VS Code is not required. Do not close the terminal while the app is running.
Xero API integration is not required; manual Excel exports are supported.

### Client workpaper grouping

The client library uses a saved `client_name` first. For older generated files,
the read-only preview script can infer a tag from the standard
`client_workpaper_timestamp.xlsx` filename convention:

```bash
python tools/tag_workpapers_by_client.py
```

After checking the preview, missing sidecar tags can be written explicitly:

```bash
python tools/tag_workpapers_by_client.py --write-tags
python tools/tag_workpapers_by_client.py --write-index client_index.json
```

The script never edits an Excel workbook and does not fuzzy-merge similar client
names. Confirm aliases manually before grouping them together.

### Safety design

- Each generation runs in an isolated UUID job directory.
- Invalid Excel errors, malformed confirmed amounts and ambiguous periods stop
  deliberately; the system does not turn them into guessed zeros.
- Temporary job inputs, configuration, outputs and logs are removed after the
  final workbook is copied to the session-scoped download area.
- Uploaded workbooks, generated workpapers, logs and job directories are
  ignored by Git.
- AI receives minimised decision evidence rather than workbooks or backend logs.
- AI review audit sidecars remain local and are not part of the tax calculation.
- The original workbook remains unchanged when a reviewer exports a revision.

### Tax-rate and policy-year boundaries

The 25% company-tax option is available only after the user confirms base-rate
entity eligibility. The UI records that decision; it does not infer eligibility
from a company name or profile. Without a confirmed rate, tax remains blank.

The supported policy years are 2024, 2025 and 2026. Year-specific ATO rules and
thresholds are kept separately. PSI, R&D, depreciation, losses and other
judgement-dependent matters require the relevant facts and accountant review.

### Deterministic calculator layer

The root-level `tax_calculators/` package separates regulated arithmetic from
AI review and workbook generation. It contains company-tax, reconciliation,
depreciation, Division 7A and tax-loss primitives. Year-specific ATO constants
are held in reviewed source files. See
[`tax_calculators/README.md`](tax_calculators/README.md) for interfaces and
limitations.

### Automated checks

Run the complete test suite from the project root:

```bash
python -m unittest discover -s tests -v
```

The tests cover policy-year routing, strict amount parsing, reconciliation
approval safety, formulas, workbook output, session isolation, revision audit,
AI contracts, UI safety states and client grouping.

### Optional AI review

AI is disabled by default. The optional Gemini/Grok adapter receives minimised,
deterministic decision evidence and cannot change tax outcomes. Each run may
write a local `*.ai_review_audit.json` sidecar containing provider, model, input
hash, response status, findings and accountant disposition. Read
[`docs/ai_review_data_handling.md`](docs/ai_review_data_handling.md) before
enabling it for client work. Never commit API keys or client workbooks.

### Official references

- [ATO company tax rates](https://www.ato.gov.au/tax-rates-and-codes/company-tax-rates)
- [ATO Company tax return 2024 instructions](https://www.ato.gov.au/forms-and-instructions/company-tax-return-2024-instructions)
- [ATO Company tax return 2025 instructions](https://www.ato.gov.au/forms-and-instructions/company-tax-return-2025-instructions)
- [ATO Company tax return 2026](https://iorder.com.au/publication/publicationdetails.aspx?pid=0656-6.2026)
- [ATO Guide to depreciating assets 2025](https://www.ato.gov.au/law/view/document?LocID=%22SAV%2FDEPRECIATING%2FATCARLIMIT%22&PiT=99991231235958)
- [ATO TR 2022/3 — personal services income](https://www.ato.gov.au/law/view/document?LocID=%22TXR%2FTR20223%2FNAT%2FATO%2F00001%22&PiT=99991231235958)

<a id="中文"></a>

## 中文

这是一个面向澳大利亚会计事务所的税务工作底稿草稿生成流程。

系统可以读取损益表、资产负债表以及可选的支持性附表，按照 ATO 公司税申报表项目进行账户映射，并以确定性规则生成“会计利润 → 初步应税收入”的调节表。

### 使用范围与会计师审核

本项目只生成报税准备阶段的工作草稿，不是最终申报或自动报税系统。所有输出、建议调节、税率选择、年度规则和支持性附表，都必须由合资格会计师审核后才能使用。

计算结果由确定性规则产生。AI 审核是可选的、只读的解释功能；它可以帮助说明证据或提示风险，但不能修改税务处理、工作簿公式、账户分类或已批准的调节。

### 系统功能

- 读取 Xero 导出的损益表和资产负债表 Excel 文件。
- 自动识别表头、期间、金额列和行类型；遇到不安全输入时会明确停止。
- 将账户映射到 ATO ITR 项目，例如 6C、7W 和 7F。
- 生成简洁的 Tab 3：会计利润、适用的 ADD/SUBTRACT 项目、Excel 公式合计和初步 Item 7T。
- 只有当税法折旧表匹配所选年度且有非零金额时，才作为初步 7F 证据；错误年度或零金额折旧表只保留为佐证。
- 保留原始上传表，并将它们放在生成内容之前；如果有 Fixed Assets/税法折旧源表，它会排在第 3 个 tab。
- 提供受控的浏览器审核，并导出新的修订工作簿，不覆盖原始文件。
- 按已保存的客户名称分组旧 workpaper；必要时对标准文件名使用保守的客户名兜底识别。

### 输出工作簿

生成的工作簿可能包含：

1. 原始源报表，保持不变。
2. 可选的 Fixed Assets/税法折旧源表。
3. Tax Reconciliation，其中合计和初步 7T 使用 Excel 实时公式。
4. Inputs & Overrides、Checks 以及其他生成的审核/支持页。

该工作簿是预计算和审核辅助工具。最终申报前，必须由会计师确认税务处理。

### 快速开始

1. 安装 Python 3.11、3.12 或 3.13。
2. 从 Xero 导出相关 Excel 报表。
3. 在项目根目录运行：

   ```bash
   streamlit run frontend/app.py
   ```

4. 打开 Streamlit 显示的本地地址。
5. 输入客户/项目名称，选择收入年度并上传源工作簿。
6. 只选择与本项目有关的审核附表，然后点击 **Generate workpaper**。
7. 下载 Excel 工作簿并完成会计师审核。

不需要 VS Code。程序运行时不要关闭终端窗口。不需要 Xero API，手动导出的 Excel 文件即可使用。

### 客户 workpaper 分组

客户库会优先使用保存的 `client_name`。对于旧的生成文件，可以用只读预览脚本从标准的 `client_workpaper_timestamp.xlsx` 文件名推断标签：

```bash
python tools/tag_workpapers_by_client.py
```

确认预览结果后，才可以显式写入缺失的 sidecar 标签：

```bash
python tools/tag_workpapers_by_client.py --write-tags
python tools/tag_workpapers_by_client.py --write-index client_index.json
```

脚本不会修改 Excel，也不会模糊合并相似客户名。客户别名必须人工确认。

### 安全设计

- 每次生成任务都在独立的 UUID 任务目录中运行。
- Excel 错误、已确认金额列中的无效金额以及不明确的期间会触发安全停止；系统不会猜测或静默改成零。
- 临时输入、配置、输出和日志会在最终工作簿复制到当前会话下载区后清理。
- 上传工作簿、生成文件、日志和任务目录都被 Git 忽略。
- AI 只接收最小化的决定证据，不接收工作簿或后端日志。
- AI 审核 sidecar 保留在本地，不参与税务计算。
- 审核者导出修订时，原始工作簿保持不变。

### 税率与政策年度边界

只有在用户确认公司属于 base-rate entity 后，才可以选择 25% 公司税率。系统记录用户的确认，不会根据公司名称或简介自动判断资格。没有确认税率时，税额保持为空。

当前支持 2024、2025 和 2026 政策年度。ATO 规则和门槛按年度分开保存。PSI、R&D、折旧、税务亏损以及其他依赖专业判断的事项，都需要相关事实和会计师审核。

### 确定性计算器层

根目录的 `tax_calculators/` 将受规则约束的算术与 AI 审核、工作簿生成分开。它包含公司税、税务调节、折旧、Division 7A 和税务亏损等基础计算器；各年度 ATO 常量保存在经过审核的来源文件中。接口和限制请参阅 [`tax_calculators/README.md`](tax_calculators/README.md)。

### 自动化测试

在项目根目录运行完整测试：

```bash
python -m unittest discover -s tests -v
```

测试覆盖政策年度路由、严格金额解析、调节审批安全、Excel 公式、工作簿输出、会话隔离、修订审计、AI 契约、UI 安全状态和客户分组。

### 可选 AI 审核

AI 默认关闭。可选的 Gemini/Grok 适配器只接收最小化的确定性决定证据，不能修改税务结果。每次运行可能在本地生成 `*.ai_review_audit.json` sidecar，记录服务商、模型、输入哈希、响应状态、发现和会计师处置。为客户项目启用前，请阅读 [`docs/ai_review_data_handling.md`](docs/ai_review_data_handling.md)。不要提交 API key 或客户工作簿。

### 官方参考

- [ATO 公司税率](https://www.ato.gov.au/tax-rates-and-codes/company-tax-rates)
- [ATO 2024 公司税申报说明](https://www.ato.gov.au/forms-and-instructions/company-tax-return-2024-instructions)
- [ATO 2025 公司税申报说明](https://www.ato.gov.au/forms-and-instructions/company-tax-return-2025-instructions)
- [ATO 2026 公司税申报](https://iorder.com.au/publication/publicationdetails.aspx?pid=0656-6.2026)
- [ATO 2025 折旧资产指南](https://www.ato.gov.au/law/view/document?LocID=%22SAV%2FDEPRECIATING%2FATCARLIMIT%22&PiT=99991231235958)
- [ATO TR 2022/3：个人服务收入](https://www.ato.gov.au/law/view/document?LocID=%22TXR%2FTR20223%2FNAT%2FATO%2F00001&PiT=99991231235958)
