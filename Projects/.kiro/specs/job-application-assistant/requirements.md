# Requirements Document

## Introduction

The Job Application Assistant is a portal that streamlines the job application process. It scrapes job descriptions from popular job platforms (LinkedIn, Naukri), extracts the required tech stack, matches the JD against the user's existing resume, suggests targeted resume edits, generates an updated Word document, and provides comprehensive interview preparation materials including topic lists and categorized Q&A sets.

## Glossary

- **Portal**: The Job Application Assistant web application that provides all job application assistance features.
- **JD_Scraper**: The component responsible for fetching and extracting job description content from external job posting URLs.
- **Tech_Stack_Extractor**: The component that analyzes a job description and identifies required technologies, frameworks, tools, and skills.
- **Resume_Matcher**: The component that compares a parsed job description against the user's base resume and calculates a match score.
- **Resume_Editor**: The component that generates resume edit suggestions and produces a modified Word document (.docx) incorporating those suggestions.
- **Interview_Prep_Generator**: The component that generates interview preparation topics and categorized question-answer sets based on a job description.
- **Base_Resume**: The user's existing resume document uploaded to the Portal, used as the baseline for comparison and editing.
- **Match_Score**: A percentage value (0–100) representing how closely the Base_Resume aligns with a given job description.
- **Experience_Level**: The user's self-reported professional experience level (e.g., Fresher, Junior, Mid-Level, Senior, Lead/Architect) used to tailor interview preparation content.
- **Difficulty_Category**: A classification of interview questions into Easy, Medium, or Difficult tiers.

## Requirements

### Requirement 1: Job Description Scraping

**User Story:** As a job seeker, I want to provide a job posting URL from LinkedIn or Naukri so that the portal can automatically extract the job description without manual copy-pasting.

#### Acceptance Criteria

1. WHEN a user provides a valid LinkedIn job posting URL, THE JD_Scraper SHALL extract the job title, company name, job description text, and listed requirements from the page.
2. WHEN a user provides a valid Naukri job posting URL, THE JD_Scraper SHALL extract the job title, company name, job description text, and listed requirements from the page.
3. IF the provided URL is not a recognized LinkedIn or Naukri job posting URL, THEN THE JD_Scraper SHALL return a descriptive error message indicating the URL is unsupported.
4. IF the JD_Scraper fails to fetch content from a valid URL due to a network error or access restriction, THEN THE JD_Scraper SHALL return a descriptive error message indicating the fetch failure reason.
5. WHEN a job description is successfully scraped, THE JD_Scraper SHALL present the extracted job description to the user for confirmation before proceeding to further analysis.

### Requirement 2: Tech Stack Extraction

**User Story:** As a job seeker, I want to see the tech stack required for a job so that I can quickly understand the technical expectations.

#### Acceptance Criteria

1. WHEN a job description has been successfully scraped, THE Tech_Stack_Extractor SHALL identify and list all programming languages, frameworks, libraries, tools, databases, and cloud platforms mentioned in the job description.
2. THE Tech_Stack_Extractor SHALL categorize the extracted technologies into "Required" and "Nice-to-Have" based on the language used in the job description (e.g., "must have" vs. "preferred" or "good to have").
3. WHEN the job description contains no identifiable technologies, THE Tech_Stack_Extractor SHALL inform the user that no specific tech stack was found and suggest manual review.

### Requirement 3: Resume Upload, Parsing, and Persistence

**User Story:** As a job seeker, I want to upload my resume once and have it saved for future use so that I do not need to re-upload it every time I analyze a new job posting.

#### Acceptance Criteria

1. THE Portal SHALL accept Base_Resume uploads in PDF (.pdf) and Word (.docx) formats.
2. WHEN a Base_Resume is uploaded, THE Portal SHALL parse the resume and extract structured sections including contact information, skills, work experience, education, and certifications.
3. WHEN a Base_Resume is successfully uploaded and parsed, THE Portal SHALL persist the Base_Resume and its parsed data for reuse across multiple job application sessions.
4. WHILE a persisted Base_Resume exists, THE Portal SHALL use the stored Base_Resume for all subsequent job description analyses without requiring the user to re-upload.
5. WHEN a user uploads a new Base_Resume, THE Portal SHALL replace the previously stored Base_Resume with the new one.
6. THE Portal SHALL allow the user to view the currently stored Base_Resume details (file name, upload date, extracted skills summary) at any time.
7. IF the uploaded file is not a valid PDF or Word document, THEN THE Portal SHALL return a descriptive error message indicating the supported formats.
8. IF the uploaded resume cannot be parsed due to corrupted content or unreadable formatting, THEN THE Portal SHALL return a descriptive error message indicating the parsing failure.

### Requirement 4: Resume-to-JD Matching

**User Story:** As a job seeker, I want to see how well my resume matches a job description so that I can assess my fit for the role.

#### Acceptance Criteria

