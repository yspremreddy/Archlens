"""Rule-based (regex) extraction of components and relationships from
architecture documents.

Deliberately NOT an LLM extractor — Postgres `components.extraction_method`
records this as `'rule_based'` (added to that column's CHECK constraint by
this phase's migration; see docs/SCHEMA.md §3). This is a small, fixed set
of textual patterns tuned against the actual structure of
data/samples/*.md ("## Components" bullet lists, "## Ownership" sections)
— honest about being narrow rather than a general NLP/LLM extractor, per
CLAUDE.md rule 3 (don't fabricate results): every extracted fact is
traceable to a specific regex match against specific source text, and a
document whose structure doesn't match simply yields fewer (or zero)
components/relationships rather than guessed ones.
"""

import re
from dataclasses import dataclass

from app.graph.schema import REL_DEPENDS_ON, REL_SENDS_DATA_TO

COMPONENT_TYPES = ("service", "datastore", "queue", "external_system", "other")

_EXTERNAL_KEYWORDS = ("external", "third-party", "third party")
_QUEUE_KEYWORDS = ("queue", "kafka", "topic", "message bus")
_DATASTORE_KEYWORDS = ("database", "postgresql", "warehouse", "cache", "redis")
_SERVICE_KEYWORDS = ("api", "endpoint", "job", "worker", "service")

_BULLET_RE = re.compile(r"^-\s+\*\*([\w-]+)\*\*:?\s*(.*)$")
_OWNERSHIP_RE = re.compile(r"Owned by the ([A-Za-z][A-Za-z \-]*?) team\b")
_CALLS_IT_RE = re.compile(r"\bcalls\s+it\b", re.IGNORECASE)


@dataclass(frozen=True)
class ExtractedComponent:
    name: str
    type: str
    description: str


@dataclass(frozen=True)
class ExtractedRelationship:
    source_name: str
    target_name: str
    kind: str  # REL_SENDS_DATA_TO or REL_DEPENDS_ON


@dataclass(frozen=True)
class ExtractionResult:
    components: list[ExtractedComponent]
    relationships: list[ExtractedRelationship]
    owner_team: str | None
    primary_component_name: str | None  # first component listed; OWNED_BY subject


def _self_describing_clause(description: str, other_names: list[str]) -> str:
    """The portion of a bullet's description that's actually about *this*
    component, for type-keyword matching — not the whole description,
    which often goes on to mention *other* components (e.g. payment-db's
    description mentions a "third-party PCI-compliant vault" further in,
    which would otherwise wrongly classify payment-db itself as
    external). Truncates at the first mention of another known
    component's name, or the first sentence, whichever comes first.
    """
    cut = len(description)
    if other_names:
        alt = _name_alternation(other_names)
        m = re.search(rf"\b({alt})\b", description)
        if m:
            cut = min(cut, m.start())
    period = description.find(".")
    if period != -1:
        cut = min(cut, period + 1)
    return description[:cut]


def _infer_type(description: str, other_names: list[str]) -> str:
    lower = _self_describing_clause(description, other_names).lower()
    if any(k in lower for k in _EXTERNAL_KEYWORDS):
        return "external_system"
    if any(k in lower for k in _QUEUE_KEYWORDS):
        return "queue"
    if any(k in lower for k in _DATASTORE_KEYWORDS):
        return "datastore"
    if any(k in lower for k in _SERVICE_KEYWORDS):
        return "service"
    return "other"


def _section(text: str, heading: str) -> str | None:
    """Text of a '## <heading>' section, up to the next '## ' heading."""
    pattern = re.compile(
        rf"^##\s+{re.escape(heading)}\s*$\n(.*?)(?=^##\s|\Z)", re.MULTILINE | re.DOTALL
    )
    m = pattern.search(text)
    return m.group(1) if m else None


