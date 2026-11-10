# Implementation Plan: Job Application Assistant

## Overview

This plan implements the Job Application Assistant as a full-stack web application with a Python/FastAPI backend, PostgreSQL database, and vanilla HTML/CSS/JS SPA frontend. Tasks are organized to build foundational layers first (project structure, database, auth), then core features (JD scraping, resume parsing, matching), then advanced features (tailored resume generation, interview prep, cover letters), and finally the dashboard and export capabilities. Each task builds incrementally on previous work.

## Tasks

- [x] 1. Set up project structure, configuration, and database models
  - [x] 1.1 Create project directory structure and install dependencies
    - Create `job_application_assistant/` directory with `backend/`, `frontend/`, subdirectories
    - Create `backend/requirements.txt` with: fastapi, uvicorn, sqlalchemy, asyncpg, alembic, python-jose, passlib[bcrypt], httpx, beautifulsoup4, pypdf, python-docx, weasyprint, langchain, pydantic
    - Create `backend/config.py` with environment-based settings (DATABASE_URL, JWT_SECRET, LLM config)
    - Create `backend/main.py` with FastAPI app initialization, CORS middleware
    - _Requirements: All (foundational)_

  - [x] 1.2 Define SQLAlchemy models for all database tables
    - Create `backend/models.py` with models: `User`, `BaseResume`, `ScrapedJD`, `TechStackItem`, `JobEntry`, `MatchResult`, `TailoredResume`, `CoverLetter`, `InterviewTopic`, `InterviewQA`
    - Use UUID primary keys, define all relationships and constraints per the design ERD
    - Include valid status enum for `JobEntry`: `not_applied`, `applied`, `interview_scheduled`, `interview_completed`, `offered`, `rejected`
    - _Requirements: 3.3, 9.1, 9.7_

  - [x] 1.3 Create Pydantic schemas for API request/response validation
    - Create `backend/schemas.py` with request and response schemas for all API endpoints
    - Include `ScrapedJD`, `TechStackResult`, `ParsedResume`, `MatchBreakdown`, `EditSuggestion`, `InterviewTopic`, `InterviewQA`, `CoverLetter` schemas
    - _Requirements: All (foundational)_

  - [x] 1.4 Set up database connection and Alembic migrations
    - Create `backend/database.py` with async SQLAlchemy engine and session factory
    - Initialize Alembic configuration and generate initial migration from models
    - _Requirements: 3.3 (persistence)_

- [x] 2. Implement authentication system
  - [x] 2.1 Implement user registration and login endpoints
    - Create `backend/auth.py` with password hashing (passlib/bcrypt) and JWT token creation/validation (python-jose)
    - Create `backend/routers/auth.py` with `POST /api/auth/register`, `POST /api/auth/login`, `GET /api/auth/me` routes
    - Implement auth dependency for extracting current user from JWT Bearer token
    - _Requirements: All authenticated endpoints_

  - [ ]* 2.2 Write unit tests for authentication
    - Test registration with valid/invalid data, login with correct/incorrect credentials, JWT token validation, and protected route access
    - _Requirements: All authenticated endpoints_

- [ ] 3. Checkpoint - Ensure project bootstraps and auth works
  - Ensure all tests pass, ask the user if questions arise.

