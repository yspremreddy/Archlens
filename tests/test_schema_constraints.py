import pytest
from sqlalchemy.exc import IntegrityError

from app.models import Chunk, ComplianceControl, Document, Finding, FindingEvidence


def _make_document(**overrides) -> Document:
    defaults = dict(
        source_type="upload",
        original_filename="x.md",
        file_size_bytes=1,
        storage_path="/tmp/x",
        content_hash="sha256:deadbeef",
    )
    defaults.update(overrides)
    return Document(**defaults)


def test_document_status_check_constraint_rejects_invalid_value(db_session):
    doc = _make_document(status="not-a-real-status")
    db_session.add(doc)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_document_source_type_check_constraint_rejects_invalid_value(db_session):
    doc = _make_document(source_type="connected_repo")
    db_session.add(doc)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_chunk_unique_document_id_and_chunk_index(db_session):
    doc = _make_document()
    db_session.add(doc)
    db_session.flush()

    db_session.add(
        Chunk(document_id=doc.id, chunk_index=0, text="first", content_hash="sha256:aaa")
    )
    db_session.flush()
    db_session.add(
        Chunk(document_id=doc.id, chunk_index=0, text="duplicate index", content_hash="sha256:bbb")
    )
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_chunk_rejects_empty_text(db_session):
    doc = _make_document()
    db_session.add(doc)
    db_session.flush()

    db_session.add(Chunk(document_id=doc.id, chunk_index=0, text="", content_hash="sha256:aaa"))
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_document_cascade_deletes_its_chunks(db_session):
    doc = _make_document()
    db_session.add(doc)
    db_session.flush()
    db_session.add(Chunk(document_id=doc.id, chunk_index=0, text="a", content_hash="sha256:aaa"))
    db_session.commit()

    db_session.delete(doc)
    db_session.commit()

    remaining = db_session.query(Chunk).filter_by(document_id=doc.id).count()
    assert remaining == 0


def test_cannot_delete_chunk_cited_as_finding_evidence(db_session):
    doc = _make_document()
    db_session.add(doc)
    db_session.flush()
    chunk = Chunk(document_id=doc.id, chunk_index=0, text="evidence text", content_hash="sha256:aaa")
    db_session.add(chunk)
    db_session.flush()

    finding = Finding(title="t", statement="s")
    db_session.add(finding)
    db_session.flush()

    db_session.add(FindingEvidence(finding_id=finding.id, chunk_id=chunk.id))
    db_session.commit()

    db_session.delete(chunk)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_compliance_control_unique_framework_and_code(db_session):
    db_session.add(
        ComplianceControl(framework="archlens-custom", control_code="AC-1", title="First")
    )
    db_session.flush()
    db_session.add(
        ComplianceControl(framework="archlens-custom", control_code="AC-1", title="Duplicate")
    )
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()
