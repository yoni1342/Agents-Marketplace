"""the starter crew, exactly as the Bench Agent Instructions define it

Revision ID: 0008_crew_doc
Revises: 0007_crew_cards
Create Date: 2026-09-08

Eight agents: CEO, Strategist, Marketer, Closer, Operator, Money, Grant Writer,
Content Producer. Names lose the "The"/"Agent" decoration to match the document
and the website, every prompt becomes CORE + its specialist block, and Money and
Content Producer join.

Concierge and Analyst leave the STARTER set but stay in the catalog as hireable
templates — an org that wants a support or data specialist can still add one,
and no existing agent anywhere is deleted.

Reads everything from app.builtin_templates.STARTER_TEMPLATES so the constant
stays the single source of truth. Idempotent: it upserts by slug.
"""
from typing import Sequence, Union
from uuid import uuid4

import sqlalchemy as sa
from alembic import op

from app.builtin_templates import STARTER_TEMPLATES

revision: str = "0008_crew_doc"
down_revision: Union[str, Sequence[str], None] = "0007_crew_cards"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_RETIRED = ("concierge", "analyst")


def upgrade() -> None:
    bind = op.get_bind()
    for t in STARTER_TEMPLATES:
        row = dict(t)
        row["id"] = str(uuid4())
        bind.execute(
            sa.text(
                """
                INSERT INTO agent_templates (
                    id, slug, name, tagline, role, system_prompt,
                    default_model, default_budget_cents, category,
                    sort_order, is_built_in, is_starter, created_at
                ) VALUES (
                    :id, :slug, :name, :tagline, :role, :system_prompt,
                    :default_model, :default_budget_cents, :category,
                    :sort_order, true, true, now()
                )
                ON CONFLICT (slug) DO UPDATE SET
                    name = EXCLUDED.name,
                    tagline = EXCLUDED.tagline,
                    role = EXCLUDED.role,
                    system_prompt = EXCLUDED.system_prompt,
                    default_model = EXCLUDED.default_model,
                    default_budget_cents = EXCLUDED.default_budget_cents,
                    category = EXCLUDED.category,
                    sort_order = EXCLUDED.sort_order,
                    is_starter = true
                """
            ),
            row,
        )
    # Out of the starter seed, still hireable.
    bind.execute(
        sa.text(
            "UPDATE agent_templates SET is_starter = false, category = 'Specialists' "
            "WHERE slug = ANY(:slugs)"
        ),
        {"slugs": list(_RETIRED)},
    )


def downgrade() -> None:
    bind = op.get_bind()
    bind.execute(
        sa.text(
            "UPDATE agent_templates SET is_starter = true, category = 'Starter Team' "
            "WHERE slug = ANY(:slugs)"
        ),
        {"slugs": list(_RETIRED)},
    )
    bind.execute(
        sa.text(
            "UPDATE agent_templates SET is_starter = false WHERE slug = ANY(:slugs)"
        ),
        {"slugs": ["money", "content-producer"]},
    )
