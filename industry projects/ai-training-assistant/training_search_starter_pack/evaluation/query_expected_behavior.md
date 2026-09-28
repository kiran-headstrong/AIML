# Query Expected Behavior Guide

Use this file to judge whether the prototype is returning useful results. The system does not need to produce identical wording, but it should retrieve the correct source files and avoid unsupported answers.

## Review dimensions
- **Top source relevance:** Is the best source aligned with the query topic?
- **Mixed-content handling:** Does the system return screenshot references when the query asks for screenshot evidence?
- **Grounding:** Does the answer use visible source content instead of unsupported assumptions?
- **Confidence label:** Does the output show Low confidence when source evidence is weak?
- **Operational clarity:** Can a non-developer operations reviewer understand the output?

## Recommended test flow
1. Run all queries from `evaluation/test_queries.csv`.
2. Save top retrieved sources and confidence labels.
3. Mark each result from 1 to 5 for retrieval relevance.
4. Note cases where screenshot search fails or returns unrelated images.
5. Include 3 to 5 sample screenshots of the Streamlit result page in the final submission.

## Minimum acceptable behavior
- Most access, approval, refund, dashboard, and quality-review queries should retrieve the expected primary source in the top 3.
- Screenshot-focused queries should return the related PNG file or its metadata.
- The answer draft should include source file names or section references.