- [x] 4. Implement JD Scraping and Tech Stack Extraction
  - [x] 4.1 Implement JD Scraper Service
    - Create `backend/services/jd_scraper.py` with `JDScraperService` class
    - Implement `_detect_platform()` to identify LinkedIn or Naukri from URL, raising `UnsupportedURLError` for other URLs
    - Implement `scrape()` with async httpx fetch and BeautifulSoup4 parsing for both LinkedIn and Naukri page structures
    - Implement `parse_to_structured()` to extract: job title, company name, location, experience required, description body, required skills, preferred skills
    - Implement `format_pretty()` to produce clean readable output from a `ScrapedJD`
    - Handle network errors and access restrictions with descriptive error messages
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 15.1, 15.2_

  - [x] 4.2 Implement Tech Stack Extractor Service
    - Create `backend/services/tech_stack_extractor.py` with `TechStackExtractorService` class
    - Implement `extract()` using LangChain LLM to identify and categorize technologies from JD text into categories (language, framework, database, cloud, tool) and priorities (required, nice_to_have)
    - Handle JDs with no identifiable technologies by returning an empty result with informational message
    - _Requirements: 2.1, 2.2, 2.3_

  - [x] 4.3 Create JD API routes
    - Create `backend/routers/jd.py` with `POST /api/jd/scrape`, `GET /api/jd/{id}`, `GET /api/jd/{id}/tech-stack`
    - Scrape endpoint: validate URL, scrape JD, persist to `scraped_jds` table, extract tech stack, persist to `tech_stack_items`, auto-create `job_entries` row with status `not_applied`
    - Return structured JD data formatted for user confirmation
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 2.1, 2.2, 2.3, 9.7, 15.1, 15.2_

  - [ ]* 4.4 Write unit tests for JD Scraper and Tech Stack Extractor
    - Test URL detection for LinkedIn, Naukri, and unsupported URLs
    - Test error handling for network failures
    - Test tech stack categorization into required/nice-to-have
    - Test handling of JDs with no technologies
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 2.1, 2.2, 2.3_

- [x] 5. Implement Resume Upload, Parsing, and Persistence
  - [x] 5.1 Implement Resume Parser Service
    - Create `backend/services/resume_parser.py` with `ResumeParserService` class
    - Implement `_parse_pdf()` using pypdf to extract text from PDF files
    - Implement `_parse_docx()` using python-docx to extract text from Word documents
    - Implement `_extract_sections()` using LLM to parse raw text into structured sections: contact info, skills, work experience, education, certifications
    - Validate file type and handle corrupted/unreadable files with descriptive errors
    - _Requirements: 3.1, 3.2, 3.7, 3.8_

  - [x] 5.2 Create Resume API routes
    - Create `backend/routers/resume.py` with `POST /api/resume/upload` and `GET /api/resume`
    - Upload endpoint: accept PDF/DOCX file, save to `uploads/` directory, parse resume, persist file path and parsed data to `base_resumes` table
    - Enforce one resume per user — replace existing on re-upload
    - GET endpoint: return stored resume details (file name, upload date, extracted skills summary)
    - Reject unsupported file types with descriptive error
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 3.8_

  - [ ]* 5.3 Write unit tests for Resume Parser
    - Test PDF and DOCX parsing
    - Test error handling for unsupported and corrupted files
    - Test section extraction produces expected structured output
    - _Requirements: 3.1, 3.2, 3.7, 3.8_

- [x] 6. Implement Resume-to-JD Matching and Skill Gap Analysis
  - [x] 6.1 Implement Resume Matcher Service
    - Create `backend/services/resume_matcher.py` with `ResumeMatcherService` class
    - Implement `_compute_skills_score()` comparing resume skills against JD required/preferred skills
    - Implement `_compute_experience_score()` comparing resume experience keywords against JD text
    - Implement `_compute_education_score()` comparing resume education against JD requirements
    - Implement `compute_match()` combining weighted sub-scores into overall 0–100 score with breakdown of matched/missing skills and experience keywords
    - Implement `_categorize_score()` mapping score ranges to "Strong Match", "Moderate Match", "Weak Match"
    - _Requirements: 4.1, 4.2, 4.3, 4.4_

  - [x] 6.2 Implement Skill Gap Analysis in Tech Stack Extractor
    - Add `identify_skill_gaps()` method to `TechStackExtractorService`
    - Compare tech stack items against resume skills, categorize gaps as "Critical" (required) or "Recommended" (nice-to-have)
    - Generate learning resource suggestions (documentation links, course recommendations) for each gap using LLM
    - _Requirements: 11.1, 11.2, 11.3_

  - [x] 6.3 Create Match API routes
    - Create `backend/routers/match.py` with `POST /api/match/{jd_id}`, `GET /api/match/{jd_id}`, `GET /api/match/{jd_id}/suggestions`, `GET /api/match/{jd_id}/skill-gaps`
    - Match endpoint: compute match, persist to `match_results` table, update `job_entries.match_score`
    - Skill gaps endpoint: return skill gap analysis alongside match score breakdown
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 11.1, 11.2, 11.3, 11.4_

  - [ ]* 6.4 Write unit tests for Resume Matcher and Skill Gap Analysis
    - Test score computation with known inputs
    - Test category assignment for various score ranges
    - Test skill gap identification with overlapping and non-overlapping skill sets
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 11.1, 11.2_

