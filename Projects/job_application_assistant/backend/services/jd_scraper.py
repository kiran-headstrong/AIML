"""
JD Scraper Service.

Fetch and extract structured job-description data from LinkedIn and Naukri job
posting URLs. The service:

* detects the hosting platform from the URL (``_detect_platform``),
* fetches the page with an async ``httpx`` client using a realistic
  ``User-Agent`` (``scrape``),
* parses the returned HTML with BeautifulSoup4 using platform-specific helpers
  (``_scrape_linkedin`` / ``_scrape_naukri``), tolerating markup variation via
  multiple selector fallbacks,
* exposes ``parse_to_structured`` to turn raw text/HTML into a
  :class:`~schemas.ScrapedJD`, and
* exposes ``format_pretty`` to render a :class:`~schemas.ScrapedJD` as a clean,
  human-readable string.

``parse_to_structured`` and ``format_pretty`` are intentionally designed to be
round-trippable: the labelled, section-oriented layout produced by
``format_pretty`` can be re-parsed by ``parse_to_structured`` into an equivalent
structured object (Requirement 15.3).

Import style follows the backend package convention (direct module imports),
since ``main.py`` inserts the backend directory onto ``sys.path``.
"""
from __future__ import annotations

import re
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup

from schemas import ScrapedJD


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class UnsupportedURLError(ValueError):
    """Raised when a URL is not a recognised LinkedIn or Naukri job posting.

    Carries a descriptive message explaining why the URL is unsupported
    (Requirement 1.3).
    """


class ScrapeError(RuntimeError):
    """Raised when a valid URL cannot be fetched or accessed.

    Covers network errors, timeouts, non-200 responses, and access
    restrictions, with a descriptive message indicating the failure reason
    (Requirement 1.4).
    """


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

#: Realistic desktop browser User-Agent to reduce the chance of being blocked.
_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
)

_DEFAULT_HEADERS = {
    "User-Agent": _USER_AGENT,
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;q=0.9,"
        "image/avif,image/webp,*/*;q=0.8"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}

#: Request timeout in seconds.
_TIMEOUT_SECONDS = 20.0

#: Field labels used by ``format_pretty`` / ``parse_to_structured`` so the two
#: operations stay in sync (round-trip property, Requirement 15.3).
_LABEL_TITLE = "Job Title"
_LABEL_COMPANY = "Company"
_LABEL_LOCATION = "Location"
_LABEL_EXPERIENCE = "Experience Required"
_LABEL_DESCRIPTION = "Description"
_LABEL_REQUIRED = "Required Skills"
_LABEL_PREFERRED = "Preferred Skills"

#: Headings (lower-cased) that introduce a "required / must-have" skills block.
_REQUIRED_HEADINGS = (
    "required skills",
    "requirements",
    "must have",
    "must-have",
    "must haves",
    "key skills",
    "mandatory skills",
    "what you'll need",
    "what you need",
    "qualifications",
)

#: Headings (lower-cased) that introduce a "preferred / nice-to-have" block.
_PREFERRED_HEADINGS = (
    "preferred skills",
    "preferred",
    "good to have",
    "good-to-have",
    "nice to have",
    "nice-to-have",
    "bonus",
    "plus",
    "desired skills",
    "optional",
)


