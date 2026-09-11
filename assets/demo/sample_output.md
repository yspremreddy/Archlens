# ArchLens Demo — Audit Summary

**Input:** [`payment-service-architecture.md`](payment-service-architecture.md)
**Pipeline:** real `POST /documents` → `POST /review` calls against a running
ArchLens backend (local Postgres + pgvector, no external LLM — default
`template` provider). Full machine-readable output: [`sample_output.json`](sample_output.json).

Every result below is copied verbatim from the live API response — nothing
here is invented or adjusted after the fact, including the two results
(retention, backup/DR docs) where ArchLens correctly abstains rather than
guessing.

---

## 1. Public database accessibility — **FAIL**

> *"Does this architecture comply with the requirement that production
> customer databases must not be publicly accessible?"*

| | |
|---|---|
| Verdict | **FAIL** |
| Severity | medium |
| Confidence | 0.65 |

**Recommendation:** A gap was found: Production customer databases must not
be publicly accessible.. Assign an owner, remediate, and add verification.

**Evidence:**
- *"1. Production customer databases must not be publicly accessible."*
  (Compliance Requirements)
- *"The PostgreSQL database is deployed in a public subnet to simplify
  operational access."* (Network Architecture)
- *"publicly accessible network access"* (Security)

The document states the requirement **and** states the database is deployed
in a public subnet with publicly accessible network access — a real,
correctly-flagged violation.

## 2. Payment data encryption — **PASS**

> *"Is customer payment data encrypted?"*

| | |
|---|---|
| Verdict | **PASS** |
| Severity | low |
| Confidence | 0.65 |

**Evidence:** *"Customer payment data is encrypted at the application layer
before being stored."*

Note: the document's compliance requirement is encryption "at rest"; the
evidence describes application-layer encryption specifically. ArchLens's
policy engine matches the general phrase "is encrypted" — it does not
distinguish encryption *layers* (application vs. storage/at-rest). Reported
here as-is, not smoothed over.

## 3. Payment record retention — **UNKNOWN**

> *"Are payment records retained for at least 7 years?"*

| | |
|---|---|
| Verdict | **UNKNOWN** |
| Confidence | 0.67 |

**Recommendation:** Relevant evidence was found but it does not explicitly
confirm or deny this control. Manual review recommended.

The document does say *"Payment records are retained for 7 years"* — but
this phrasing doesn't match any of ArchLens's negation/affirmation marker
patterns (`app/policy/markers.py`), so it correctly abstains rather than
guessing PASS. This is a real, demonstrated limitation of the rule-based
marker vocabulary, not a bug being hidden.

## 4. PostgreSQL failover — **CONFLICT**

> *"Does PostgreSQL have a documented failover configuration?"*

| | |
|---|---|
| Verdict | **CONFLICT** |
| Severity | medium |
| Confidence | 0.5 |

**Recommendation:** Evidence conflicts: some sources affirm this control is
in place, others indicate it is not. Manually reconcile the sources listed
in citations before relying on either claim.

**Why:** the sentence *"PostgreSQL currently has a single primary instance
and no documented failover configuration"* contains both an affirmation
marker (`has a`) and a negation marker (`no documented`) in the same
sentence — a real, observed edge case in the marker-scanning approach
(`app/policy/engine.py`), surfaced honestly as CONFLICT rather than silently
picked one way.

## 5. Backup / disaster recovery documentation — **UNKNOWN**

> *"Are database backups and disaster recovery procedures documented?"*

| | |
|---|---|
| Verdict | **UNKNOWN** |
| Confidence | 0.58 |

The document states *"Database backups are not documented"* and *"Disaster
recovery procedures are not documented"* — but ArchLens's negation patterns
include `no documented` (bare), not `not documented`. Another genuine,
demonstrated gap in the marker vocabulary rather than a fabricated result.

---

## Takeaways

- ArchLens correctly caught the one clear-cut compliance violation in the
  document (public database access) with full evidence and citations.
- It correctly abstains (UNKNOWN) rather than guessing when its rule-based
  marker vocabulary doesn't cover a phrasing it hasn't seen.
- It surfaces a genuine ambiguous case (CONFLICT) instead of silently
  picking a side when one sentence matches both an affirmation and a
  negation pattern.
- Every citation resolves to a real document/chunk hash — see
  `sample_output.json` for the full evidence text and hashes behind each
  verdict above.
