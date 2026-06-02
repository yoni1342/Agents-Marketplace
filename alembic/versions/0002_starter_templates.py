"""add is_starter flag + seed the starter team

Revision ID: 0002_starter
Revises: 0001_initial
Create Date: 2026-06-02

Makes the marketplace the single source of truth for ALL agent definitions,
not just hireable specialists. Adds ``agent_templates.is_starter`` and seeds
the eight starter-team specs (CEO + the seven canonical roles) lifted from
Bench's old ``default_agents.py``.

Starter templates are excluded from the hireable browse list and served only
via ``GET /v1/templates/starter``, which Bench calls when provisioning a new
org. Existing rows default to ``is_starter = false`` (the six specialists).
"""
from typing import Sequence, Union
from uuid import uuid4

from alembic import op
import sqlalchemy as sa

from app.builtin_templates import STARTER_TEMPLATES

revision: str = "0002_starter"
down_revision: Union[str, Sequence[str], None] = "0001_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "agent_templates",
        sa.Column(
            "is_starter",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.create_index(
        "ix_agent_templates_is_starter", "agent_templates", ["is_starter"]
    )

    bind = op.get_bind()
    for t in STARTER_TEMPLATES:
        bind.execute(
            sa.text(
                """
                INSERT INTO agent_templates (
                    id, slug, name, tagline, role, system_prompt,
                    default_model, default_budget_cents, category,
                    sort_order, is_built_in, is_starter, created_at
                )
                VALUES (
                    :id, :slug, :name, :tagline, :role, :sp,
                    :model, :budget, :category, :sort_order, true, true, NOW()
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
    bind = op.get_bind()
    slugs = tuple(t["slug"] for t in STARTER_TEMPLATES)
    bind.execute(
        sa.text("DELETE FROM agent_templates WHERE slug IN :slugs").bindparams(
            sa.bindparam("slugs", expanding=True)
        ),
        {"slugs": list(slugs)},
    )
    op.drop_index("ix_agent_templates_is_starter", table_name="agent_templates")
    op.drop_column("agent_templates", "is_starter")
