"""initial: agent_templates catalog + seed built-ins

Revision ID: 0001_initial
Revises:
Create Date: 2026-06-02

Creates the marketplace's own ``agent_templates`` table and seeds the six
built-in specialists (Bookkeeper, Recruiter, Newsletter Writer, PR Officer,
Project Manager, Customer Researcher). The catalog data lives in
``app.builtin_templates`` so it has a single source of truth.

This is the marketplace half of Bench's original
``e2b9d4f7c805_add_agent_templates`` migration — the ``agents.template_slug``
column stays in Bench.
"""
from typing import Sequence, Union
from uuid import uuid4

from alembic import op
import sqlalchemy as sa

from app.builtin_templates import BUILTIN_TEMPLATES

revision: str = "0001_initial"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "agent_templates",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column("slug", sa.String(), nullable=False, unique=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("tagline", sa.String(), nullable=False),
        sa.Column("role", sa.String(), nullable=False),
        sa.Column("system_prompt", sa.Text(), nullable=False),
        sa.Column("default_model", sa.String(), nullable=False),
        sa.Column("default_budget_cents", sa.Integer(), nullable=False),
        sa.Column("category", sa.String(), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "is_built_in", sa.Boolean(), nullable=False, server_default=sa.true()
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "ix_agent_templates_slug", "agent_templates", ["slug"], unique=True
    )
    op.create_index(
        "ix_agent_templates_is_built_in", "agent_templates", ["is_built_in"]
    )

    bind = op.get_bind()
    for t in BUILTIN_TEMPLATES:
        bind.execute(
            sa.text(
                """
                INSERT INTO agent_templates (
                    id, slug, name, tagline, role, system_prompt,
                    default_model, default_budget_cents, category,
                    sort_order, is_built_in, created_at
                )
                VALUES (
                    :id, :slug, :name, :tagline, :role, :sp,
                    :model, :budget, :category, :sort_order, true, NOW()
                )
                """
            ),
            {
                "id": uuid4(),
                "slug": t["slug"],
                "name": t["name"],
                "tagline": t["tagline"],
                "role": t["role"],
                "sp": t["system_prompt"],
                "model": t["default_model"],
                "budget": t["default_budget_cents"],
                "category": t["category"],
                "sort_order": t["sort_order"],
            },
        )


def downgrade() -> None:
    op.drop_index("ix_agent_templates_is_built_in", table_name="agent_templates")
    op.drop_index("ix_agent_templates_slug", table_name="agent_templates")
    op.drop_table("agent_templates")