1. WHEN a Base_Resume and a scraped job description are both available, THE Resume_Matcher SHALL compute a Match_Score as a percentage (0–100) representing the alignment between the resume and the job description.
2. THE Resume_Matcher SHALL provide a breakdown of the Match_Score showing matched skills, missing skills, matched experience keywords, and missing experience keywords.
3. WHEN the Match_Score is computed, THE Resume_Matcher SHALL display the score along with a summary categorization (e.g., "Strong Match", "Moderate Match", "Weak Match").
4. THE Resume_Matcher SHALL weight technical skills, relevant experience, and education separately in the Match_Score computation and display each sub-score to the user.

### Requirement 5: Resume Edit Suggestions

**User Story:** As a job seeker, I want to receive specific suggestions on how to improve my resume for a particular job so that I can increase my chances of getting shortlisted.

#### Acceptance Criteria

1. WHEN a Match_Score has been computed, THE Resume_Editor SHALL generate a list of specific, actionable edit suggestions to improve the alignment between the Base_Resume and the job description.
2. THE Resume_Editor SHALL categorize suggestions into: "Skills to Add", "Experience Descriptions to Rephrase", "Keywords to Include", and "Sections to Reorder or Emphasize".
3. THE Resume_Editor SHALL prioritize suggestions by estimated impact on the Match_Score, presenting high-impact changes first.
4. THE Resume_Editor SHALL preserve the factual accuracy of the user's experience and qualifications in all suggestions, limiting edits to rephrasing, reordering, and keyword optimization.

### Requirement 6: Tailored Resume Generation in Word Document

**User Story:** As a job seeker, I want the portal to generate a new, tailored Word document resume for each job application so that I can download and submit a job-specific resume directly.

#### Acceptance Criteria

1. WHEN resume edit suggestions have been generated, THE Resume_Editor SHALL produce a new Word document (.docx) with the suggested changes applied to a copy of the Base_Resume content.
2. THE Resume_Editor SHALL preserve the original formatting, fonts, and layout structure of the Base_Resume in the generated Word document as closely as possible.
3. THE Resume_Editor SHALL highlight or annotate the modified sections in the generated Word document so the user can identify what was changed.
4. THE Portal SHALL provide a download link for the generated Word document.
5. THE Resume_Editor SHALL leave the persisted Base_Resume unchanged; each generated resume SHALL be a separate document tailored to the specific job description.
6. IF the Base_Resume was uploaded as a PDF, THEN THE Resume_Editor SHALL convert the parsed resume content into a Word document format before applying edits.
7. THE Portal SHALL associate each generated tailored resume with the corresponding job description for the user's reference.

### Requirement 7: Interview Preparation Topics

**User Story:** As a job seeker, I want to know what topics to prepare for the interview so that I can study efficiently.

#### Acceptance Criteria

1. WHEN a job description has been scraped, THE Interview_Prep_Generator SHALL generate a list of interview preparation topics relevant to the job description.
2. THE Interview_Prep_Generator SHALL categorize topics into "Technical Topics", "Domain Knowledge Topics", and "Behavioral/Soft Skill Topics".
3. THE Interview_Prep_Generator SHALL rank topics by relevance to the job description, with the most critical topics listed first.

### Requirement 8: Interview Q&A Generation

**User Story:** As a job seeker, I want to practice with interview questions and answers tailored to the job and my experience level so that I am well-prepared.

#### Acceptance Criteria

1. WHEN interview preparation topics have been generated, THE Interview_Prep_Generator SHALL generate interview questions and corresponding model answers for each topic.
2. THE Interview_Prep_Generator SHALL categorize each question into one Difficulty_Category: Easy, Medium, or Difficult.
3. THE Interview_Prep_Generator SHALL generate scenario-based questions that present realistic workplace situations relevant to the job description.
4. WHEN the user provides an Experience_Level, THE Interview_Prep_Generator SHALL tailor the depth, complexity, and expected answer quality of questions to match that experience level.
5. THE Interview_Prep_Generator SHALL generate a minimum of 5 questions per Difficulty_Category for each major topic.
6. THE Interview_Prep_Generator SHALL include the expected answer alongside each question, with key points highlighted for quick review.

### Requirement 9: Job Application Tracking Dashboard

**User Story:** As a job seeker, I want a dashboard to track all the jobs I have analyzed and applied to so that I can manage my job search progress in one place.

#### Acceptance Criteria

