# Frontend / 前端

Run from the repository root:
请从项目根目录运行：

```bash
python -m streamlit run frontend/app.py
```

The frontend accepts one combined Excel workbook or multiple workbooks, records explicit tax-year and company-rate selections, and starts an isolated backend job. Temporary job data is removed after the result is copied into the current session's history folder.

前端支持上传一个合并工作簿或多个工作簿，记录明确的报税年度与公司税率选择，并启动独立后端任务。结果复制到当前会话的历史目录后，临时任务数据会被删除。

AI is optional. Do not paste an API key unless the selected provider will be used for that run. Keys are passed directly to the face-check helper and are not written to job configuration or metadata.

AI 为可选功能。只有本次任务确实需要使用相应服务商时才输入 API key。API key 会直接传给 face-check，不会写入任务配置或元数据。
