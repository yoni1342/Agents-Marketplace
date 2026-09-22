"""admin-managed templates: edits made in Bench's admin panel survive the git sync

Revision ID: 0011_admin_managed
Revises: 0010_marketer_approval
Create Date: 2026-09-22

The boot-time sync upserts every git package over its DB row, so an operator's
API edit was reverted on the next deploy. ``admin_edited_at`` marks a template
the admin now owns (the sync skips it); ``retired_template_slugs`` keeps a
deleted template deleted even though its package is still in agents/.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0011_admin_managed"
down_revision: Union[str, Sequence[str], None] = "0010_marketer_approval"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("agent_templates", sa.Column("admin_edited_at", sa.DateTime(timezone=True), nullable=True))
    op.create_table(
        "retired_template_slugs",
        sa.Column("slug", sa.String(), primary_key=True),
        sa.Column("retired_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("retired_template_slugs")
    op.drop_column("agent_templates", "admin_edited_at")