def _bullets(section_text: str) -> list[str]:
    """Joins each bullet's wrapped continuation lines (indented, no blank
    line before the next '- ') into one logical line per bullet."""
    bullets: list[str] = []
    current: list[str] = []
    for line in section_text.splitlines():
        if line.startswith("- "):
            if current:
                bullets.append(" ".join(current))
            current = [line]
        elif line.strip() and current:
            current.append(line.strip())
    if current:
        bullets.append(" ".join(current))
    return bullets


def _extract_components(text: str) -> list[ExtractedComponent]:
    section = _section(text, "Components")
    if not section:
        return []

    raw: list[tuple[str, str]] = []
    for line in _bullets(section):
        m = _BULLET_RE.match(line)
        if m:
            raw.append((m.group(1), m.group(2).strip()))

    all_names = [name for name, _ in raw]
    components = []
    for name, desc in raw:
        other_names = [n for n in all_names if n != name]
        components.append(
            ExtractedComponent(name=name, type=_infer_type(desc, other_names), description=desc)
        )
    return components


def _name_alternation(names: list[str]) -> str:
    return "|".join(re.escape(n) for n in sorted(names, key=len, reverse=True))


def _first_name(text: str, name_re: re.Pattern, *, exclude: str) -> str | None:
    for m in name_re.finditer(text):
        if m.group(1) != exclude:
            return m.group(1)
    return None


def _extract_relationships(
    full_text: str, components: list[ExtractedComponent]
) -> list[ExtractedRelationship]:
    if len(components) < 2:
        return []
    names = [c.name for c in components]
    alt = _name_alternation(names)
    name_re = re.compile(rf"\b({alt})\b")
    rels: list[ExtractedRelationship] = []

    # Rule 1: within a bullet's own description, "from A ... to/into B"
    # names this bullet's component as the mediator: A -> this -> B.
    from_to_re = re.compile(rf"\bfrom\s+({alt})\b.*?\b(?:to|into)\s+(?:the\s+)?", re.IGNORECASE)
    for comp in components:
        m = from_to_re.search(comp.description)
        if not m:
            continue
        a = m.group(1)
        b = _first_name(comp.description[m.end() :], name_re, exclude=comp.name)
        if a != comp.name:
            rels.append(ExtractedRelationship(a, comp.name, REL_SENDS_DATA_TO))
        if b:
            rels.append(ExtractedRelationship(comp.name, b, REL_SENDS_DATA_TO))

    # Rule 2: "<component> calls it" within another component's bullet ->
    # the caller DEPENDS_ON this bullet's component ("it").
    for comp in components:
        if not _CALLS_IT_RE.search(comp.description):
            continue
        caller = _first_name(comp.description, name_re, exclude=comp.name)
        if caller:
            rels.append(ExtractedRelationship(caller, comp.name, REL_DEPENDS_ON))

    # Rule 3: "<component> accepts events ... reach A [and B]" anywhere in
    # the document — the accepting component sends to each reached one.
    accepts_reach_re = re.compile(
        rf"\b({alt})\s+accepts\s+events?\b[\s\S]{{0,200}}?\breach\s+({alt})"
        rf"(?:\s+and\s+({alt}))?",
        re.IGNORECASE,
    )
    for m in accepts_reach_re.finditer(full_text):
        source = m.group(1)
        for target in (m.group(2), m.group(3)):
            if target and target != source:
                rels.append(ExtractedRelationship(source, target, REL_SENDS_DATA_TO))

    seen: set[tuple[str, str, str]] = set()
    unique: list[ExtractedRelationship] = []
    for r in rels:
        key = (r.source_name, r.target_name, r.kind)
        if key not in seen:
            seen.add(key)
            unique.append(r)
    return unique


def extract(document_text: str) -> ExtractionResult:
    components = _extract_components(document_text)
    relationships = _extract_relationships(document_text, components)

    owner_match = _OWNERSHIP_RE.search(document_text)
    owner_team = owner_match.group(1).strip() if owner_match else None
    primary = components[0].name if components else None

    return ExtractionResult(
        components=components,
        relationships=relationships,
        owner_team=owner_team,
        primary_component_name=primary,
    )
