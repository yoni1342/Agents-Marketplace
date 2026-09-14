"""the starter crew gets CORE's two missing rules; the Marketer waits for approval

Revision ID: 0010_marketer_approval
Revises: 0009_retire_dupes
Create Date: 2026-09-14

Two changes to the starter prompts, both already in Bench's fallback mirror:

- CORE gains THE USER'S MONEY and DO WHAT WAS ASKED. Bench added them to its
  mirror and to every existing agent (its migration d4f81a6c02b7), but never to
  this catalog — and new workspaces are seeded from here, so every workspace
  created since would have got a crew without them.
- The Marketer gains POSTING AND APPROVAL: schedule rather than publish, ask
  even when the user named the time, report where the approval is waiting. It
  is taking over the Social Media & Ads Manager's job.

Starter prompts are not synced from agents/ — 0008 wrote them from
STARTER_TEMPLATES — so new text reaches the catalog only through a migration.
Rewrites every starter prompt from that constant, like 0008.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

from app.builtin_templates import STARTER_TEMPLATES

revision: str = "0010_marketer_approval"
down_revision: Union[str, Sequence[str], None] = "0009_retire_dupes"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    for t in STARTER_TEMPLATES:
        bind.execute(
            sa.text("UPDATE agent_templates SET system_prompt = :prompt WHERE slug = :slug"),
            {"prompt": t["system_prompt"], "slug": t["slug"]},
        )


def downgrade() -> None:
    bind = op.get_bind()
    slugs = [t["slug"] for t in STARTER_TEMPLATES]
    # The two CORE rules sit between WHAT YOU KNOW and BEFORE YOU START. The
    # first quantifier is non-greedy, so Postgres takes the shortest match.
    bind.execute(
        sa.text(
            "UPDATE agent_templates SET system_prompt = regexp_replace("
            "system_prompt, :rules, 'BEFORE YOU START') WHERE slug = ANY(:slugs)"
        ),
        {"rules": "THE USER'S MONEY\n.*?BEFORE YOU START", "slugs": slugs},
    )
    # The approval section runs from its heading to the end of the prompt.
    bind.execute(
        sa.text(
            "UPDATE agent_templates SET system_prompt = "
            "regexp_replace(system_prompt, :section, '') WHERE slug = 'marketer'"
        ),
        {"section": "\n\nPOSTING AND APPROVAL\n.*$"},
    )
