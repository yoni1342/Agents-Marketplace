"""add the Publishing shelf: ai-marketing-engine, book-metadata-generator, manuscript-editor

Revision ID: 0005_publishing
Revises: 0004_versions
Create Date: 2026-07-17

Seeds the three Publishing agents into the catalog. Data-only; no schema change.

WHY A MIGRATION, when these agents are authored as git specs under ``agents/``:

``python -m app.cli sync agents/`` is the only thing that turns those specs into
catalog rows, and it is a LOCAL command — the deploy workflow builds, migrates,
and rolls the service, and never syncs. So a spec-only change reaches the image
and stops there: the files are present at /app/agents in production and nothing
reads them. Adding the specs alone would have looked complete, deployed cleanly,
and left the Publishing category invisible.

Migrations are the mechanism that already works (see 0002 and 0003, which seed
templates the same way) and they run against prod on every deploy via
run-migrations.sh. So this is the seam.

The rows are built by READING the git specs rather than restating them, so the
spec files stay the single source of truth and the prompt in the catalog cannot
drift from the prompt in the repo.

Only the three new slugs are touched, deliberately. ``catalog_sync.sync_specs``
would have been shorter, but it UPDATES every identity it finds — and at least
one existing spec in ``agents/`` carries an older preamble than the row live in
production, so a blanket sync would quietly rewrite prompts for agents nobody
asked us to touch. ON CONFLICT DO NOTHING keeps this additive.
"""
from pathlib import Path
from typing import Sequence, Union
from uuid import uuid4

import sqlalchemy as sa
from alembic import op

revision: str = "0005_publishing"
down_revision: Union[str, Sequence[str], None] = "0004_versions"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_SLUGS = ("ai-marketing-engine", "book-metadata-generator", "manuscript-editor")

# agents/ sits next to app/ in the image; this file is alembic/versions/x.py.
_AGENTS_ROOT = Path(__file__).resolve().parents[2] / "agents"


def _packages():
    from app.spec_repo import discover_packages

    wanted = {}
    for pkg in discover_packages(_AGENTS_ROOT):
        if pkg.manifest.slug in _SLUGS:
            latest = max(
                (vf.spec for vf in pkg.versions),
                key=lambda s: tuple(int(p) for p in s.version.split(".")),
            )
            wanted[pkg.manifest.slug] = (pkg.manifest, latest)
    missing = set(_SLUGS) - set(wanted)
    if missing:
        raise RuntimeError(f"Publishing specs missing from agents/: {sorted(missing)}")
    return wanted


def upgrade() -> None:
    import json

    bind = op.get_bind()
    for slug, (manifest, spec) in _packages().items():
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
                # Hire-only, on purpose. A plumber opening Bench should not find
                # a book-metadata agent already on their roster, and the starter
                # bench already ships The Marketer.
                "starter": manifest.is_starter,
            },
        )
        # The rich version row: Bench's versioned activation path pulls
        # (slug, version) and copies it into the client's runtime, so without
        # this the template browses but cannot be activated with its config.
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
                "tools": json.dumps(
                    [t.model_dump(exclude_none=True) for t in spec.tools]
                ),
                "cfg": json.dumps(
                    {k: v.model_dump(exclude_none=True) for k, v in spec.config_schema.items()}
                ),
                "quality": json.dumps(spec.quality.model_dump(exclude_none=True)),
                "budget": spec.budget.default_monthly_cents,
                # Matches every other row in this catalog: the gate needs the
                # claude CLI, which no deployed image has. Declared, not implied.
                "report": json.dumps(
                    {"reason": "seeded from git specs; eval gate not run in deploy"}
                ),
            },
        )


def downgrade() -> None:
    bind = op.get_bind()
    for slug in _SLUGS:
        # Versions cascade from the identity row's slug FK.
        bind.execute(
            sa.text("DELETE FROM agent_templates WHERE slug = :slug"), {"slug": slug}
        )