class JDScraperService:
    """Scrape and parse job descriptions from LinkedIn and Naukri."""

    # -- Public API ---------------------------------------------------------

    async def scrape(self, url: str) -> ScrapedJD:
        """Scrape and parse a job posting URL into a :class:`ScrapedJD`.

        Detects the platform, fetches the page over async HTTP, and delegates
        to the platform-specific parser.

        Args:
            url: A LinkedIn or Naukri job posting URL.

        Returns:
            A :class:`ScrapedJD` with ``raw_html`` preserved for re-parsing.

        Raises:
            UnsupportedURLError: If the URL is not a LinkedIn/Naukri posting.
            ScrapeError: If the page cannot be fetched (network error, timeout,
                non-200 status, or access restriction).
        """
        platform = self._detect_platform(url)
        if platform == "linkedin":
            return await self._scrape_linkedin(url)
        return await self._scrape_naukri(url)

    def _detect_platform(self, url: str) -> str:
        """Return ``'linkedin'`` or ``'naukri'`` based on the URL host.

        Args:
            url: The job posting URL.

        Returns:
            ``'linkedin'`` or ``'naukri'``.

        Raises:
            UnsupportedURLError: For any URL whose host is not a recognised
                LinkedIn or Naukri domain (Requirement 1.3).
        """
        parsed = urlparse(url.strip())
        host = (parsed.netloc or parsed.path).lower()
        # Strip a leading "www." and any port suffix for matching.
        host = host.split("@")[-1].split(":")[0]
        if host.startswith("www."):
            host = host[4:]

        if not parsed.scheme and not host:
            raise UnsupportedURLError(
                f"'{url}' is not a valid URL. Provide a full LinkedIn or "
                "Naukri job posting URL (e.g. https://www.linkedin.com/jobs/...)."
            )

        if "linkedin.com" in host:
            return "linkedin"
        if "naukri.com" in host:
            return "naukri"

        raise UnsupportedURLError(
            f"Unsupported URL '{url}'. Only LinkedIn (linkedin.com) and Naukri "
            "(naukri.com) job posting URLs are supported."
        )

    def parse_to_structured(self, raw_text: str, raw_html: str = "") -> ScrapedJD:
        """Parse raw JD text (and optional HTML) into structured fields.

        Extracts the job title, company name, location, experience required,
        description body, and required/preferred skills (Requirements 1.1, 1.2,
        15.1). Skills are extracted heuristically from labelled fields when the
        text was produced by :meth:`format_pretty`, otherwise from
        "requirements"/"must have" versus "preferred"/"good to have" sections.

        The method is resilient: missing information degrades gracefully to an
        empty string / ``None`` / empty list rather than raising.

        Args:
            raw_text: The raw JD text to parse.
            raw_html: Optional original HTML, preserved on the returned object
                and used as a secondary source for skill extraction.

        Returns:
            A structured :class:`ScrapedJD`.
        """
        text = (raw_text or "").replace("\r\n", "\n").replace("\r", "\n")

        labelled = self._parse_labelled(text)
        if labelled is not None:
            labelled.raw_html = raw_html or labelled.raw_html
            return labelled

        # Fall back to free-form heuristic parsing.
        lines = [ln.strip() for ln in text.split("\n")]
        non_empty = [ln for ln in lines if ln]

        job_title = non_empty[0] if non_empty else ""
        company_name = non_empty[1] if len(non_empty) > 1 else ""
        location = self._find_value(text, ("location",))
        experience = self._find_value(
            text, ("experience required", "experience", "exp")
        )

        required_skills = self._extract_section_skills(text, _REQUIRED_HEADINGS)
        preferred_skills = self._extract_section_skills(text, _PREFERRED_HEADINGS)

        return ScrapedJD(
            job_title=job_title,
            company_name=company_name,
            location=location,
            experience_required=experience,
            description_body=text.strip(),
            required_skills=required_skills,
            preferred_skills=preferred_skills,
            raw_html=raw_html,
        )

    def format_pretty(self, jd: ScrapedJD) -> str:
        """Render a :class:`ScrapedJD` as a clean, readable multi-line string.

        The output uses stable ``Label: value`` lines and labelled skill
        sections so it can be re-parsed by :meth:`parse_to_structured` into an
        equivalent object (Requirements 15.2, 15.3).

        Args:
            jd: The structured job description to format.

        Returns:
            A human-readable, re-parsable string representation.
        """
        lines: list[str] = [
            f"{_LABEL_TITLE}: {jd.job_title}",
            f"{_LABEL_COMPANY}: {jd.company_name}",
            f"{_LABEL_LOCATION}: {jd.location or ''}",
            f"{_LABEL_EXPERIENCE}: {jd.experience_required or ''}",
            "",
            f"{_LABEL_DESCRIPTION}:",
            (jd.description_body or "").strip(),
            "",
            f"{_LABEL_REQUIRED}:",
        ]
        lines.extend(f"- {skill}" for skill in jd.required_skills)
        lines.append("")
        lines.append(f"{_LABEL_PREFERRED}:")
        lines.extend(f"- {skill}" for skill in jd.preferred_skills)

        return "\n".join(lines).rstrip() + "\n"

    # -- Platform scrapers --------------------------------------------------

    async def _scrape_linkedin(self, url: str) -> ScrapedJD:
        """Fetch and parse a LinkedIn job posting into a :class:`ScrapedJD`."""
        html = await self._fetch(url)
        soup = BeautifulSoup(html, "html.parser")

        job_title = self._first_text(
            soup,
            [
                "h1.top-card-layout__title",
                "h1.topcard__title",
                "h1.job-details-jobs-unified-top-card__job-title",
                "h1",
            ],
        )
        company_name = self._first_text(
            soup,
            [
                "a.topcard__org-name-link",
                "span.topcard__flavor",
                "a.job-details-jobs-unified-top-card__company-name",
                ".topcard__org-name-link",
                ".top-card-layout__card .topcard__flavor",
            ],
        )
        location = self._first_text(
            soup,
            [
                "span.topcard__flavor--bullet",
                ".top-card-layout__second-subline .topcard__flavor--bullet",
                ".job-details-jobs-unified-top-card__bullet",
            ],
        )
        description_body = self._first_text(
            soup,
            [
                "div.show-more-less-html__markup",
                "div.description__text",
                "section.description",
                ".jobs-description__content",
            ],
        )

        return self._assemble(
            html=html,
            job_title=job_title,
            company_name=company_name,
            location=location,
            experience=None,
            description_body=description_body,
        )

    async def _scrape_naukri(self, url: str) -> ScrapedJD:
        """Fetch and parse a Naukri job posting into a :class:`ScrapedJD`."""
        html = await self._fetch(url)
        soup = BeautifulSoup(html, "html.parser")

        job_title = self._first_text(
            soup,
            [
                "h1.jd-header-title",
                "h1.styles_jd-header-title__rZwM1",
                "section.jd-header h1",
                "h1",
            ],
        )
        company_name = self._first_text(
            soup,
            [
                "div.jd-header-comp-name a",
                "a.jd-header-comp-name",
                "div.styles_jd-header-comp-name__MvqAI a",
                ".jd-header-comp-name",
            ],
        )
        location = self._first_text(
            soup,
            [
                "span.location span.ni-job-tuple-icon-srp-location",
                "div.styles_jhc__loc___Du2H",
                "span.locWdth",
                ".loc .location",
            ],
        )
        experience = self._first_text(
            soup,
            [
                "div.styles_jhc__exp__k_giM",
                "span.exp span.ni-job-tuple-icon-srp-experience",
                "span.expwdth",
                ".exp .experience",
            ],
        )
        description_body = self._first_text(
            soup,
            [
                "div.styles_JDC__dang-inner-html__h0K4t",
                "section.job-desc",
                "div.dang-inner-html",
                ".job-description",
            ],
        )

        return self._assemble(
            html=html,
            job_title=job_title,
            company_name=company_name,
            location=location,
            experience=experience,
            description_body=description_body,
        )

    # -- Internal helpers ---------------------------------------------------

    async def _fetch(self, url: str) -> str:
        """Fetch a URL and return its HTML body.

        Uses an async ``httpx`` client with a realistic ``User-Agent``, a
        reasonable timeout, and redirect following.

        Raises:
            ScrapeError: On network/transport errors, timeouts, or non-2xx
                responses (including access restrictions).
        """
        try:
            async with httpx.AsyncClient(
                headers=_DEFAULT_HEADERS,
                timeout=_TIMEOUT_SECONDS,
                follow_redirects=True,
            ) as client:
                response = await client.get(url)
        except httpx.TimeoutException as exc:
            raise ScrapeError(
                f"Timed out while fetching '{url}'. The server took too long "
                "to respond; please try again later."
            ) from exc
        except httpx.HTTPError as exc:
            raise ScrapeError(
                f"Failed to fetch '{url}' due to a network error: {exc}."
            ) from exc

        if response.status_code in (401, 403):
            raise ScrapeError(
                f"Access to '{url}' was denied (HTTP {response.status_code}). "
                "The job posting may require login or be restricted."
            )
        if response.status_code == 404:
            raise ScrapeError(
                f"The job posting at '{url}' was not found (HTTP 404). "
                "It may have been removed or the URL is incorrect."
            )
        if response.status_code >= 400:
            raise ScrapeError(
                f"Failed to fetch '{url}': the server responded with HTTP "
                f"{response.status_code}."
            )

        return response.text

    def _assemble(
        self,
        *,
        html: str,
        job_title: str,
        company_name: str,
        location: str | None,
        experience: str | None,
        description_body: str,
    ) -> ScrapedJD:
        """Build a :class:`ScrapedJD` from scraped fields plus derived skills.

        Skills are derived from the description body using the same heuristics
        as :meth:`parse_to_structured`, so scraped and re-parsed objects stay
        consistent.
        """
        required_skills = self._extract_section_skills(
            description_body, _REQUIRED_HEADINGS
        )
        preferred_skills = self._extract_section_skills(
            description_body, _PREFERRED_HEADINGS
        )

        return ScrapedJD(
            job_title=job_title or "",
            company_name=company_name or "",
            location=location or None,
            experience_required=experience or None,
            description_body=description_body or "",
            required_skills=required_skills,
            preferred_skills=preferred_skills,
            raw_html=html,
        )

    @staticmethod
    def _first_text(soup: BeautifulSoup, selectors: list[str]) -> str:
        """Return normalised text from the first matching CSS selector.

        Tries each selector in order and gracefully returns an empty string
        when none match, so parsing never crashes on missing elements.
        """
        for selector in selectors:
            try:
                element = soup.select_one(selector)
            except Exception:
                # A malformed/unsupported selector should never abort parsing.
                element = None
            if element is not None:
                text = element.get_text(separator="\n", strip=True)
                if text:
                    return re.sub(r"\n{3,}", "\n\n", text).strip()
        return ""

    def _parse_labelled(self, text: str) -> ScrapedJD | None:
        """Parse text previously produced by :meth:`format_pretty`.

        Returns ``None`` when the text does not look like labelled output, so
        the caller can fall back to free-form parsing.
        """
        if f"{_LABEL_TITLE}:" not in text:
            return None

        job_title = self._find_value(text, (_LABEL_TITLE.lower(),)) or ""
        company_name = self._find_value(text, (_LABEL_COMPANY.lower(),)) or ""
        location = self._find_value(text, (_LABEL_LOCATION.lower(),))
        experience = self._find_value(text, (_LABEL_EXPERIENCE.lower(),))

        description_body = self._extract_block(
            text,
            start_label=_LABEL_DESCRIPTION,
            end_labels=(_LABEL_REQUIRED, _LABEL_PREFERRED),
        )
        required_skills = self._extract_bullets(
            text,
            start_label=_LABEL_REQUIRED,
            end_labels=(_LABEL_PREFERRED,),
        )
        preferred_skills = self._extract_bullets(
            text,
            start_label=_LABEL_PREFERRED,
            end_labels=(),
        )

        return ScrapedJD(
            job_title=job_title,
            company_name=company_name,
            location=location,
            experience_required=experience,
            description_body=description_body,
            required_skills=required_skills,
            preferred_skills=preferred_skills,
            raw_html="",
        )

    @staticmethod
    def _find_value(text: str, labels: tuple[str, ...]) -> str | None:
        """Return the value of the first ``label: value`` line that matches.

        Matching is case-insensitive. Returns ``None`` when no label matches or
        the value is empty.
        """
        for raw_line in text.split("\n"):
            line = raw_line.strip()
            if ":" not in line:
                continue
            key, _, value = line.partition(":")
            if key.strip().lower() in labels:
                value = value.strip()
                return value or None
        return None

    @staticmethod
    def _extract_block(
        text: str, start_label: str, end_labels: tuple[str, ...]
    ) -> str:
        """Extract the body between ``start_label:`` and the next end label."""
        lines = text.split("\n")
        start_prefix = f"{start_label.lower()}:"
        end_prefixes = tuple(f"{label.lower()}:" for label in end_labels)

        collecting = False
        collected: list[str] = []
        for raw_line in lines:
            stripped = raw_line.strip()
            lowered = stripped.lower()
            if not collecting:
                if lowered.startswith(start_prefix):
                    collecting = True
                    # Capture any inline value after the label on the same line.
                    inline = stripped[len(start_label) + 1 :].strip()
                    if inline:
                        collected.append(inline)
                continue
            if end_prefixes and lowered.startswith(end_prefixes):
                break
            collected.append(raw_line)

        return "\n".join(collected).strip()

    @staticmethod
    def _extract_bullets(
        text: str, start_label: str, end_labels: tuple[str, ...]
    ) -> list[str]:
        """Extract ``- item`` bullet lines following ``start_label:``."""
        lines = text.split("\n")
        start_prefix = f"{start_label.lower()}:"
        end_prefixes = tuple(f"{label.lower()}:" for label in end_labels)

        collecting = False
        skills: list[str] = []
        for raw_line in lines:
            stripped = raw_line.strip()
            lowered = stripped.lower()
            if not collecting:
                if lowered.startswith(start_prefix):
                    collecting = True
                continue
            if end_prefixes and lowered.startswith(end_prefixes):
                break
            if stripped.startswith(("-", "*", "•")):
                skill = stripped.lstrip("-*• ").strip()
                if skill:
                    skills.append(skill)
            elif stripped == "":
                continue
            else:
                # A non-bullet, non-empty line ends the labelled list block.
                break
        return skills

    def _extract_section_skills(
        self, text: str, headings: tuple[str, ...]
    ) -> list[str]:
        """Heuristically extract skills from a named section of free-form text.

        Locates a heading (e.g. "Requirements", "Good to have"), then collects
        bullet-style or comma-separated items until the next heading or a blank
        separator. Returns an empty list when no matching section is found.
        """
        lines = text.split("\n")
        skills: list[str] = []
        collecting = False
        blank_run = 0

        for raw_line in lines:
            stripped = raw_line.strip()
            lowered = stripped.lower().rstrip(":").strip()

            if not collecting:
                if self._matches_heading(lowered, headings):
                    collecting = True
                    # Handle "Heading: a, b, c" on a single line.
                    _, _, inline = stripped.partition(":")
                    skills.extend(self._split_items(inline))
                continue

            # While collecting, stop at the next recognised heading.
            if self._is_any_heading(lowered):
                break

            if stripped == "":
                blank_run += 1
                # Two consecutive blank lines end the section.
                if blank_run >= 2:
                    break
                continue
            blank_run = 0

            if stripped.startswith(("-", "*", "•")):
                item = stripped.lstrip("-*• ").strip()
                skills.extend(self._split_items(item))
            else:
                skills.extend(self._split_items(stripped))

        # De-duplicate while preserving order.
        seen: set[str] = set()
        unique: list[str] = []
        for skill in skills:
            key = skill.lower()
            if skill and key not in seen:
                seen.add(key)
                unique.append(skill)
        return unique

    @staticmethod
    def _matches_heading(line: str, headings: tuple[str, ...]) -> bool:
        """Return True if ``line`` starts with any of ``headings``."""
        return any(line.startswith(h) for h in headings)

    @classmethod
    def _is_any_heading(cls, line: str) -> bool:
        """Return True if the line looks like a required/preferred heading."""
        return cls._matches_heading(line, _REQUIRED_HEADINGS) or cls._matches_heading(
            line, _PREFERRED_HEADINGS
        )

    @staticmethod
    def _split_items(chunk: str) -> list[str]:
        """Split a line into individual skill items on commas / semicolons."""
        chunk = chunk.strip()
        if not chunk:
            return []
        parts = re.split(r"[;,]", chunk)
        return [p.strip() for p in parts if p.strip()]
