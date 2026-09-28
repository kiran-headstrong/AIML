# Spinnaker Analytics - Internal Training Content Search Starter Pack

## Purpose

This resource pack is provided for the **Internal Training Content Search Assistant for Operations Knowledge Retrieval** project.

You should use it as the sanitized starter corpus for building a low-cost Streamlit retrieval prototype that searches across internal-style PDFs, SOP notes, and screenshot references. The files are safe mock equivalents of operational training material and do not contain confidential client data.

## What you are expected to build

You are expected to create a local prototype that lets an operations user enter a process-related question and retrieve:

- a short source-grounded answer draft
- top matching PDF or note references
- matching screenshot references where relevant
- confidence label such as High, Medium, or Low
- suggested next step such as review source or escalate

This is a searchable internal content assistant for operations use. Keep the build practical and bounded.

## Suggested folder usage

```text
spinnaker_training_search_starter_pack/
  documents/
    pdfs/
    notes/
  screenshots/
  metadata/
  evaluation/
  templates/
```

## Starter corpus included

### PDF training references

- `documents/pdfs/Ops_Onboarding_Access_Requests.pdf`
- `documents/pdfs/Approval_Escalation_Process.pdf`
- `documents/pdfs/Refund_Exception_Handling_Guide.pdf`

### Notes and SOP references

- `documents/notes/dashboard_filter_setup.md`
- `documents/notes/monthly_quality_review_sop.md`
- `documents/notes/user_role_matrix.txt`
- `documents/notes/internal_search_use_cases.md`
- `documents/notes/training_content_index.md`

### Screenshot-style references

- `screenshots/dashboard_filter_setup.png`
- `screenshots/approval_queue_status.png`
- `screenshots/refund_exception_form.png`
- `screenshots/user_access_role_mapping.png`
- `screenshots/quality_review_checklist.png`
- `screenshots/kb_search_result_mock.png`

### Metadata

- `metadata/corpus_metadata.csv`
- `metadata/corpus_metadata.json`
- `metadata/screenshot_metadata.csv`
- `metadata/screenshot_metadata.json`

### Evaluation resources

- `evaluation/test_queries.csv`
- `evaluation/retrieval_evaluation_template.csv`
- `evaluation/query_expected_behavior.md`

### Templates

- `templates/public_source_collection_template.csv`
- `templates/corpus_record_schema.json`

## Recommended implementation approach

You may use the following local-first stack:

- Python
- Streamlit
- pandas
- PyMuPDF or pdfplumber for PDF extraction
- sentence-transformers for embeddings
- FAISS or Chroma for vector search
- Pillow for image preview handling
- SQLite, CSV, or JSON for metadata storage

Optional:

- OCR using pytesseract if it works reliably on your laptop
- Ollama for local answer drafting
- limited OpenAI API calls only if needed and cost-controlled

## Suggested ingestion logic

1. Read metadata from `metadata/corpus_metadata.csv`.
2. Extract text from PDFs and notes.
3. Chunk the extracted text into retrieval-ready sections.
4. Read `metadata/screenshot_metadata.csv` and index the `manual_text` field for screenshot search.
5. Store chunks and screenshot metadata in FAISS or Chroma.
6. Build a Streamlit UI that displays text matches and screenshot matches separately.
7. Generate a short answer draft only from retrieved context.
8. Show source references clearly.

## Public-source extension

This project uses hybrid data mode. You should extend the starter corpus with a small set of credible public references.

Use `templates/public_source_collection_template.csv` to track public sources. Prefer:

- official help-center articles
- official product documentation
- onboarding guides
- public process walkthroughs
- official tool documentation with screenshots where available

Keep the collection bounded. Around 30 to 60 additional public text sections and 20 to 40 screenshot references are enough.

Avoid random datasets, benchmark corpora, unrelated blogs, or copied material without source tracking.

## Output expectations

For each user query, your Streamlit prototype should show:

- query category
- 4 to 6 line answer draft
- top text sources with title, source file, section/page if available, and excerpt
- screenshot matches with image preview or file name
- confidence indicator
- suggested next step

## Suggested confidence logic

You may start with simple rules:

- **High:** top retrieved sources are from the same topic and scores are strong
- **Medium:** relevant sources are present but excerpts are partial
- **Low:** retrieval is weak, topic mismatch exists, or only indirect evidence is available

Do not fabricate an answer when confidence is Low. Show the best sources and recommend manual review.

## Evaluation

Use `evaluation/test_queries.csv` to test the prototype. Record your results in `evaluation/retrieval_evaluation_template.csv`.

At minimum, include:

- top retrieved source
- top 3 retrieved sources
- relevance score from 1 to 5
- whether the answer was grounded
- whether screenshot retrieval worked where expected
- reviewer notes

## Submission reminder

Submit your completed project folder as a structured zip file with:

- source code
- Streamlit app
- ingestion/indexing scripts
- README for your implementation
- sample outputs
- evaluation summary
- screenshots of the working UI
- assumptions and limitations

Send project-related doubts through the official project email only. Consolidate questions clearly and do not assume access to any private systems unless files are explicitly shared.
