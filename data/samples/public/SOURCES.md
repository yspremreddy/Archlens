# Public corpus — sources, licenses, retrieval record

A small, real-world public corpus for evaluation (Phase 8), alongside
the existing fully-synthetic dataset (`data/samples/*.md`,
`data/samples/diagrams/`). Every file below is a genuine excerpt from a
publicly published, clearly-licensed source — fetched on the date
recorded, with the exact source URL and license kept alongside the
content (CLAUDE.md rule 3: no fabricated content; rule 5/8 equivalent
for provenance — never present derived/paraphrased text as if it were
the primary source without saying so).

Kept deliberately small (4 short excerpt files, ~1-2KB each) — enough
for real retrieval/evaluation diversity, not a large dataset.

| File | Source | URL | License | Retrieved |
|------|--------|-----|---------|-----------|
| `kubernetes-pod-security-standards.md` | Kubernetes documentation | https://kubernetes.io/docs/concepts/security/pod-security-standards/ | CC BY 4.0 (Kubernetes documentation license — https://github.com/kubernetes/website#license) | 2026-09-11 |
| `nist-csf-functions.md` | NIST Cybersecurity Framework (csf 1.1 "Five Functions" page) | https://www.nist.gov/cyberframework/online-learning/five-functions | U.S. Government work — public domain in the United States (17 U.S.C. §105); see https://www.nist.gov/copyrights-disclaimers | 2026-09-11 |
| `owasp-a01-broken-access-control.md` | OWASP Top 10:2021 | https://owasp.org/Top10/2021/A01_2021-Broken_Access_Control/ | CC BY 3.0 Unported ("© Copyright 2021-2025 - OWASP Top 10 Team") | 2026-09-11 |
| `owasp-a02-cryptographic-failures.md` | OWASP Top 10:2021 | https://owasp.org/Top10/2021/A02_2021-Cryptographic_Failures/ | CC BY 3.0 Unported ("© Copyright 2021-2025 - OWASP Top 10 Team") | 2026-09-11 |

Each file below also carries its own attribution header (source, URL,
license, retrieval date) so provenance survives even if this ledger and
the file are separated. Content is a mix of direct quotation (marked)
and close paraphrase of the fetched page content — not a full mirror of
either site, kept short deliberately (CLAUDE.md rule 8 / task instruction
"do not use large unnecessary datasets").

**Why these four, out of the suggested list (AWS, NIST, Kubernetes,
Terraform, OpenAPI/security docs):** NIST (public domain) and Kubernetes/
OWASP (both explicit CC-BY reuse licenses) have the clearest, most
unambiguous public-reuse terms of the suggested sources. AWS
documentation prose is copyrighted by Amazon without an open-reuse
license for verbatim excerpts, and HashiCorp's Terraform documentation
prose is similarly all-rights-reserved (only the Terraform *code* is
MPL-2.0) — both were excluded on that basis rather than included and
risked. OpenAPI's specification text (Apache-2.0) was considered but
skipped in favor of OWASP, which is more directly relevant to the
"security documentation" framing and to this project's compliance/risk
review use case.
