"""Generic negation/affirmation marker scanning over evidence text — the
basis for the policy engine's PASS/FAIL/CONFLICT/UNKNOWN verdicts
(app/policy/engine.py).

Deliberately generic, not a curated per-topic rule library: the existing
synthetic sample documents' "Known gaps" sections were authored using
exactly this kind of plain-English negation ("no documented...", "is not
currently...", "without..."), so a general negation/affirmation scan
over whatever evidence the agent retrieves is both simpler than curating
per-topic rules (CLAUDE.md rule 8 — prefer simple) and more general (it
works for any question, not just ones a rule author anticipated).
"""

import re

NEGATION_PATTERNS = [
    r"\bno documented\b",
    r"\bno automated\b",
    r"\bnot currently\b",
    r"\bnot able to\b",
    r"\bdoes not\b",
    r"\bdoesn't\b",
    r"\bisn't\b",
    r"\baren't\b",
    r"\bwithout\b",
    r"\blacks?\b",
    r"\bno assigned\b",
    r"\bno mechanism\b",
    r"\bunfiltered\b",
    r"\bnot reviewed\b",
    r"\bnot rotated\b",
    r"\bmanual,? case-by-case\b",
    r"\bhas no\b",
    # Added for Phase 8's real-world public corpus (data/samples/public/):
    # official docs (Kubernetes, OWASP, NIST) phrase prohibitions
    # differently than the synthetic corpus's "no documented X" style —
    # "forbidden", "disallowed", "prohibited", "not allowed", "denied"
    # are all generic English negation-of-permission words, not curated
    # per-topic vocabulary (CLAUDE.md rule 8).
    r"\bforbidden\b",
    r"\bdisallow(?:ed|s)?\b",
    r"\bprohibited\b",
    r"\bnot allowed\b",
    r"\bdenied\b",
    # Added after a real compliance-requirement sentence ("Production
    # customer databases must not be publicly accessible.") was found to
    # match neither this list nor AFFIRMATION_PATTERNS at all, producing
    # UNKNOWN on a plainly negative (prohibitive) requirement instead of
    # FAIL. "must not"/"shall not" are the same generic class of
    # negation-of-obligation phrasing as "not allowed"/"forbidden" above
    # — just the surface form requirement/policy documents commonly use
    # ("X must not Y") rather than the "X is not allowed" form already
    # covered.
    r"\bmust not\b",
    r"\bshall not\b",
]
# Deliberately NOT included: "cannot" and "never" (removed after testing
# against real data). Both are too context-dependent — "users cannot
# act outside their intended permissions" (OWASP A01, describing how
# access control is *supposed* to work) and "passwords are never
# persisted or logged" (a *good* practice) both use these words to
# describe correct/desired behavior, not a gap. A curated per-phrase
# list can't safely capture "cannot X" as a general negation the way it
# can "no documented X" or "without X".

AFFIRMATION_PATTERNS = [
    r"\bis encrypted\b",
    r"\bare encrypted\b",
    r"\buses?\b",
    r"\bimplements?\b",
    r"\benforces?\b",
    # NOT bare "documented"/"automated" — those words appear inside the
    # negation phrases "no documented X" / "no automated Y" too (caught
    # during development: "payment-api ... has no documented rate
    # limiting" matched bare "documented" as an affirmation, producing a
    # false CONFLICT on a plain FAIL case). Only count them as
    # affirmative when explicitly positive.
    r"\bis documented\b",
    r"\bhas been documented\b",
    r"\bis automated\b",
    r"\breviewed on\b",
    r"\bcurrently (?:runs|verifies|checks|validates)\b",
    r"\bprovides?\b",
    r"\bhas an?\b",
]

_NEG_RE = re.compile("|".join(NEGATION_PATTERNS), re.IGNORECASE)
_POS_RE = re.compile("|".join(AFFIRMATION_PATTERNS), re.IGNORECASE)

HIGH_SEVERITY_KEYWORDS = (
    "password",
    "pii",
    "personally identifiable",
    "encrypt",
    "card",
    "auth",
    "secret",
    "token",
    "credential",
    "vulnerab",
)

_SEVERITY_ORDER = ("low", "medium", "high", "critical")


def scan_text(text: str) -> tuple[bool, bool]:
    """Returns (has_negation, has_affirmation) for one piece of text."""
    return bool(_NEG_RE.search(text)), bool(_POS_RE.search(text))


def infer_severity(text: str) -> str:
    lower = text.lower()
    if any(k in lower for k in HIGH_SEVERITY_KEYWORDS):
        return "high"
    return "medium"


def max_severity(severities: list[str], *, default: str = "medium") -> str:
    if not severities:
        return default
    return max(severities, key=_SEVERITY_ORDER.index)