- [ ] 7. Checkpoint - Ensure core scraping, parsing, and matching pipeline works
  - Ensure all tests pass, ask the user if questions arise.

- [x] 8. Implement Resume Edit Suggestions and Tailored Resume Generation
  - [x] 8.1 Implement Resume Editor Service
    - Create `backend/services/resume_editor.py` with `ResumeEditorService` class
    - Implement `generate_suggestions()` using LLM to produce categorized, prioritized edit suggestions: "skills_to_add", "experience_rephrase", "keywords_to_include", "sections_reorder"
    - Each suggestion includes impact level (high/medium/low), original text, and suggested text
    - Ensure suggestions preserve factual accuracy of user's qualifications
    - _Requirements: 5.1, 5.2, 5.3, 5.4_

  - [x] 8.2 Implement tailored resume document generation
    - Implement `generate_tailored_docx()` to apply edit suggestions to a copy of the base resume
    - Implement `_apply_edits_to_docx()` to modify content while preserving original formatting, fonts, and layout
    - Implement `_highlight_changes()` to annotate modified sections for user identification
    - Handle PDF-uploaded resumes by converting parsed content into a Word document before applying edits
    - Save generated document to `generated/` directory, persist path to `tailored_resumes` table
    - _Requirements: 6.1, 6.2, 6.3, 6.5, 6.6, 6.7_

  - [x] 8.3 Create tailored resume API routes
    - Add `POST /api/match/{jd_id}/generate-resume` and `GET /api/match/{jd_id}/download-resume` to match router
    - Generate endpoint: trigger suggestion generation and document creation, associate with job entry
    - Download endpoint: return the generated .docx file
    - _Requirements: 5.1, 6.1, 6.4, 6.7_

  - [ ]* 8.4 Write unit tests for Resume Editor Service
    - Test suggestion generation categories and prioritization
    - Test DOCX generation preserves structure
    - Test highlight annotations are applied
    - _Requirements: 5.1, 5.2, 5.3, 6.1, 6.2, 6.3_

- [x] 9. Implement Interview Preparation
  - [x] 9.1 Implement Interview Prep Service
    - Create `backend/services/interview_prep.py` with `InterviewPrepService` class
    - Implement `generate_topics()` using LLM to produce ranked topics categorized as "technical", "domain", "behavioral"
    - Implement `generate_qa()` using LLM to produce Q&A sets per topic with difficulty levels (easy/medium/difficult), scenario-based questions, key points, and minimum 5 questions per difficulty per major topic
    - Tailor question depth and complexity based on user's experience level
    - _Requirements: 7.1, 7.2, 7.3, 8.1, 8.2, 8.3, 8.4, 8.5, 8.6_

  - [x] 9.2 Create Interview API routes
    - Create `backend/routers/interview.py` with `POST /api/interview/{jd_id}/topics`, `POST /api/interview/{jd_id}/qa`, `GET /api/interview/{jd_id}/export-pdf`
    - Persist generated topics and Q&A to `interview_topics` and `interview_qas` tables
    - _Requirements: 7.1, 7.2, 7.3, 8.1, 8.2, 8.3, 8.4, 8.5, 8.6_

  - [ ]* 9.3 Write unit tests for Interview Prep Service
    - Test topic generation produces categorized, ranked output
    - Test Q&A generation meets minimum count requirements per difficulty
    - Test experience level tailoring produces different output
    - _Requirements: 7.1, 7.2, 7.3, 8.1, 8.2, 8.5_

