"""restate the starter crew's card descriptions

Revision ID: 0007_crew_cards
Revises: 0005_publishing
Create Date: 2026-09-08

The taglines shipped with the starter team were first-person slogans — "I make
your numbers talk so you decide with evidence, not gut" — which describe a
feeling rather than a job. These are the descriptions the website uses, so the
page that sells the crew and the card that lists it say the same thing.

Reads the new text from app.builtin_templates rather than repeating it, so the
constant stays the single source of truth. Guarded on the OLD text: a tagline
edited since seeding is left alone, which also makes this idempotent.

Only the six roles the site describes. Concierge and Analyst are untouched —
they have no copy on the site, being the two the crew is due to replace.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

from app.builtin_templates import STARTER_TEMPLATES

revision: str = "0007_crew_cards"
down_revision: Union[str, Sequence[str], None] = "0005_publishing"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# slug -> the tagline it was seeded with, which is what we are replacing.
_OLD: dict[str, str] = {
    "ceo": "I break goals into work and route each piece to the right teammate.",
    "strategist": "I turn goals into plans you can actually run.",
    "marketer": "I keep your voice in the market sounding like you.",
    "closer": "I keep your pipeline warm so deals don't go cold.",
    "operator": "I keep the engine running so nothing falls between the cracks.",
    "grant-writer": (
        "I find the funders, write the proposals, and free your team to serve."
    ),
}


def _new(slug: str) -> str:
    t = next((x for x in STARTER_TEMPLATES if x["slug"] == slug), None)
    if t is None:
        raise RuntimeError(f"{slug} missing from STARTER_TEMPLATES")
    return t["tagline"]


def _move(frm: dict[str, str], to: dict[str, str]) -> None:
    bind = op.get_bind()
    for slug in _OLD:
        bind.execute(
            sa.text(
                "UPDATE agent_templates SET tagline = :new "
                "WHERE slug = :slug AND tagline = :old"
            ),
            {"slug": slug, "old": frm[slug], "new": to[slug]},
        )


def upgrade() -> None:
    _move(_OLD, {s: _new(s) for s in _OLD})


def downgrade() -> None:
    _move({s: _new(s) for s in _OLD}, _OLD)
