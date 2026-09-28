# Requirements Document

## Introduction

The Internal Training Content Search Assistant is a low-cost, local-first Streamlit prototype that helps operations users search across mixed internal training content (PDFs, text/Markdown notes, and screenshots) and retrieve the most relevant guidance with clear source references. Today the operations enablement team answers repeated process questions by manually checking shared folders, PDF training decks, screenshots from internal tools, and short SOP notes. The same topics are explained in multiple places but cannot be searched together, which slows response time.

This prototype ingests a bounded corpus (~30-60 text documents/sections and ~20-40 screenshots), builds a searchable index using local embeddings, and presents source-backed answers through a simple Streamlit search interface. It is deliberately scoped as a retrieval prototype, not a broad chatbot, a full multimodal reasoning system, or an enterprise knowledge platform. The corpus combines a sanitized starter dataset pack with additional publicly available reference content used to extend retrieval testing.

The 20-day cycle produces: complete source code, the Streamlit prototype, ingestion and indexing scripts, a structured metadata file, an optional screenshot metadata file, 20-30 test queries with retrieved outputs, a README, notes on assumptions and limitations, and a short evaluation summary.

## Glossary

- **Assistant**: The complete Internal Training Content Search Assistant prototype, including ingestion, indexing, retrieval, and the Streamlit interface.
- **Ingestion_Component**: The subsystem that reads source files from a local folder and prepares them for indexing (extraction, chunking, metadata assembly).
- **PDF_Extractor**: The component that extracts text and page/section references from PDF files.
- **Screenshot_Indexer**: The component that indexes screenshot images using filename, optional OCR text, and manual metadata.
- **Metadata_Store**: The persisted structure (SQLite, CSV, or JSON) that holds per-item metadata such as topic, document type, source file name, and section reference.
- **Embedding_Component**: The component that converts text chunks into vector embeddings using a local sentence-transformers model.
- **Vector_Index**: The searchable vector store (FAISS or Chroma) that holds text chunk embeddings and supports similarity search.
- **Retrieval_Component**: The component that takes a user query, embeds it, searches the Vector_Index, and returns ranked matches.
- **Answer_Drafter**: The component that composes a short answer draft grounded only in retrieved content.
- **Search_Interface**: The Streamlit user interface where a user enters a query and views results.
- **Evaluation_Component**: The component/scripts that run sample queries and record retrieved outputs for the evaluation summary.
- **Text_Chunk**: A bounded segment of extracted text from a PDF or note, associated with source and section metadata.
- **Screenshot_Item**: An indexed screenshot image with its filename, related topic tag, and matching metadata or extracted text.
- **Query_Category**: One of the fixed classification labels: onboarding, SOP lookup, screenshot lookup, policy reference, troubleshooting support.
- **Confidence_Indicator**: A qualitative label of High, Medium, or Low describing how well retrieved content supports the answer draft.
- **Corpus**: The full set of ingested text documents and screenshots available for search.
- **User**: An operations team member who enters queries into the Search_Interface.

## Requirements

### Requirement 1: Local Corpus Ingestion

**User Story:** As an operations user, I want the Assistant to ingest a local folder of mixed training content, so that scattered PDFs, notes, and screenshots become searchable together.

#### Acceptance Criteria

1. WHEN a User specifies a local folder path containing supported files, THE Ingestion_Component SHALL read PDF files, TXT files, Markdown files, and screenshot image files (PNG, JPG, JPEG) from that folder and its subfolders.
2. WHERE an optional CSV or JSON metadata file is present in the specified folder, THE Ingestion_Component SHALL load the metadata file and associate its entries with the corresponding source files.
3. IF a file has an unsupported extension, THEN THE Ingestion_Component SHALL skip the file and record the skipped file name in an ingestion log.
4. IF a supported file cannot be read or parsed, THEN THE Ingestion_Component SHALL skip the file, record a descriptive error entry in the ingestion log, and continue processing remaining files.
5. WHEN ingestion completes, THE Ingestion_Component SHALL report the count of ingested text documents, the count of ingested screenshots, and the count of skipped files.

### Requirement 2: PDF Text Extraction and Chunking