- [x] 10. Implement Cover Letter Generation
  - [x] 10.1 Implement Cover Letter Service
    - Create `backend/services/cover_letter.py` with `CoverLetterService` class
    - Implement `generate()` using LLM to produce structured cover letter (opening, body with relevant qualifications, closing)
    - Tailor tone and content depth based on experience level
    - Implement `export_docx()` to generate a downloadable .docx file
    - _Requirements: 10.1, 10.2, 10.3_

  - [x] 10.2 Create Cover Letter API routes
    - Create `backend/routers/cover_letter.py` with `POST /api/cover-letter/{jd_id}` and `GET /api/cover-letter/{jd_id}/download`
    - Generate endpoint: create cover letter, persist content and file path to `cover_letters` table, associate with job entry
    - Download endpoint: return .docx file
    - Support user review/edit by returning content in response before download
    - _Requirements: 10.1, 10.2, 10.3, 10.4, 10.5, 10.6_

  - [ ]* 10.3 Write unit tests for Cover Letter Service
    - Test cover letter structure contains opening, body, and closing
    - Test DOCX export generates valid file
    - _Requirements: 10.1, 10.2, 10.5_

- [x] 11. Implement Interview Prep PDF Export
  - [x] 11.1 Implement Export Service
    - Create `backend/services/export_service.py` with `ExportService` class
    - Implement `export_interview_prep_pdf()` using WeasyPrint to generate formatted PDF
    - Include clear section headings for topics, difficulty labels per question, readable answer formatting
    - Include job title and company name on the PDF for reference
    - Wire export to `GET /api/interview/{jd_id}/export-pdf` route
    - _Requirements: 14.1, 14.2, 14.3, 14.4_

  - [ ]* 11.2 Write unit tests for Export Service
    - Test PDF generation produces valid PDF bytes
    - Test PDF includes job title and company name
    - _Requirements: 14.1, 14.2, 14.3_

- [ ] 12. Checkpoint - Ensure all backend services and API routes work
  - Ensure all tests pass, ask the user if questions arise.

- [x] 13. Implement Job Application Tracking Dashboard API
  - [x] 13.1 Create Dashboard API routes
    - Create `backend/routers/dashboard.py` with `GET /api/dashboard`, `PATCH /api/dashboard/{entry_id}`, `DELETE /api/dashboard/{entry_id}`, `GET /api/dashboard/summary`
    - GET dashboard: return all job entries for user with JD title, company, date, match score, tailored resume link, status, notes, deadline
    - Support filter by status and sort by status, date, company name, match score, and deadline
    - PATCH endpoint: update status, notes, and/or deadline for a job entry
    - DELETE endpoint: remove job entry and associated data
    - Summary endpoint: return counts of total analyzed, applied, interviews scheduled, offers received
    - _Requirements: 9.1, 9.2, 9.3, 9.4, 9.5, 9.6, 9.8, 9.9_

  - [x] 13.2 Implement deadline tracking logic
    - Compute days remaining for entries with deadlines and `not_applied` status
    - Flag entries with deadlines within 2 days as urgent
    - Support deadline-based sorting
    - _Requirements: 12.1, 12.2, 12.3, 12.4, 12.5_

  - [ ]* 13.3 Write unit tests for Dashboard API
    - Test CRUD operations on job entries
    - Test filtering and sorting
    - Test summary statistics computation
    - Test deadline urgency calculation
    - _Requirements: 9.1, 9.2, 9.3, 9.4, 9.5, 9.6, 9.8, 9.9, 12.1, 12.2, 12.3_

- [x] 14. Implement JD Comparison API
  - [x] 14.1 Create Compare API route
    - Create `backend/routers/compare.py` with `POST /api/compare`
    - Accept list of JD IDs, fetch their data including match scores
    - Return structured comparison: job title, company, required skills, preferred skills, experience required, match score for each
    - Highlight commonalities and differences in required skills across selected JDs
    - Indicate which role has the highest match score
    - _Requirements: 13.1, 13.2, 13.3, 13.4_

  - [ ]* 14.2 Write unit tests for JD Comparison
    - Test comparison with multiple JDs identifies common and unique skills
    - Test highest match score identification
    - _Requirements: 13.1, 13.2, 13.3, 13.4_

- [x] 15. Wire all routers into FastAPI application
  - Register all routers (auth, jd, resume, match, interview, cover_letter, dashboard, compare) in `main.py`
  - Ensure consistent error handling and response formatting across all endpoints
  - Configure CORS for frontend origin
  - _Requirements: All_

- [ ] 16. Checkpoint - Ensure complete backend is functional
  - Ensure all tests pass, ask the user if questions arise.

