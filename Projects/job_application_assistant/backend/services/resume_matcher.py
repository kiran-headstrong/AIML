"""
Resume Matcher Service.

Compute a weighted :class:`~schemas.MatchBreakdown` describing how closely a
parsed base resume aligns with a scraped job description (Requirement 4.1).
The overall 0–100 score is a weighted blend of three independently-computed
sub-scores — technical skills, relevant experience, and education
(Requirement 4.4) — and the breakdown additionally reports which skills and
experience keywords matched and which are missing (Requirement 4.2), together
with a human-readable category label (Requirement 4.3).

Design notes
------------
* This service is deliberately **deterministic and LLM-free**. Matching is a
  lexical/keyword comparison so that scores are stable, explainable, and
  testable with known inputs. (The LLM-backed skill-gap narrative lives in the
  tech-stack extractor; see task 6.2.)
* All comparisons are case-insensitive and tolerant of surrounding whitespace.
  Skill and keyword matching also tolerates token-level containment (e.g. a
  resume skill ``"Amazon Web Services (AWS)"`` matches a JD skill ``"AWS"``)
  so that minor phrasing differences do not depress the score unfairly.
* Sub-scores are expressed on a 0–100 scale. The overall score blends them
  using the weights in :data:`DEFAULT_WEIGHTS`; when a JD provides no signal
  for a given dimension (e.g. no skills listed), that dimension is dropped from
  the blend and the remaining weights are renormalised so a missing dimension
  neither helps nor hurts artificially.

Import style follows the backend package convention (direct module imports),
since ``main.py`` inserts the backend directory onto ``sys.path``.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from schemas import Education, MatchBreakdown, MatchCategory, ParsedResume, ScrapedJD, WorkExperience

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

#: Relative weights of each sub-score in the overall match score (Req 4.4).
#: Technical skills dominate, followed by experience, then education.
DEFAULT_WEIGHTS: dict[str, float] = {
    "skills": 0.5,
    "experience": 0.35,
    "education": 0.15,
}

#: Score thresholds (inclusive lower bounds) mapping to category labels (Req 4.3).
_STRONG_MATCH_THRESHOLD: float = 75.0
_MODERATE_MATCH_THRESHOLD: float = 50.0

#: Common education-level keywords used to gauge education alignment.
_DEGREE_KEYWORDS: tuple[str, ...] = (
    "phd",
    "doctorate",
    "master",
    "mba",
    "bachelor",
    "b.tech",
    "btech",
    "b.e",
    "be",
    "m.tech",
    "mtech",
    "m.s",
    "ms",
    "b.s",
    "bs",
    "b.sc",
    "bsc",
    "m.sc",
    "msc",
    "associate",
    "diploma",
    "degree",
)

#: Words ignored when deriving experience keywords from JD text — common
#: English stop-words plus generic recruiting filler that carries no signal.
_STOP_WORDS: frozenset[str] = frozenset(
    {
        "the", "and", "for", "with", "you", "your", "our", "are", "will",
        "have", "has", "that", "this", "from", "they", "their", "them",
        "who", "whom", "was", "were", "been", "being", "its", "it's",
        "a", "an", "of", "to", "in", "on", "at", "by", "or", "as", "is",
        "be", "we", "us", "all", "any", "can", "may", "not", "but", "if",
        "job", "role", "work", "working", "team", "teams", "company",
        "candidate", "candidates", "ability", "strong", "good", "great",
        "excellent", "years", "year", "experience", "experienced", "skills",
        "skill", "knowledge", "understanding", "required", "requirements",
        "requirement", "preferred", "plus", "nice", "must", "should",
        "responsibilities", "responsibility", "including", "etc", "such",
        "well", "like", "using", "use", "used", "new", "across", "within",
        "about", "into", "over", "more", "most", "other", "others", "per",
        "via", "e.g", "i.e", "also", "both", "each", "than", "then", "when",
        "where", "while", "which", "what", "how", "why", "there", "here",
        "based", "help", "helping", "ensure", "ensuring", "build", "building",
        "develop", "developing", "support", "supporting", "provide",
        "providing", "lead", "leading", "manage", "managing", "deliver",
        "delivering", "looking", "seeking", "join", "joining", "opportunity",
    }
)


@dataclass(frozen=True)
class _SkillMatch:
    """Outcome of comparing one set of skills against another."""

    matched: list[str]
    missing: list[str]
    score: float


class ResumeMatcherService:
    """Compute deterministic resume-to-JD match scores and breakdowns."""

    def __init__(self, weights: dict[str, float] | None = None) -> None:
        """Create a matcher with optional custom sub-score weights.

        Args:
            weights: Optional mapping with ``"skills"``, ``"experience"`` and
                ``"education"`` relative weights. Defaults to
                :data:`DEFAULT_WEIGHTS`. Values need not sum to 1; they are
                renormalised internally.
        """
        self._weights = dict(weights or DEFAULT_WEIGHTS)

    # -- Public API ---------------------------------------------------------

    def compute_match(
        self, parsed_resume: ParsedResume, scraped_jd: ScrapedJD
    ) -> MatchBreakdown:
        """Compute a weighted match score with a detailed breakdown.

        Blends three sub-scores — skills, experience, and education
        (Requirement 4.4) — into an overall 0–100 score (Requirement 4.1),
        reports matched/missing skills and experience keywords
        (Requirement 4.2), and assigns a summary category label
        (Requirement 4.3).

        Dimensions for which the JD provides no signal are dropped from the
        weighted blend and the remaining weights are renormalised, so an absent
        dimension neither inflates nor deflates the overall score.

        Args:
            parsed_resume: The user's parsed base resume.
            scraped_jd: The scraped, structured job description.

        Returns:
            A fully-populated :class:`MatchBreakdown`.
        """
        skills_match = self._compute_skills_score(
            parsed_resume.skills, scraped_jd
        )
        experience_result = self._compute_experience_score(
            parsed_resume.experience, parsed_resume.skills, scraped_jd
        )
        education_score = self._compute_education_score(
            parsed_resume.education, scraped_jd
        )

        overall = self._blend_scores(
            skills_score=skills_match.score,
            experience_score=experience_result.score,
            education_score=education_score,
            has_skills_signal=self._jd_has_skill_signal(scraped_jd),
            has_experience_signal=bool(experience_result.matched or experience_result.missing),
            has_education_signal=bool(self._jd_education_keywords(scraped_jd)),
        )

        return MatchBreakdown(
            overall_score=round(overall, 2),
            skills_score=round(skills_match.score, 2),
            experience_score=round(experience_result.score, 2),
            education_score=round(education_score, 2),
            matched_skills=skills_match.matched,
            missing_skills=skills_match.missing,
            matched_experience_keywords=experience_result.matched,
            missing_experience_keywords=experience_result.missing,
            category=self._categorize_score(overall),
        )

    # -- Sub-score: skills --------------------------------------------------

    def _compute_skills_score(
        self, resume_skills: list[str], scraped_jd: ScrapedJD
    ) -> _SkillMatch:
        """Compare resume skills against the JD's required/preferred skills.

        Required skills are weighted more heavily than preferred skills so that
        missing a required skill costs more than missing a nice-to-have one.
        Matching is case-insensitive and token-aware (a resume skill matches a
        JD skill when either contains the other as a whole phrase/token).

        Args:
            resume_skills: Skills extracted from the resume.
            scraped_jd: The scraped JD (its ``required_skills`` and
                ``preferred_skills`` drive the comparison).

        Returns:
            A :class:`_SkillMatch` with matched skills, missing skills, and a
            0–100 score. When the JD lists no skills at all, the score is
            ``0.0`` and both lists are empty (the dimension carries no signal).
        """
        required = self._normalise_list(scraped_jd.required_skills)
        preferred = self._normalise_list(scraped_jd.preferred_skills)
        resume_norm = self._normalise_list(resume_skills)

        if not required and not preferred:
            return _SkillMatch(matched=[], missing=[], score=0.0)

        matched: list[str] = []
        missing: list[str] = []

        # Weighted tallies: required skills count double.
        required_weight = 2.0
        preferred_weight = 1.0
        total_weight = 0.0
        earned_weight = 0.0

        for skill in required:
            total_weight += required_weight
            if self._skill_present(skill, resume_norm):
                earned_weight += required_weight
                matched.append(skill)
            else:
                missing.append(skill)

        for skill in preferred:
            # Skip duplicates already counted as required.
            if skill in required:
                continue
            total_weight += preferred_weight
            if self._skill_present(skill, resume_norm):
                earned_weight += preferred_weight
                matched.append(skill)
            else:
                missing.append(skill)

        score = (earned_weight / total_weight * 100.0) if total_weight else 0.0
        return _SkillMatch(
            matched=self._dedupe_preserve_order(matched),
            missing=self._dedupe_preserve_order(missing),
            score=score,
        )

    # -- Sub-score: experience ----------------------------------------------

    def _compute_experience_score(
        self,
        resume_experience: list[WorkExperience],
        resume_skills: list[str],
        scraped_jd: ScrapedJD,
    ) -> _SkillMatch:
        """Compare resume experience text against salient JD keywords.

        Derives a set of salient keywords from the JD description body (and its
        skills) by tokenising, discarding stop-words, and keeping meaningful
        terms. Each keyword is then looked for across the resume's experience
        entries (titles, descriptions, highlights) and its skills. The score is
        the proportion of JD keywords found.

        Args:
            resume_experience: Work-experience entries from the resume.
            resume_skills: Skills from the resume (also searched, since skills
                frequently restate experience keywords).
            scraped_jd: The scraped JD whose text supplies the keywords.

        Returns:
            A :class:`_SkillMatch` whose ``matched``/``missing`` are JD
            experience keywords and whose ``score`` is 0–100. When the JD
            yields no keywords, the score is ``0.0`` and both lists are empty.
        """
        jd_keywords = self._jd_experience_keywords(scraped_jd)
        if not jd_keywords:
            return _SkillMatch(matched=[], missing=[], score=0.0)

        haystack = self._experience_haystack(resume_experience, resume_skills)

        matched: list[str] = []
        missing: list[str] = []
        for keyword in jd_keywords:
            if self._keyword_in_text(keyword, haystack):
                matched.append(keyword)
            else:
                missing.append(keyword)

        score = len(matched) / len(jd_keywords) * 100.0
        return _SkillMatch(matched=matched, missing=missing, score=score)

    # -- Sub-score: education -----------------------------------------------

    def _compute_education_score(
        self, resume_education: list[Education], scraped_jd: ScrapedJD
    ) -> float:
        """Compare resume education against the JD's education requirements.

        Looks for degree-level keywords (e.g. "bachelor", "master") in the JD
        text. When the JD specifies none, education is treated as a non-signal
        and this returns ``0.0`` (the dimension is later dropped from the blend
        by :meth:`compute_match`). When the JD does require a degree, the score
        reflects whether the resume lists any education and, more specifically,
        whether it matches the degree level(s) the JD asks for.

        Args:
            resume_education: Education entries from the resume.
            scraped_jd: The scraped JD whose text may mention degree levels.

        Returns:
            A 0–100 education sub-score.
        """
        jd_degree_keywords = self._jd_education_keywords(scraped_jd)
        if not jd_degree_keywords:
            return 0.0

        if not resume_education:
            return 0.0

        resume_edu_text = " ".join(
            " ".join(
                part
                for part in (
                    edu.degree,
                    edu.field_of_study,
                    edu.institution,
                )
                if part
            )
            for edu in resume_education
        ).lower()

        if not resume_edu_text.strip():
            return 0.0

        # Full credit if any JD-required degree level appears in the resume's
        # education; partial credit if the resume lists some education but not
        # the specific level the JD requested.
        for keyword in jd_degree_keywords:
            if keyword in resume_edu_text:
                return 100.0

        return 60.0

    # -- Overall blend ------------------------------------------------------

    def _blend_scores(
        self,
        *,
        skills_score: float,
        experience_score: float,
        education_score: float,
        has_skills_signal: bool,
        has_experience_signal: bool,
        has_education_signal: bool,
    ) -> float:
        """Blend sub-scores into a 0–100 overall score using renormalised weights.

        Only dimensions that carry a signal from the JD contribute. Their
        weights (from :data:`DEFAULT_WEIGHTS`) are renormalised to sum to 1 so
        that an absent dimension neither helps nor hurts. When no dimension
        carries a signal, the overall score is ``0.0``.
        """
        contributions: list[tuple[float, float]] = []  # (weight, score)
        if has_skills_signal:
            contributions.append((self._weights.get("skills", 0.0), skills_score))
        if has_experience_signal:
            contributions.append(
                (self._weights.get("experience", 0.0), experience_score)
            )
        if has_education_signal:
            contributions.append(
                (self._weights.get("education", 0.0), education_score)
            )

        total_weight = sum(weight for weight, _ in contributions)
        if total_weight <= 0:
            return 0.0

        blended = sum(weight * score for weight, score in contributions)
        return blended / total_weight

    # -- Category -----------------------------------------------------------

    @staticmethod
    def _categorize_score(score: float) -> MatchCategory:
        """Map an overall 0–100 score to a category label (Requirement 4.3).

        * ``score >= 75`` → ``"Strong Match"``
        * ``score >= 50`` → ``"Moderate Match"``
        * otherwise       → ``"Weak Match"``
        """
        if score >= _STRONG_MATCH_THRESHOLD:
            return "Strong Match"
        if score >= _MODERATE_MATCH_THRESHOLD:
            return "Moderate Match"
        return "Weak Match"

    # -- JD keyword derivation ----------------------------------------------

    def _jd_experience_keywords(self, scraped_jd: ScrapedJD) -> list[str]:
        """Derive salient experience keywords from the JD.

        Combines the JD's skills with meaningful tokens from the description
        body (stop-words removed, short tokens dropped), de-duplicated while
        preserving first-seen order.
        """
        keywords: list[str] = []

        # Skills are strong experience signals; include them verbatim.
        keywords.extend(self._normalise_list(scraped_jd.required_skills))
        keywords.extend(self._normalise_list(scraped_jd.preferred_skills))

        # Salient tokens from the description body.
        for token in self._tokenise(scraped_jd.description_body):
            if len(token) < 3:
                continue
            if token in _STOP_WORDS:
                continue
            if token.isdigit():
                continue
            keywords.append(token)

        return self._dedupe_preserve_order(keywords)

    def _jd_education_keywords(self, scraped_jd: ScrapedJD) -> list[str]:
        """Return the degree-level keywords the JD mentions, if any."""
        text = (
            f"{scraped_jd.description_body or ''} "
            f"{scraped_jd.experience_required or ''}"
        ).lower()
        return [kw for kw in _DEGREE_KEYWORDS if kw in text]

    @staticmethod
    def _jd_has_skill_signal(scraped_jd: ScrapedJD) -> bool:
        """True when the JD lists any required or preferred skills."""
        return bool(scraped_jd.required_skills or scraped_jd.preferred_skills)

    # -- Text helpers -------------------------------------------------------

    def _experience_haystack(
        self, experience: list[WorkExperience], skills: list[str]
    ) -> str:
        """Build a single lower-cased search string from resume experience/skills."""
        parts: list[str] = []
        for entry in experience:
            for value in (
                entry.title,
                entry.company,
                entry.description,
            ):
                if value:
                    parts.append(value)
            parts.extend(h for h in entry.highlights if h)
        parts.extend(s for s in skills if s)
        return " ".join(parts).lower()

    @staticmethod
    def _keyword_in_text(keyword: str, text: str) -> bool:
        """Whole-word / phrase containment check for ``keyword`` in ``text``.

        Uses word boundaries so ``"go"`` does not match ``"google"`` while still
        allowing multi-word phrases like ``"machine learning"``.
        """
        if not keyword or not text:
            return False
        pattern = r"\b" + re.escape(keyword) + r"\b"
        return re.search(pattern, text) is not None

    @classmethod
    def _skill_present(cls, jd_skill: str, resume_skills: list[str]) -> bool:
        """Whether ``jd_skill`` is covered by any of ``resume_skills``.

        Matches when a resume skill equals the JD skill, or when either string
        contains the other as a whole-word/phrase (tolerating parenthetical
        expansions and extra descriptors).
        """
        for resume_skill in resume_skills:
            if resume_skill == jd_skill:
                return True
            if cls._keyword_in_text(jd_skill, resume_skill):
                return True
            if cls._keyword_in_text(resume_skill, jd_skill):
                return True
        return False

    @staticmethod
    def _tokenise(text: str) -> list[str]:
        """Lower-case and split text into alphanumeric word tokens."""
        if not text:
            return []
        return re.findall(r"[a-zA-Z0-9][a-zA-Z0-9\+\#\.]*", text.lower())

    @staticmethod
    def _normalise_list(values: list[str]) -> list[str]:
        """Trim, lower-case, drop empties, and de-duplicate a list of strings."""
        result: list[str] = []
        seen: set[str] = set()
        for value in values or []:
            if not isinstance(value, str):
                continue
            cleaned = value.strip().lower()
            if not cleaned or cleaned in seen:
                continue
            seen.add(cleaned)
            result.append(cleaned)
        return result

    @staticmethod
    def _dedupe_preserve_order(values: list[str]) -> list[str]:
        """De-duplicate a list (case-insensitive) preserving first-seen order."""
        result: list[str] = []
        seen: set[str] = set()
        for value in values:
            key = value.lower()
            if key in seen:
                continue
            seen.add(key)
            result.append(value)
        return result