**User Story:** As an operations user, I want PDF training decks to be extracted and split into searchable sections, so that I can find the specific step or reference I need.

#### Acceptance Criteria

1. WHEN the PDF_Extractor processes a PDF file, THE PDF_Extractor SHALL extract text content along with the page number for each extracted segment.
2. WHEN text is extracted from a PDF file, THE PDF_Extractor SHALL divide the extracted text into Text_Chunks that do not exceed a configured maximum chunk size.
3. THE PDF_Extractor SHALL associate each Text_Chunk with its source file name and page reference.
4. IF a PDF file contains no extractable text, THEN THE PDF_Extractor SHALL record the file name in the ingestion log as containing no extractable text and produce zero Text_Chunks for that file.

### Requirement 3: Text Note Ingestion and Chunking

**User Story:** As an operations user, I want SOP notes in TXT and Markdown files to be searchable, so that short process notes are retrieved alongside PDF content.

#### Acceptance Criteria

1. WHEN the Ingestion_Component processes a TXT file or Markdown file, THE Ingestion_Component SHALL extract the text content and divide it into Text_Chunks that do not exceed the configured maximum chunk size.
2. THE Ingestion_Component SHALL associate each Text_Chunk from a note with its source file name and a section reference derived from the file structure or heading where available.

### Requirement 4: Screenshot Indexing

**User Story:** As an operations user, I want screenshots to be indexed and searchable, so that I can locate the right screenshot reference without remembering the file name.

#### Acceptance Criteria

1. WHEN the Screenshot_Indexer processes a screenshot image file, THE Screenshot_Indexer SHALL record the file name and the file path as a Screenshot_Item.
2. WHERE OCR is enabled and available, THE Screenshot_Indexer SHALL extract text from the screenshot image and store the extracted text with the Screenshot_Item.
3. WHERE manual metadata is provided for a screenshot image, THE Screenshot_Indexer SHALL associate the provided topic tag and description with the Screenshot_Item.
4. IF OCR is disabled or unavailable for a screenshot image, THEN THE Screenshot_Indexer SHALL index the Screenshot_Item using the file name and any provided manual metadata.

### Requirement 5: Metadata Tagging and Storage

**User Story:** As a reviewer, I want each indexed item to carry consistent metadata, so that results can be traced back to their source and topic.

#### Acceptance Criteria

1. THE Metadata_Store SHALL record, for each Text_Chunk and each Screenshot_Item, the topic tag, the document type, the source file name, and the section or page reference where available.
2. WHEN ingestion completes, THE Metadata_Store SHALL persist all recorded metadata to a local file using SQLite, CSV, or JSON.
3. WHEN the Assistant is started with a previously built Metadata_Store present, THE Assistant SHALL load the persisted metadata without requiring re-ingestion.

### Requirement 6: Local Embedding and Vector Indexing

**User Story:** As an operations user, I want text content indexed with local embeddings, so that search works offline at low cost without paid cloud services.

#### Acceptance Criteria

1. WHEN the Embedding_Component processes a Text_Chunk, THE Embedding_Component SHALL produce a vector embedding using a local sentence-transformers model.
2. THE Embedding_Component SHALL generate embeddings without requiring a GPU and without requiring a paid cloud service.
3. WHEN embeddings are generated for all Text_Chunks, THE Vector_Index SHALL store each embedding together with a reference to its Text_Chunk in a local FAISS or Chroma store.
4. WHEN the Assistant is started with a previously built Vector_Index present, THE Assistant SHALL load the persisted Vector_Index without regenerating embeddings.

### Requirement 7: Query Retrieval

**User Story:** As an operations user, I want to enter a process-related query and receive the most relevant results, so that I can quickly confirm process steps or find references.

#### Acceptance Criteria