- [x] 17. Build Frontend SPA - Authentication and Layout
  - [x] 17.1 Create base HTML structure and navigation
    - Create `frontend/index.html` with SPA shell: navbar, sidebar/nav links, main content area
    - Create `frontend/css/styles.css` with responsive layout, card-based design, table styling
    - Create `frontend/js/app.js` with SPA router (hash-based routing), API client utility with JWT auth headers
    - _Requirements: All (foundational)_

  - [x] 17.2 Implement login and registration pages
    - Create `frontend/js/pages/auth.js` with login form, registration form, JWT token storage in localStorage
    - Implement auth guard to redirect unauthenticated users to login
    - _Requirements: All authenticated features_

- [x] 18. Build Frontend SPA - Core Feature Pages
  - [x] 18.1 Implement JD scraping page
    - Create `frontend/js/pages/jd.js` with URL input form, scraped JD display (pretty-printed structured view), tech stack display with required/nice-to-have categorization
    - Show confirmation view after scraping before proceeding
    - Handle unsupported URL and network error messages
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 2.1, 2.2, 2.3, 15.1, 15.2_

  - [x] 18.2 Implement resume upload and display page
    - Create `frontend/js/pages/resume.js` with file upload form (PDF/DOCX), current resume details display (file name, upload date, skills summary)
    - Show upload validation errors for unsupported formats
    - _Requirements: 3.1, 3.2, 3.5, 3.6, 3.7_

  - [x] 18.3 Implement match results and suggestions page
    - Create `frontend/js/pages/match.js` with match score display (overall + sub-scores), category label, matched/missing skills lists, edit suggestions grouped by category and sorted by impact
    - Add skill gap analysis section with priority labels and learning resources
    - Add buttons for generating tailored resume and downloading it
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 5.1, 5.2, 5.3, 6.4, 11.1, 11.2, 11.3, 11.4_

- [x] 19. Build Frontend SPA - Advanced Feature Pages
  - [x] 19.1 Implement interview preparation page
    - Create `frontend/js/pages/interview.js` with topics list (categorized and ranked), Q&A display with difficulty filters, scenario-based question indicators, key points highlighting
    - Add experience level selector that triggers re-generation
    - Add PDF export download button
    - _Requirements: 7.1, 7.2, 7.3, 8.1, 8.2, 8.3, 8.4, 8.5, 8.6, 14.1, 14.2, 14.3, 14.4_

  - [x] 19.2 Implement cover letter page
    - Create `frontend/js/pages/cover_letter.js` with cover letter generation trigger, content display in editable text area for review/edit, download button for .docx
    - Add experience level selector
    - _Requirements: 10.1, 10.2, 10.3, 10.4, 10.5, 10.6_

  - [x] 19.3 Implement job comparison page
    - Create `frontend/js/pages/compare.js` with multi-select JD picker, side-by-side comparison table showing title, company, skills, experience, match score
    - Highlight common and unique skills, indicate highest match score
    - _Requirements: 13.1, 13.2, 13.3, 13.4_

- [x] 20. Build Frontend SPA - Dashboard
  - [x] 20.1 Implement tracking dashboard page
    - Create `frontend/js/pages/dashboard.js` with tabular/card layout of all job entries showing title, company, date, match score, status, notes, deadline, resume link
    - Implement status dropdown for updating application status
    - Implement inline notes editing (add/edit free-text feedback)
    - Implement deadline date picker with days-remaining indicator and urgent highlighting (≤2 days)
    - Implement delete entry with confirmation
    - Add filter dropdowns (by status) and sort controls (by status, date, company, match score, deadline)
    - Add summary stats bar: total analyzed, total applied, interviews scheduled, offers received
    - _Requirements: 9.1, 9.2, 9.3, 9.4, 9.5, 9.6, 9.8, 9.9, 12.1, 12.2, 12.3, 12.4, 12.5_

- [x] 21. Final checkpoint - Ensure full application works end-to-end
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation at key milestones
- The backend is built first (tasks 1–16) so API routes can be tested independently before the frontend
- The frontend (tasks 17–20) consumes the backend API and mirrors the requirement structure
- All LLM interactions use LangChain with a configurable provider for flexibility
