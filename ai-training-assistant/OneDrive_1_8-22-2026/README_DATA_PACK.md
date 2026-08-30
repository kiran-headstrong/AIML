# AI Training Assistant Data Pack (Test-only)

This data pack provides synthetic internal documents and an evaluation set for the capstone:
**AI Training Assistant for New Employees**.

## Contents
- `corpus/` (Markdown docs)
  - `company/` General overview and norms
  - `roles/` Role guides (Data Analyst, Product Manager)
  - `policies/` Expense, leave, conduct, security basics
  - `admin/` Onboarding checklist, HR processes, IT access, timesheets, travel
  - `faq/` Onboarding FAQ
- `evaluation_set.csv` (20 labeled questions with routing + gold citation hints)
- `dataset_manifest.json` (folder map + route mapping + schema)
- `retrieval_report_template.md` (optional)
- `runs_template.csv` (optional)

## Usage (Suggested)
1. Ingest `corpus/` into your chunking + embedding pipeline.
2. Implement routing: general_company / role_specific / admin_policy / direct_llm.
3. Evaluate using `evaluation_set.csv`:
   - RAG routes: citation correctness and answer key-phrase match
   - direct_llm: refusal/clarification correctness
