# Stage 2 — Isolated job and backend contract

## Purpose

`frontend/job_runner.py` creates a UUID-scoped job directory, saves copies of
the uploads, writes `request.json`, launches `python -m v1.main`, validates
`result.json`, and publishes only the owned output.

## Inputs and outputs

- Input: validated UI options and uploaded files.
- Output: `WorkpaperRequest` JSON to the backend and `WorkpaperResult` JSON
  back to the frontend.

## Issue/debugging log

| State | Issue | Diagnosis and safe resolution |
| --- | --- | --- |
| Resolved | Environment variables and filesystem paths formed an implicit backend API. | Use the versioned request/result contract; reject malformed results and paths outside the job directory. |
| Guardrail | Backend timeouts or result files are missing. | Show a failed job, publish no output, keep no partially trusted result. |

## Debug procedure

1. Re-run with `retain_job_files=True` only in a safe local debugging session.
2. Inspect that job's `request.json`, `result.json`, and logs; never inspect a
   different job directory.
3. Run `python -m unittest tests.test_workpaper_contract tests.test_job_runner -v`.
4. Check that every output path is inside its UUID job directory before the
   frontend copies it.
