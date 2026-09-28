# Data Dictionary

This pack is a sanitized starter corpus for the Spinnaker Analytics internal training content search assistant project.

## Folder layout

- `documents/pdfs/`  
  Sanitized training PDF references for access requests, approval escalation, and refund exception handling.

- `documents/notes/`  
  SOP notes, role reference material, use cases, and a lightweight content index.

- `screenshots/`  
  Mock screenshot-style PNG files that represent internal tool views without exposing real systems.

- `metadata/`  
  Structured metadata for corpus records and screenshot records in CSV and JSON format.

- `evaluation/`  
  Starter test queries and retrieval evaluation template.

- `templates/`  
  Public-source collection template and corpus schema.

## Key metadata fields

| Field | Meaning |
|---|---|
| record_id | Unique ID for each text/PDF corpus item |
| file_path | Relative file path inside the pack |
| title | Display title for search results |
| source_type | Whether the item is starter pack material or public-source material |
| content_type | File/content format |
| topic | Retrieval topic tag |
| document_type | Business document category |
| primary_user | Expected user role |
| expected_use | How the item should support operations search |
| confidentiality | Indicates sanitized sample or public source |
| suggested_query | Example query for testing |

## Screenshot metadata

The screenshot files are intentionally paired with manual metadata. If OCR is unreliable on your system, index the `manual_text` field from `metadata/screenshot_metadata.csv` and show the corresponding image preview in the app.

## Hybrid data extension

You may extend this pack with bounded public-source material. Use `templates/public_source_collection_template.csv` to record source title, URL, type, topic, and collected text path. Prefer official help centers, product documentation, onboarding guides, and public process walkthroughs.
