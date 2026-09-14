"""retire the four marketplace agents the default team already covers

Revision ID: 0009_retire_dupes
Revises: 0008_crew_doc
Create Date: 2026-09-14

Newsletter Writer and LinkedIn Thought Leadership Writer do the Content
Producer's job, Project Manager does the Operator's, and Bid Writer uses the
same quote/invoice tool the Closer and Money already have. None of the four
had a single hire in prod on 2026-09-14.

Removing ``agents/<slug>/`` alone is not enough: the sync only upserts, so the
cards would stay in the catalog. This deletes the rows; their versions go with
them through the ON DELETE CASCADE foreign key. On a fresh database 0001 still
seeds two of these from ``builtin_templates`` — this runs after it and removes
them again.

Agents already hired in Bench are ordinary agents holding their own prompt
copy, so they keep working; they just stop resolving a marketplace version.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0009_retire_dupes"
down_revision: Union[str, Sequence[str], None] = "0008_crew_doc"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_SLUGS = [
    "newsletter-writer",
    "linkedin-thought-leadership-writer",
    "project-manager",
    "bid-and-invoice-writer",
]


def upgrade() -> None:
    op.get_bind().execute(
        sa.text("DELETE FROM agent_templates WHERE slug IN :slugs").bindparams(
            sa.bindparam("slugs", expanding=True)
        ),
        {"slugs": _SLUGS},
    )


def downgrade() -> None:
    # The specs left agents/ in the same commit. Bringing a card back means
    # restoring its folder from git history and adding it with a new migration,
    # the way 0006 added the Social Media & Ads Manager.
    pass
