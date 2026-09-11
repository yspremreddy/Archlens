"""One-off script used to assemble assets/demo/sample_output.json from the
real /review API responses captured against the live backend (see
assets/demo/sample_output.md for how it was run). Not part of the
application; kept for reproducibility, not imported by app/ or tests/.
"""

import json
from pathlib import Path

DEMO_DIR = Path(__file__).parent
DOCUMENT_ID = "067130fd-e130-4955-9634-af69d1202396"
DOCUMENT_FILENAME = "payment-service-architecture.md"
DOCUMENT_CONTENT_HASH = "sha256:902941c022ab6c6ccdae9eb6099328905907d9d723665587bc6077e2a48a491a"

RAW_DIR = DEMO_DIR / "_raw"
QUESTIONS = [
    ("q1", RAW_DIR / "archlens_q1.json", "Public database accessibility"),
    ("q2", RAW_DIR / "archlens_q2.json", "Payment data encryption"),
    ("q3", RAW_DIR / "archlens_q3.json", "Payment record retention"),
    ("q4", RAW_DIR / "archlens_q4.json", "PostgreSQL failover"),
    ("q5", RAW_DIR / "archlens_q5.json", "Backup / disaster recovery documentation"),
]


def main() -> None:
    reviews = []
    for qid, path, label in QUESTIONS:
        body = json.loads(Path(path).read_text())
        reviews.append(
            {
                "id": qid,
                "label": label,
                "question": body["question"],
                "verdict": body["verdict"],
                "severity": body["severity"],
                "confidence": body["confidence"],
                "recommendation": body["recommendation"],
                "agent_steps": body["agent_steps"],
                "citations": [
                    {
                        "document_filename": c["document_filename"],
                        "document_content_hash": c["document_content_hash"],
                        "chunk_index": c["chunk_index"],
                        "chunk_content_hash": c["chunk_content_hash"],
                        "text": c["text"],
                    }
                    for c in body["citations"]
                ],
                "finding_id": body["finding_id"],
            }
        )

    output = {
        "generated_by": "ArchLens /review API (real, live pipeline run — no fabricated values)",
        "input_document": {
            "filename": DOCUMENT_FILENAME,
            "document_id": DOCUMENT_ID,
            "content_hash": DOCUMENT_CONTENT_HASH,
            "source_path": "assets/demo/payment-service-architecture.md",
        },
        "reviews": reviews,
    }

    (DEMO_DIR / "sample_output.json").write_text(json.dumps(output, indent=2) + "\n")
    print("wrote", DEMO_DIR / "sample_output.json")


if __name__ == "__main__":
    main()
