"""Rule-based policy verdict engine.

Given a question and the evidence gathered for it (text/multimodal
chunks + graph facts, from the bounded agent — app/agent/controller.py),
produces a PASS/FAIL/UNKNOWN/CONFLICT verdict with severity, confidence,
and a recommendation. Deliberately rule-based (negation/affirmation
marker scanning, app/policy/markers.py), not LLM-judged — consistent
with docs/DECISIONS.md ADR-005/ADR-008's finding that the local models
practical on this machine are not reliable for structured judgment
tasks; a marker-based scan is fully deterministic, inspectable, and
testable, and never invents a verdict beyond what the evidence text
literally contains (CLAUDE.md rule 3).

Verdict semantics:
- **UNKNOWN**: no evidence was retrieved, or the evidence has
  essentially no lexical overlap with the question — an honest "we
  don't know" rather than a guess.
- **PASS**: evidence contains an affirmation marker and no negation.
- **FAIL**: evidence contains a negation marker and no affirmation.
- **CONFLICT**: evidence contains BOTH — a real contradiction between
  (or within) sources, surfaced rather than silently resolved one way.
  This is the contradiction-detection requirement: a conflicting pair of
  claims is a first-class outcome, not collapsed into PASS or FAIL.

Evidence granularity (fixed — see docs/DECISIONS.md ADR-010): relevance
and marker scanning happen per SENTENCE/bullet (`_logical_units`), not
per whole retrieved chunk. Phase 1's chunker groups ~1000 characters
together, which often means 2-3 unrelated bullet points end up in one
chunk (e.g. a "Known gaps" section covering three different topics).
Scanning at chunk granularity meant a question relevant to only one
bullet could still pick up an unrelated bullet's negation/affirmation
just because it shared the chunk — this was a known, documented
limitation (ADR-009) and is now fixed without touching chunking,
retrieval, or citations: a `Citation` still points at the whole chunk
(the actual retrieval/provenance unit), only the *verdict* reasoning
is now scoped to the specific sentence that's actually relevant.
"""

import re
from dataclasses import dataclass

from app.policy.markers import infer_severity, max_severity, scan_text

_WORD_RE = re.compile(r"[a-zA-Z0-9]{4,}")

# Generic, low-information words common in architecture prose — excluded
# from keyword-overlap relevance matching. Caught during development:
# "does the system support biometric login?" shared "system" and
# "login" with an unrelated doc's generic intro sentence ("Handles user
# registration, login..."), clearing the overlap-count threshold and
# producing a false PASS for a topic the corpus never actually
# discusses. This is a short list of genuinely generic words, not
# curated per-topic vocabulary (CLAUDE.md rule 8 — still simple/general).
_STOPWORDS = frozenset(
    {
        "does", "have", "with", "this", "that", "from", "into", "system",
        "support", "user", "users", "used", "using", "service", "services",
        "data", "will", "when", "then", "also", "each", "your", "their",
    }
)


@dataclass(frozen=True)
class PolicyVerdict:
    verdict: str  # PASS | FAIL | UNKNOWN | CONFLICT
    severity: str  # low | medium | high | critical
    confidence: float
    recommendation: str
    affirming_texts: list[str]
    denying_texts: list[str]


_MIN_OVERLAP_COUNT = 2  # see _is_relevant docstring
_SENTENCE_END_RE = re.compile(r"(?<=[.!?])\s+")


def _logical_units(text: str) -> list[str]:
    """Splits a chunk of text into bullet/sentence-level units, rejoining
    a bullet's own wrapped continuation lines first (so a phrase split
    across a line-wrap boundary — e.g. Phase 1's chunker preserves the
    source file's ~72-column wrapping — isn't itself split into two
    separate, incomplete units), then splitting further on sentence
    punctuation. This is what makes evidence scanning sentence-level
    rather than chunk-level (see module docstring / ADR-010)."""
    blocks: list[str] = []
    current: list[str] = []

    def flush() -> None:
        if current:
            blocks.append(" ".join(current))
            current.clear()

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            flush()
            continue
        if line.startswith(("- ", "* ")):
            flush()
            current.append(line[2:].strip())
        else:
            current.append(line)
    flush()

    units: list[str] = []
    for block in blocks:
        for part in _SENTENCE_END_RE.split(block):
            part = part.strip()
            # Drop list-header lines (e.g. "The Baseline policy enforces
            # or disallows the following:") — caught testing against the
            # real public corpus (data/samples/public/): a header merely
            # introducing a list trivially contains both an affirmation
            # word ("enforces") and a negation word ("disallows"),
            # producing a false CONFLICT on a purely structural sentence
            # that makes no substantive claim of its own.
            if part and not part.endswith(":"):
                units.append(part)
    return units


def _keywords(text: str) -> set[str]:
    return {w for w in (m.lower() for m in _WORD_RE.findall(text)) if w not in _STOPWORDS}


def _relevance(question_keywords: set[str], text: str) -> float:
    if not question_keywords:
        return 0.0
    return len(question_keywords & _keywords(text)) / len(question_keywords)


