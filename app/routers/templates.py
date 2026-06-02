"""Catalog endpoints.

Read (``GET``): list the built-in catalog and fetch a single spec by slug.
These are what Bench's backend calls — to render the marketplace page (list)
and to activate a template (fetch one spec, then create the Agent locally).
The catalog is org-agnostic; the ``already_activated`` flag the UI shows is
layered on by Bench from its own ``agents`` table, not here.

Write (``POST`` / ``PATCH`` / ``DELETE``): operator-only catalog curation,
guarded by the shared service key.
"""
from __future__ import annotations

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select

from ..auth import require_service_key, verify_caller
from ..db import get_session
from ..models import AgentTemplate

router = APIRouter(prefix="/v1/templates", tags=["marketplace"])


# ---- response / request shapes ---------------------------------------------


class TemplateEntry(BaseModel):
    """One catalog entry. Note there is NO ``already_activated`` field — that
    is org-scoped state Bench owns and adds at its proxy layer."""

    slug: str
    name: str
    tagline: str
    role: str
    category: str
    default_model: str
    default_budget_cents: int
    sort_order: int
    is_built_in: bool


class TemplateDetail(TemplateEntry):
    """Full spec, including the system prompt — returned on single-slug
    fetch so Bench can stamp the activated Agent."""

    system_prompt: str
    created_at: datetime


class TemplateListResponse(BaseModel):
    templates: list[TemplateEntry]


class TemplateUpsert(BaseModel):
    slug: str
    name: str
    tagline: str
    role: str
    system_prompt: str
    default_model: str
    default_budget_cents: int
    category: str
    sort_order: int = 0
    is_built_in: bool = True


class TemplatePatch(BaseModel):
    name: str | None = None
    tagline: str | None = None
    role: str | None = None
    system_prompt: str | None = None
    default_model: str | None = None
    default_budget_cents: int | None = None
    category: str | None = None
    sort_order: int | None = None
    is_built_in: bool | None = None


def _to_entry(t: AgentTemplate) -> TemplateEntry:
    return TemplateEntry(
        slug=t.slug,
        name=t.name,
        tagline=t.tagline,
        role=t.role,
        category=t.category,
        default_model=t.default_model,
        default_budget_cents=t.default_budget_cents,
        sort_order=t.sort_order,
        is_built_in=t.is_built_in,
    )


def _to_detail(t: AgentTemplate) -> TemplateDetail:
    return TemplateDetail(
        **_to_entry(t).model_dump(),
        system_prompt=t.system_prompt,
        created_at=t.created_at,
    )


# ---- reads -----------------------------------------------------------------


@router.get("", response_model=TemplateListResponse)
def list_templates(
    _: None = Depends(verify_caller),
    session: Session = Depends(get_session),
) -> TemplateListResponse:
    rows = list(
        session.exec(
            select(AgentTemplate)
            .where(AgentTemplate.is_built_in == True)  # noqa: E712
            .order_by(
                AgentTemplate.category,
                AgentTemplate.sort_order,
                AgentTemplate.name,
            )
        ).all()
    )
    return TemplateListResponse(templates=[_to_entry(t) for t in rows])


@router.get("/{slug}", response_model=TemplateDetail)
def get_template(
    slug: str,
    _: None = Depends(verify_caller),
    session: Session = Depends(get_session),
) -> TemplateDetail:
    t = session.exec(
        select(AgentTemplate).where(AgentTemplate.slug == slug)
    ).first()
    if t is None:
        raise HTTPException(status_code=404, detail="Template not found")
    return _to_detail(t)


# ---- writes (operator-only) ------------------------------------------------


@router.post("", response_model=TemplateDetail, status_code=201)
def create_template(
    body: TemplateUpsert,
    _: None = Depends(require_service_key),
    session: Session = Depends(get_session),
) -> TemplateDetail:
    existing = session.exec(
        select(AgentTemplate).where(AgentTemplate.slug == body.slug)
    ).first()
    if existing is not None:
        raise HTTPException(status_code=409, detail="Slug already exists")
    t = AgentTemplate(**body.model_dump())
    session.add(t)
    session.commit()
    session.refresh(t)
    return _to_detail(t)


@router.patch("/{slug}", response_model=TemplateDetail)
def update_template(
    slug: str,
    body: TemplatePatch,
    _: None = Depends(require_service_key),
    session: Session = Depends(get_session),
) -> TemplateDetail:
    t = session.exec(
        select(AgentTemplate).where(AgentTemplate.slug == slug)
    ).first()
    if t is None:
        raise HTTPException(status_code=404, detail="Template not found")
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(t, field, value)
    session.add(t)
    session.commit()
    session.refresh(t)
    return _to_detail(t)


@router.delete("/{slug}", status_code=204)
def delete_template(
    slug: str,
    _: None = Depends(require_service_key),
    session: Session = Depends(get_session),
) -> None:
    t = session.exec(
        select(AgentTemplate).where(AgentTemplate.slug == slug)
    ).first()
    if t is None:
        raise HTTPException(status_code=404, detail="Template not found")
    session.delete(t)
    session.commit()
