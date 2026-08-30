"""Evaluate the AI Training Assistant against the labeled evaluation set.

Measures retrieval quality and (optionally) generated-answer quality using the
dataset's ``evaluation_set.csv``:

- Retrieval citation accuracy: is the gold source document present in the
  top-k retrieved chunks?
- Key-phrase match: do the retrieved chunks (and, if enabled, the generated
  answer) contain the expected key phrases?
- Refusal correctness: for ``direct_llm`` questions (no gold source), the
  system should refuse or ask for clarification rather than fabricate an answer.

Retrieval metrics run fully offline (no API key needed). Answer-generation
metrics run only when ``--with-llm`` is passed and ``GROQ_API_KEY`` is set.

Usage:
    python evaluate.py                # retrieval-only metrics
    python evaluate.py --with-llm     # also score generated answers
"""

import argparse
import csv
import sys
from pathlib import Path

from src.knowledge_base import get_retriever, retrieve


HERE = Path(__file__).resolve().parent
EVAL_CSV = HERE / "OneDrive_1_8-22-2026" / "evaluation_set.csv"
TOP_K = 5


def _load_eval_rows() -> list[dict]:
    """Load the evaluation CSV into a list of row dicts.

    Returns:
        A list of dict rows keyed by the CSV header names.

    Raises:
        FileNotFoundError: If the evaluation CSV is missing.
    """
    if not EVAL_CSV.exists():
        raise FileNotFoundError(f"Evaluation set not found: {EVAL_CSV}")
    with EVAL_CSV.open(encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def _gold_source_name(gold_source: str) -> str:
    """Return the bare filename of a gold source path.

    Args:
        gold_source: A path like ``corpus/policies/leave_policy.md``.

    Returns:
        The filename (e.g. ``leave_policy.md``), or an empty string.
    """
    if not gold_source:
        return ""
    return gold_source.replace("\\", "/").split("/")[-1].strip()


def _key_phrases(raw: str) -> list[str]:
    """Split the expected key-phrase field into individual phrases.

    Args:
        raw: The gold key-phrase field, phrases separated by ';'.

    Returns:
        A list of lowercased, stripped phrases.
    """
    return [p.strip().lower() for p in raw.split(";") if p.strip()]


def _phrase_hit(phrases: list[str], text: str) -> bool:
    """Check whether any expected phrase appears in the text.

    Uses a loose token-overlap match so minor wording differences still count.

    Args:
        phrases: Expected key phrases (lowercased).
        text: The text to search (retrieved chunks or generated answer).

    Returns:
        True if at least one phrase reasonably matches.
    """
    low = text.lower()
    for phrase in phrases:
        if phrase and phrase in low:
            return True
        # Loose match: most significant words of the phrase appear.
        words = [w for w in phrase.split() if len(w) > 3]
        if words and sum(1 for w in words if w in low) >= max(1, len(words) // 2):
            return True
    return False


def _looks_like_refusal(text: str) -> bool:
    """Heuristically detect a refusal / clarification response.

    Args:
        text: The generated answer text.

    Returns:
        True if the answer appears to refuse, redirect, or ask to clarify.
    """
    markers = [
        "don't have", "do not have", "cannot", "can't", "unable",
        "contact hr", "hr portal", "payroll", "manager", "clarif",
        "not able", "reach out", "helpdesk", "i don't", "please provide",
    ]
    low = text.lower()
    return any(m in low for m in markers)


def main() -> int:
    """Run the evaluation and print a metrics report.

    Returns:
        Process exit code (0 on success).
    """
    parser = argparse.ArgumentParser(description="Evaluate the RAG assistant.")
    parser.add_argument(
        "--with-llm", action="store_true",
        help="Also generate answers via Groq and score them (needs GROQ_API_KEY).",
    )
    args = parser.parse_args()

    rows = _load_eval_rows()
    print(f"Loaded {len(rows)} evaluation questions.\n")

    print("Building / loading vector store...")
    store, embeddings = get_retriever()

    assistant = None
    if args.with_llm:
        try:
            from src.assistant import TrainingAssistant
            assistant = TrainingAssistant()
        except Exception as exc:  # noqa: BLE001 - report and continue offline
            print(f"  ! LLM generation disabled: {exc}\n")
            assistant = None

    rag_total = 0
    citation_hits = 0
    phrase_hits = 0
    refusal_total = 0
    refusal_correct = 0
    answer_phrase_hits = 0
    answer_total = 0

    print("\n" + "=" * 72)
    for row in rows:
        qid = row["question_id"]
        question = row["question"]
        route = row["expected_route"].strip()
        gold_source = _gold_source_name(row["gold_source"])
        phrases = _key_phrases(row["gold_answer_key_phrase_or_expected_behavior"])

        results = retrieve(question, store, embeddings, top_k=TOP_K)
        retrieved_sources = {
            r["source"].replace("\\", "/").split("/")[-1] for r in results
        }
        retrieved_text = "\n".join(r["text"] for r in results)

        if route == "direct_llm":
            # Refusal case: no gold source expected.
            refusal_total += 1
            verdict = "n/a (needs LLM)"
            if assistant is not None:
                answer = assistant.answer(question)["answer"]
                ok = _looks_like_refusal(answer)
                refusal_correct += int(ok)
                verdict = "REFUSED ✓" if ok else "did NOT refuse ✗"
            print(f"{qid} [{route}] {verdict}")
            continue

        rag_total += 1
        cite_ok = gold_source in retrieved_sources
        phrase_ok = _phrase_hit(phrases, retrieved_text)
        citation_hits += int(cite_ok)
        phrase_hits += int(phrase_ok)

        line = (
            f"{qid} [{route}] citation={'✓' if cite_ok else '✗'} "
            f"(gold={gold_source}) phrase={'✓' if phrase_ok else '✗'}"
        )
        if assistant is not None:
            answer = assistant.answer(question)["answer"]
            a_ok = _phrase_hit(phrases, answer)
            answer_total += 1
            answer_phrase_hits += int(a_ok)
            line += f" answer_phrase={'✓' if a_ok else '✗'}"
        print(line)

    print("=" * 72)
    print("\nRESULTS")
    print("-" * 40)
    if rag_total:
        print(f"RAG questions evaluated:      {rag_total}")
        print(f"Citation accuracy (gold@{TOP_K}):  "
              f"{citation_hits}/{rag_total} = {citation_hits / rag_total:.0%}")
        print(f"Key-phrase in retrieved text: "
              f"{phrase_hits}/{rag_total} = {phrase_hits / rag_total:.0%}")
    if answer_total:
        print(f"Key-phrase in generated answer: "
              f"{answer_phrase_hits}/{answer_total} = "
              f"{answer_phrase_hits / answer_total:.0%}")
    if refusal_total:
        if assistant is not None:
            print(f"Refusal correctness:          "
                  f"{refusal_correct}/{refusal_total} = "
                  f"{refusal_correct / refusal_total:.0%}")
        else:
            print(f"Refusal cases (need --with-llm): {refusal_total}")
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
