"""add the Social Media & Ads Manager to the catalog

Revision ID: 0006_social_ads
Revises: 0005_publishing
Create Date: 2026-07-22

Same seam as 0005: ``python -m app.cli sync agents/`` is a LOCAL command and the
deploy never runs it, so a spec-only change ships the files to the image and
stops there — present at /app/agents, read by nothing. Migrations are what runs
against the catalog on every deploy, so that is where a new card has to be
introduced.

Rows are built by READING the git spec rather than restating it, so the prompt
in the catalog cannot drift from the prompt in the repo. Only this one slug is
touched, and both inserts are ON CONFLICT DO NOTHING, so re-running is a no-op
and no existing agent's prompt is rewritten.
"""
from pathlib import Path
from typing import Sequence, Union
from uuid import uuid4

import sqlalchemy as sa
from alembic import op

revision: str = "0006_social_ads"
down_revision: Union[str, Sequence[str], None] = "0005_publishing"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_SLUG = "social-media-and-ads-manager"

# agents/ sits next to app/ in the image; this file is alembic/versions/x.py.
_AGENTS_ROOT = Path(__file__).resolve().parents[2] / "agents"


def _package():
    from app.spec_repo import discover_packages

    for pkg in discover_packages(_AGENTS_ROOT):
        if pkg.manifest.slug == _SLUG:
            latest = max(
                (vf.spec for vf in pkg.versions),
                key=lambda s: tuple(int(p) for p in s.version.split(".")),
            )
            return pkg.manifest, latest
    raise RuntimeError(f"spec for {_SLUG} missing from agents/")


def upgrade() -> None:
    import json

    manifest, spec = _package()
    bind = op.get_bind()
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
                :model, :budget, :category, :sort_order,
                :built_in, :starter, NOW()
            )
            ON CONFLICT (slug) DO NOTHING
            """
        ),
        {
            "id": uuid4(),
            "slug": spec.slug,
            "name": spec.name,
            "tagline": spec.tagline,
            "role": manifest.role,
            "sp": spec.system_prompt,
            "model": spec.model.default,
            "budget": spec.budget.default_monthly_cents,
            "category": spec.category,
            "sort_order": manifest.sort_order,
            "built_in": manifest.is_built_in,
            # Hire-only: this agent posts in public as the company, so it
            # belongs on a roster somebody chose, not on every new one.
            "starter": manifest.is_starter,
        },
    )
    # The version row carries config_schema — without it the card browses but
    # can't be activated with its approval channel, which is the whole agent.
    bind.execute(
        sa.text(
            """
            INSERT INTO agent_template_versions (
                id, slug, version, system_prompt, model_routing, tools,
                config_schema, quality, budget_cents, eval_passed,
                eval_report, published_at
            )
            VALUES (
                :id, :slug, :version, :sp,
                CAST(:routing AS jsonb), CAST(:tools AS jsonb),
                CAST(:cfg AS jsonb), CAST(:quality AS jsonb),
                :budget, false, CAST(:report AS jsonb), NOW()
            )
            ON CONFLICT (slug, version) DO NOTHING
            """
        ),
        {
            "id": uuid4(),
            "slug": spec.slug,
            "version": spec.version,
            "sp": spec.system_prompt,
            "routing": json.dumps(spec.model.model_dump(exclude_none=True)),
            "tools": json.dumps([t.model_dump(exclude_none=True) for t in spec.tools]),
            "cfg": json.dumps(
                {
                    k: v.model_dump(exclude_none=True)
                    for k, v in spec.config_schema.items()
                }
            ),
            "quality": json.dumps(spec.quality.model_dump(exclude_none=True)),
            "budget": spec.budget.default_monthly_cents,
            "report": json.dumps(
                {"reason": "seeded from git specs; eval gate not run in deploy"}
            ),
        },
    )


def downgrade() -> None:
    # Versions cascade from the identity row's slug FK.
    op.get_bind().execute(
        sa.text("DELETE FROM agent_templates WHERE slug = :slug"), {"slug": _SLUG}
    )