def _is_relevant(question_keywords: set[str], text: str, *, min_relevance_overlap: float) -> bool:
    """A text counts as relevant only if it clears BOTH a fractional
    overlap threshold AND a minimum raw shared-keyword count. The count
    floor matters on its own: caught during development — a 5-keyword
    question sharing just one common word ("user") with an unrelated
    document's unrelated "Known gaps" paragraph already clears a 0.05
    fractional threshold (1/5 = 0.20), letting that paragraph's
    negation markers contaminate a verdict about something else
    entirely. Requiring at least 2 shared keywords (when the question
    has that many to give) filters out single-common-word coincidences
    without needing a curated stopword list.
    """
    overlap_count = len(question_keywords & _keywords(text))
    if len(question_keywords) >= _MIN_OVERLAP_COUNT and overlap_count < _MIN_OVERLAP_COUNT:
        return False
    return _relevance(question_keywords, text) >= min_relevance_overlap


def evaluate(
    question: str, evidence_texts: list[str], *, min_relevance_overlap: float = 0.05
) -> PolicyVerdict:
    if not evidence_texts:
        return PolicyVerdict(
            verdict="UNKNOWN",
            severity="low",
            confidence=1.0,
            recommendation=(
                "No evidence was retrieved for this question. Ingest documentation "
                "that covers this topic, or rephrase the question."
            ),
            affirming_texts=[],
            denying_texts=[],
        )

    # Only scan for negation/affirmation markers within evidence that is
    # actually relevant to the question — otherwise an unrelated
    # document's negation (e.g. a different service's "no documented
    # rate limiting") bleeds into a verdict about something else
    # entirely, since hybrid retrieval's top-k routinely spans multiple
    # documents. This was caught during development: without this
    # filter, nearly every question returned CONFLICT because the
    # small synthetic corpus's "Known gaps" sections (negations) and
    # normal prose (affirmations) both appear somewhere in most top-k
    # result sets regardless of relevance.
    #
    # Scanning happens per sentence/bullet (_logical_units), not per
    # whole chunk — see module docstring and ADR-010: a chunk routinely
    # contains several unrelated bullets, and without this a question
    # relevant to only one of them could still pick up another bullet's
    # marker just because it shares the chunk.
    question_keywords = _keywords(question)
    all_units = [unit for text in evidence_texts for unit in _logical_units(text)]
    relevant_texts = [
        unit
        for unit in all_units
        if _is_relevant(question_keywords, unit, min_relevance_overlap=min_relevance_overlap)
    ]

    if not relevant_texts:
        best_overlap = max(
            (_relevance(question_keywords, unit) for unit in all_units), default=0.0
        )
        return PolicyVerdict(
            verdict="UNKNOWN",
            severity="low",
            confidence=round(1.0 - best_overlap, 2),
            recommendation=(
                "Retrieved evidence does not appear related to this question. "
                "Ingest more relevant documentation or narrow the question."
            ),
            affirming_texts=[],
            denying_texts=[],
        )

    affirming: list[str] = []
    denying: list[str] = []
    for text in relevant_texts:
        has_neg, has_pos = scan_text(text)
        if has_neg:
            denying.append(text)
        if has_pos:
            affirming.append(text)

    if not affirming and not denying:
        avg_overlap = sum(_relevance(question_keywords, t) for t in relevant_texts) / len(
            relevant_texts
        )
        return PolicyVerdict(
            verdict="UNKNOWN",
            severity="low",
            confidence=round(avg_overlap, 2),
            recommendation=(
                "Relevant evidence was found but it does not explicitly confirm or "
                "deny this control. Manual review recommended."
            ),
            affirming_texts=[],
            denying_texts=[],
        )

    if affirming and denying:
        severity = max_severity([infer_severity(t) for t in denying])
        return PolicyVerdict(
            verdict="CONFLICT",
            severity=severity,
            confidence=0.5,
            recommendation=(
                "Evidence conflicts: some sources affirm this control is in place, "
                "others indicate it is not. Manually reconcile the sources listed "
                "in citations before relying on either claim."
            ),
            affirming_texts=affirming,
            denying_texts=denying,
        )

    if denying:
        severity = infer_severity(" ".join(denying))
        confidence = round(min(1.0, 0.5 + 0.15 * len(denying)), 2)
        return PolicyVerdict(
            verdict="FAIL",
            severity=severity,
            confidence=confidence,
            recommendation=(
                "A gap was found: " + denying[0].strip()[:200] + ". Assign an owner, "
                "remediate, and add verification."
            ),
            affirming_texts=[],
            denying_texts=denying,
        )

    confidence = round(min(1.0, 0.5 + 0.15 * len(affirming)), 2)
    return PolicyVerdict(
        verdict="PASS",
        severity="low",
        confidence=confidence,
        recommendation="No action needed; evidence confirms this control is addressed.",
        affirming_texts=affirming,
        denying_texts=[],
    )
