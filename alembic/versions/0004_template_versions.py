"""rich-spec versioning: agent_template_versions + identity columns

Revision ID: 0004_versions
Revises: 0003_seo
Create Date: 2026-06-03

Build plan §4 / D-0006 (agent-platform docs). Adds versioning ALONGSIDE the
existing flat ``agent_templates`` row so nothing breaks: the current read
endpoints keep serving the flat columns (the v0 definition) while the new
``agent_template_versions`` table holds the rich, immutable published specs.

Non-breaking:
- two new ``agent_templates`` columns, NOT NULL with a '' server_default so
  existing rows backfill instantly.
- one new table.
No column drops, no data migration of existing templates.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0004_versions"
down_revision: Union[str, Sequence[str], None] = "0003_seo"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- identity columns on the existing table -----------------------------
    op.add_column(
        "agent_templates",
        sa.Column("maintainer", sa.String(), nullable=False, server_default=""),
    )
    op.add_column(
        "agent_templates",
        sa.Column("latest_version", sa.String(), nullable=False, server_default=""),
    )

    # --- the rich versioned-spec table --------------------------------------
    op.create_table(
        "agent_template_versions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("slug", sa.String(), nullable=False),
        sa.Column("version", sa.String(), nullable=False),
        sa.Column("system_prompt", sa.String(), nullable=False),
        sa.Column("model_routing", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("tools", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("config_schema", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("quality", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("budget_cents", sa.Integer(), nullable=False, server_default="2500"),
        sa.Column("eval_passed", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("eval_report", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column(
            "published_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.ForeignKeyConstraint(
            ["slug"], ["agent_templates.slug"], ondelete="CASCADE"
        ),
        sa.UniqueConstraint("slug", "version", name="uq_template_version"),
    )
    op.create_index(
        "ix_agent_template_versions_slug", "agent_template_versions", ["slug"]
    )


def downgrade() -> None:
    op.drop_index("ix_agent_template_versions_slug", table_name="agent_template_versions")
    op.drop_table("agent_template_versions")
    op.drop_column("agent_templates", "latest_version")
    op.drop_column("agent_templates", "maintainer")
