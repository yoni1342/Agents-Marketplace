"""add The SEO Specialist to the hireable catalog

Revision ID: 0003_seo
Revises: 0002_starter
Create Date: 2026-06-02

Seeds the seo-specialist template (defined in app.builtin_templates). Uses
ON CONFLICT DO NOTHING so it's a no-op on a fresh DB where migration 0001
already inserted the whole BUILTIN_TEMPLATES list (which now includes it),
while still inserting it on the existing prod DB where 0001 predates it.
"""
from typing import Sequence, Union
from uuid import uuid4

from alembic import op
import sqlalchemy as sa

from app.builtin_templates import BUILTIN_TEMPLATES

revision: str = "0003_seo"
down_revision: Union[str, Sequence[str], None] = "0002_starter"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_SLUG = "seo-specialist"


def upgrade() -> None:
    t = next((x for x in BUILTIN_TEMPLATES if x["slug"] == _SLUG), None)
    if t is None:
        raise RuntimeError(f"{_SLUG} missing from BUILTIN_TEMPLATES")
    op.get_bind().execute(
        sa.text(
            """
            INSERT INTO agent_templates (
                id, slug, name, tagline, role, system_prompt,
                default_model, default_budget_cents, category,
                sort_order, is_built_in, is_starter, created_at
            )
            VALUES (
                :id, :slug, :name, :tagline, :role, :sp,
                :model, :budget, :category, :sort_order, true, false, NOW()
            )
            ON CONFLICT (slug) DO NOTHING
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
    op.get_bind().execute(
        sa.text("DELETE FROM agent_templates WHERE slug = :slug"),
        {"slug": _SLUG},
    )
