"""Marketplace data model.

A single table: ``agent_templates``. Each row is a *pure spec* — name,
tagline, role, default model/budget, system prompt, and UI grouping
metadata. The marketplace never stores anything org- or user-scoped; the
notion of "which org has activated which template" lives in Bench (its
``agents.template_slug`` column) and is layered on at read time by Bench's
backend. Keeping this table org-agnostic is what lets the service stay
independent.

This is intentionally identical in shape to the ``AgentTemplate`` that used
to live in Bench's ``models.py`` — the extraction is a lift, not a rewrite.
"""
from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy import Column, DateTime
from sqlmodel import Field, SQLModel


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


_TZ_DATETIME = DateTime(timezone=True)


class AgentTemplate(SQLModel, table=True):
    """A specialist available in the marketplace that can be activated
    onto an organization's bench in Bench.

    The seven canonical bench roles (Strategist, Marketer, Closer, ...) are
    seeded into every org by Bench's ``ensure_default_agents`` and are NOT
    represented here — they're the starter team. ``AgentTemplate`` rows are
    *additional* specialists an admin can browse and add on demand.

    When activated, Bench creates an ordinary ``Agent`` from these fields
    and stamps ``Agent.template_slug = slug`` so the marketplace UI can show
    "already on your bench".
    """

    __tablename__ = "agent_templates"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    # Stable identifier referenced by Bench's ``Agent.template_slug``.
    # Lowercase kebab-case, e.g. "bookkeeper", "newsletter-writer".
    slug: str = Field(sa_column_kwargs={"unique": True}, index=True)
    # Display name, including the definite article ("The Bookkeeper").
    name: str
    # First-person hook rendered on the card; copied to the Agent's tagline.
    tagline: str
    # Short role descriptor; copied to Agent.role on activation.
    role: str
    # Long system prompt; copied to Agent.system_prompt on activation.
    system_prompt: str
    # Default model + budget the template ships with.
    default_model: str
    default_budget_cents: int
    # UI grouping ("Finance", "People", "Marketing", "Operations", ...).
    category: str
    # Sort order within a category (lower = earlier); ties broken by name.
    sort_order: int = 0
    # True for platform-seeded templates; reserved for a future admin catalog.
    is_built_in: bool = Field(default=True, index=True)
    # True for the starter team (CEO + 7 canonical roles) that Bench auto-seeds
    # into every org. Starter templates are HIDDEN from the hireable browse
    # list and surfaced only via GET /v1/templates/starter (for seeding).
    is_starter: bool = Field(default=False, index=True)
    created_at: datetime = Field(default_factory=_utcnow, sa_column=Column(_TZ_DATETIME))