1. WHEN a User submits a non-empty query through the Search_Interface, THE Retrieval_Component SHALL embed the query using the same local model used for Text_Chunks and search the Vector_Index for the most similar Text_Chunks.
2. THE Retrieval_Component SHALL return the top matching Text_Chunks ranked by similarity score, limited to a configured maximum number of results.
3. THE Retrieval_Component SHALL return matching Screenshot_Items ranked by relevance using screenshot metadata and any extracted text.
4. IF a User submits an empty query, THEN THE Search_Interface SHALL display a prompt requesting a non-empty query and SHALL NOT perform retrieval.
5. IF no Text_Chunk or Screenshot_Item meets the configured minimum similarity threshold, THEN THE Retrieval_Component SHALL return an empty result set with a no-match indicator.

### Requirement 8: Query Categorization

**User Story:** As an operations user, I want each query classified into a recognizable category, so that I can understand the type of guidance returned.

#### Acceptance Criteria

1. WHEN a User submits a query, THE Retrieval_Component SHALL assign exactly one Query_Category from the set: onboarding, SOP lookup, screenshot lookup, policy reference, troubleshooting support.
2. THE Search_Interface SHALL display the assigned Query_Category with the query results.

### Requirement 9: Source-Backed Answer Draft

**User Story:** As an operations user, I want a short answer draft grounded in retrieved content, so that I get concise guidance without unsupported claims.

#### Acceptance Criteria

1. WHEN retrieval returns at least one matching Text_Chunk, THE Answer_Drafter SHALL produce an answer draft of no more than 6 lines that is derived only from the retrieved Text_Chunks and Screenshot_Items.
2. THE Answer_Drafter SHALL include, with the answer draft, references to the source items that support the answer draft.
3. IF retrieval returns no matches above the configured minimum similarity threshold, THEN THE Answer_Drafter SHALL return a statement that no supporting content was found and SHALL omit any drafted guidance.

### Requirement 10: Result Presentation

**User Story:** As an operations user, I want results displayed clearly with sources, so that a reviewer can verify each reference.

#### Acceptance Criteria

1. WHEN retrieval returns matching Text_Chunks, THE Search_Interface SHALL display for each text reference the document title, the page or section reference where available, the source file name, and a short relevant excerpt.
2. WHEN retrieval returns matching Screenshot_Items, THE Search_Interface SHALL display for each screenshot match an image preview or the file name, the related topic tag, and the matching metadata or extracted text.
3. THE Search_Interface SHALL display a Confidence_Indicator of High, Medium, or Low for the query results.
4. THE Search_Interface SHALL display a suggested next step selected from: use the source directly, review the original file, or escalate to the operations lead if unclear.

### Requirement 11: Low-Confidence Handling

**User Story:** As a reviewer, I want low-confidence cases handled honestly, so that the Assistant does not present unsupported claims.

#### Acceptance Criteria

1. IF the highest similarity score among retrieved results is below the configured Medium-confidence threshold, THEN THE Search_Interface SHALL set the Confidence_Indicator to Low and SHALL display the suggested next step to escalate to the operations lead if unclear.
2. WHILE the Confidence_Indicator is Low, THE Answer_Drafter SHALL limit the answer draft to content present in the retrieved items and SHALL indicate that confidence is low.

### Requirement 12: Local Operation Without Paid Cloud Services

**User Story:** As a capstone reviewer, I want the prototype to run locally on a standard laptop, so that I can run it without cloud accounts or GPUs.

#### Acceptance Criteria

1. THE Assistant SHALL perform ingestion, indexing, and retrieval using local components without requiring a GPU.
2. THE Assistant SHALL perform core search and retrieval without requiring a paid cloud service.
3. WHERE optional answer drafting through a local model or an external API is configured, THE Assistant SHALL fall back to grounded extraction from retrieved Text_Chunks when the configured model is unavailable.

### Requirement 13: Evaluation With Sample Queries

**User Story:** As a capstone reviewer, I want the prototype evaluated with sample queries, so that I can assess retrieval quality and screenshot search usefulness.

#### Acceptance Criteria

1. THE Evaluation_Component SHALL execute a set of at least 20 predefined sample queries against the built Corpus.
2. WHEN the Evaluation_Component executes the sample queries, THE Evaluation_Component SHALL record for each query the retrieved text references, the retrieved screenshot matches, the assigned Query_Category, and the Confidence_Indicator.
3. WHEN evaluation completes, THE Evaluation_Component SHALL write the recorded outputs to a local evaluation output file.