1. THE Portal SHALL maintain a history of all job descriptions that the user has analyzed, including the job title, company name, date analyzed, Match_Score, and a link to the generated tailored resume.
2. THE Portal SHALL provide a dashboard view displaying all tracked job applications in a tabular or card-based layout.
3. THE Portal SHALL allow the user to manually update the application status for each job entry. The supported statuses SHALL be: "Not Applied", "Applied", "Interview Scheduled", "Interview Completed", "Offered", and "Rejected".
4. THE Portal SHALL allow the user to add free-text feedback notes to each job entry (e.g., interview experience, recruiter contact, follow-up actions).
5. THE Portal SHALL allow the user to edit existing feedback notes and application status at any time (update operation).
6. THE Portal SHALL allow the user to delete a job entry from the tracking dashboard.
7. WHEN a new job description is analyzed, THE Portal SHALL automatically create a new entry in the dashboard with the status set to "Not Applied".
8. THE Portal SHALL allow the user to filter and sort dashboard entries by status, date analyzed, company name, or Match_Score.
9. THE Portal SHALL display a summary view on the dashboard showing total jobs analyzed, total applied, total interviews scheduled, and total offers received.

### Requirement 10: Cover Letter Generation

**User Story:** As a job seeker, I want the portal to generate a tailored cover letter for each job so that I can submit a compelling application without writing one from scratch.

#### Acceptance Criteria

1. WHEN a job description and a Base_Resume are both available, THE Resume_Editor SHALL generate a cover letter tailored to the specific job description, incorporating relevant skills and experience from the Base_Resume.
2. THE Resume_Editor SHALL structure the cover letter with an opening paragraph, body paragraphs highlighting relevant qualifications, and a closing paragraph.
3. WHEN the user provides an Experience_Level, THE Resume_Editor SHALL adjust the tone and content depth of the cover letter to match that experience level.
4. THE Portal SHALL allow the user to review and manually edit the generated cover letter before downloading.
5. THE Portal SHALL provide a download link for the cover letter in Word document (.docx) format.
6. THE Portal SHALL associate each generated cover letter with the corresponding job entry in the tracking dashboard.

### Requirement 11: Skill Gap Analysis and Learning Resources

**User Story:** As a job seeker, I want to understand my skill gaps and receive learning resource recommendations so that I can upskill for roles I'm interested in.

#### Acceptance Criteria

1. WHEN a Match_Score has been computed, THE Tech_Stack_Extractor SHALL identify all skills present in the job description that are absent from the Base_Resume.
2. THE Tech_Stack_Extractor SHALL categorize each skill gap by priority: "Critical" for required skills and "Recommended" for nice-to-have skills.
3. THE Tech_Stack_Extractor SHALL suggest learning resources (documentation links, course recommendations, tutorial references) for each identified skill gap.
4. THE Portal SHALL display the skill gap analysis alongside the Match_Score breakdown so the user can see both the gap and the improvement path.

### Requirement 12: Application Deadline and Reminder Tracking

**User Story:** As a job seeker, I want to set deadlines and reminders for job applications so that I do not miss application windows.

#### Acceptance Criteria

1. THE Portal SHALL allow the user to set an application deadline date for each job entry in the tracking dashboard.
2. WHILE a job entry has a deadline set and the status is "Not Applied", THE Portal SHALL display a visual indicator showing the number of days remaining until the deadline.
3. WHEN a job entry deadline is within 2 days and the status is "Not Applied", THE Portal SHALL highlight the entry with an urgent visual indicator on the dashboard.
4. THE Portal SHALL allow the user to edit or remove a deadline from any job entry.
5. THE Portal SHALL sort dashboard entries by approaching deadlines when the user selects deadline-based sorting.

### Requirement 13: Job Description Comparison

**User Story:** As a job seeker, I want to compare multiple job descriptions side by side so that I can prioritize which roles to apply for.

#### Acceptance Criteria

1. THE Portal SHALL allow the user to select two or more analyzed job descriptions for side-by-side comparison.
2. THE Portal SHALL display the comparison in a structured format showing: job title, company, required skills, preferred skills, experience required, and Match_Score for each selected job.
3. THE Portal SHALL highlight differences and commonalities in required skills across the compared job descriptions.
4. THE Portal SHALL indicate which of the compared roles has the highest Match_Score relative to the user's Base_Resume.

### Requirement 14: Export Interview Preparation as PDF

**User Story:** As a job seeker, I want to download the interview preparation topics and Q&A as a PDF so that I can study offline.

#### Acceptance Criteria

1. WHEN interview preparation topics and Q&A have been generated, THE Portal SHALL provide an option to export the content as a PDF document.
2. THE Portal SHALL format the exported PDF with clear section headings for topics, Difficulty_Category labels for each question, and readable answer formatting.
3. THE Portal SHALL include the job title and company name on the exported PDF for reference.
4. THE Portal SHALL provide a download link for the generated PDF.

### Requirement 15: JD Parsing and Pretty Printing

**User Story:** As a job seeker, I want to see a well-structured view of the scraped job description so that I can quickly understand the role requirements.

#### Acceptance Criteria

1. WHEN a job description is scraped, THE JD_Scraper SHALL parse the raw content into structured fields: job title, company name, location, experience required, job description body, required skills, and preferred skills.
2. THE Portal SHALL format and display the parsed job description in a clean, readable layout.
3. FOR ALL valid parsed job description objects, parsing then formatting then parsing SHALL produce an equivalent object (round-trip property).
