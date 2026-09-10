"""Minimal groundedness evaluation.

This is a lexical-overlap heuristic, NOT a real entailment/NLI check —
deliberately minimal per the Phase 3 scope (a real check would need an
NLI model or an LLM-judge call, which is future work; see
docs/ROADMAP.md's evaluation phase for the fuller golden-set approach).
What it catches: an answer that talks about things nowhere in the cited
evidence (a strong signal of hallucination). What it does NOT catch:
subtle misstatements that reuse the evidence's own vocabulary.

Score = fraction of the answer's significant words (>=4 chars,
alphanumeric) that also appear in the cited chunk texts. A correct
abstention (the UNKNOWN sentinel) scores 1.0 — abstaining because the
evidence is insufficient is the correctly grounded behavior, not a
failure of it.
"""

import re
from dataclasses import dataclass

from app.generation.providers import UNKNOWN_ANSWER

_WORD_PATTERN = re.compile(r"[a-zA-Z0-9]{4,}")


@dataclass(frozen=True)
class GroundednessResult:
    score: float
    is_grounded: bool
    is_abstention: bool


def _significant_words(text: str) -> set[str]:
    return {w.lower() for w in _WORD_PATTERN.findall(text)}


def score_groundedness(
    answer_text: str, cited_texts: list[str], *, min_score: float
) -> GroundednessResult:
    if answer_text.strip() == UNKNOWN_ANSWER:
        return GroundednessResult(score=1.0, is_grounded=True, is_abstention=True)

    answer_words = _significant_words(answer_text)
    if not answer_words:
        return GroundednessResult(score=0.0, is_grounded=False, is_abstention=False)

    evidence_words: set[str] = set()
    for text in cited_texts:
        evidence_words |= _significant_words(text)

    overlap = len(answer_words & evidence_words) / len(answer_words)
    return GroundednessResult(
        score=overlap, is_grounded=overlap >= min_score, is_abstention=False
    )
