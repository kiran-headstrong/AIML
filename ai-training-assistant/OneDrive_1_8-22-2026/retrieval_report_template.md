# Retrieval Report (Template)

## Run Metadata
- run_id:
- date_time:
- model:
- embedding_model:
- vector_store:
- chunk_size:
- top_k:

## Query
- user_question:

## Routing Decision
- predicted_route:
- confidence:
- reason:

## Retrieval (Top-K)
Provide the retrieved chunks with:
- source_file
- chunk_id
- similarity_score
- snippet (short)

## Final Answer
- answer_text:

## Citations Used
List citations in the format:
- [source_file#section_or_chunk_id]

## Self-Check
- evidence_sufficiency: (sufficient / weak)
- hallucination_risk: (low / medium / high)
- clarification_needed: (yes / no)
