"""phase 5 rule based extraction method

Revision ID: 540fcff68f20
Revises: e3034b9b35ac
Create Date: 2026-09-10 23:48:24.511643

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '540fcff68f20'
down_revision: Union[str, Sequence[str], None] = 'e3034b9b35ac'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Widen components.extraction_method to allow 'rule_based' (Phase 5
    graph extraction — see app/graph/extraction.py). Autogenerate does not
    detect CHECK constraint text changes, so this is hand-written."""
    op.drop_constraint("ck_components_extraction_method", "components", type_="check")
    op.create_check_constraint(
        "ck_components_extraction_method",
        "components",
        "extraction_method IN ('manual','llm_extracted','rule_based')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_components_extraction_method", "components", type_="check")
    op.create_check_constraint(
        "ck_components_extraction_method",
        "components",
        "extraction_method IN ('manual','llm_extracted')",
    )
