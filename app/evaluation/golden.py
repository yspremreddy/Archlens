"""Golden evaluation cases with ground truth — spanning the synthetic
dataset (data/samples/*.md) and the real public corpus
(data/samples/public/, see SOURCES.md). Every expected value here was
verified empirically against a running instance before being written
down (CLAUDE.md rule 3/4 — no fabricated ground truth); see
docs/DECISIONS.md ADR-011.
"""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class RetrievalCase:
    query: str
    relevant_filenames: frozenset[str]


@dataclass(frozen=True)
class ReviewCase:
    question: str
    expected_verdict: str  # PASS | FAIL | UNKNOWN | CONFLICT
    expected_citation_filename: str | None  # None for UNKNOWN-with-no-evidence cases


RETRIEVAL_GOLDEN_CASES: list[RetrievalCase] = [
    # synthetic dataset
    RetrievalCase("billing postal code retention", frozenset({"payment-service.md"})),
    RetrievalCase("bcrypt password hashing", frozenset({"user-auth-service.md"})),
    RetrievalCase(
        "schema validation for incoming events", frozenset({"data-pipeline.md"})
    ),
    # real public corpus
    RetrievalCase(
        "kubernetes pod security baseline policy hostpath volumes",
        frozenset({"kubernetes-pod-security-standards.md"}),
    ),
    RetrievalCase(
        "nist cybersecurity framework five functions identify protect detect respond recover",
        frozenset({"nist-csf-functions.md"}),
    ),
    RetrievalCase(
        "owasp broken access control least privilege",
        frozenset({"owasp-a01-broken-access-control.md"}),
    ),
    RetrievalCase(
        "owasp cryptographic failures hard-coded keys",
        frozenset({"owasp-a02-cryptographic-failures.md"}),
    ),
    RetrievalCase(
        "kubernetes restricted policy seccomp",
        frozenset({"kubernetes-pod-security-standards.md"}),
    ),
]

REVIEW_GOLDEN_CASES: list[ReviewCase] = [
    ReviewCase(
        question="does payment-api have rate limiting on the checkout endpoint?",
        expected_verdict="FAIL",
        expected_citation_filename="payment-service.md",
    ),
    ReviewCase(
        question="are user passwords hashed with bcrypt?",
        expected_verdict="PASS",
        expected_citation_filename="user-auth-service.md",
    ),
    ReviewCase(
        question="what does event-collector send data to downstream?",
        expected_verdict="FAIL",
        expected_citation_filename="data-pipeline.md",
    ),
    ReviewCase(
        question="does the kubernetes baseline policy allow hostpath volumes?",
        expected_verdict="FAIL",
        expected_citation_filename="kubernetes-pod-security-standards.md",
    ),
    ReviewCase(
        question="are hard-coded cryptographic keys a documented cryptographic failure?",
        expected_verdict="FAIL",
        expected_citation_filename="owasp-a02-cryptographic-failures.md",
    ),
]

# Questions with no answer anywhere in either corpus — used to measure
# the false-confidence rate: the system must abstain (UNKNOWN), not
# guess PASS/FAIL on a topic it has no evidence for.
UNANSWERABLE_QUESTIONS: list[str] = [
    "does the system support biometric login?",
    "does the system use a service mesh for kubernetes traffic?",
    "is there a signed data processing agreement with sub-processors?",
    "does the system support quantum-resistant encryption?",
]
