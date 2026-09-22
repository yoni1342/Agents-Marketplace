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

from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select

from .. import eval as eval_gate
from ..auth import require_service_key, verify_caller
from ..db import get_session
from ..models import AgentTemplate, AgentTemplateVersion, RetiredSlug
from ..spec import ConfigField, SpecValidationError, load_spec, validate_overrides

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
    # Newest published spec version for this slug ("" if none yet). Lets the
    # client compute "upgrade available" against what it pulled.
    latest_version: str = ""
    # What a new hire starts on ("" = Auto / automatic). See the model.
    hire_model: str = ""
    hire_image_model: str = ""


class TemplateDetail(TemplateEntry):
    """Full spec, including the system prompt — returned on single-slug
    fetch so Bench can stamp the activated Agent."""

    system_prompt: str
    created_at: datetime
    maintainer: str = ""
    is_starter: bool = False
    # When a Bench admin took this template over (None = still git-managed).
    admin_edited_at: datetime | None = None


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
    maintainer: str = ""
    hire_model: str = ""
    hire_image_model: str = ""


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
    maintainer: str | None = None
    hire_model: str | None = None
    hire_image_model: str | None = None


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
        latest_version=t.latest_version or "",
        hire_model=t.hire_model or "",
        hire_image_model=t.hire_image_model or "",
    )


def _to_detail(t: AgentTemplate) -> TemplateDetail:
    return TemplateDetail(
        **_to_entry(t).model_dump(),
        system_prompt=t.system_prompt,
        created_at=t.created_at,
        maintainer=t.maintainer or "",
        is_starter=t.is_starter,
        admin_edited_at=t.admin_edited_at,
    )


# ---- reads -----------------------------------------------------------------


@router.get("", response_model=TemplateListResponse)
def list_templates(
    _: None = Depends(verify_caller),
    session: Session = Depends(get_session),
) -> TemplateListResponse:
    """Hireable catalog — starter-team templates are excluded (they're already
    on every org's bench; see /starter for seeding)."""
    rows = list(
        session.exec(
            select(AgentTemplate)
            .where(AgentTemplate.is_built_in == True)  # noqa: E712
            .where(AgentTemplate.is_starter == False)  # noqa: E712
            .order_by(
                AgentTemplate.category,
                AgentTemplate.sort_order,
                AgentTemplate.name,
            )
        ).all()
    )
    return TemplateListResponse(templates=[_to_entry(t) for t in rows])


class StarterListResponse(BaseModel):
    templates: list[TemplateDetail]


@router.get("/starter", response_model=StarterListResponse)
def list_starter_templates(
    _: None = Depends(verify_caller),
    session: Session = Depends(get_session),
) -> StarterListResponse:
    """The starter team Bench seeds into every new org (CEO + 7 roles).

    Returns FULL specs (incl. system_prompt) ordered by sort_order so Bench
    can create the agents directly. Declared before the ``/{slug}`` route so
    "starter" isn't captured as a slug.
    """
    rows = list(
        session.exec(
            select(AgentTemplate)
            .where(AgentTemplate.is_starter == True)  # noqa: E712
            .order_by(AgentTemplate.sort_order, AgentTemplate.name)
        ).all()
    )
    return StarterListResponse(templates=[_to_detail(t) for t in rows])


class AdminTemplateEntry(TemplateEntry):
    """A catalog row as an operator sees it: hidden ones included."""

    maintainer: str = ""
    admin_edited_at: datetime | None = None
    version_count: int = 0
    created_at: datetime


class AdminTemplateListResponse(BaseModel):
    templates: list[AdminTemplateEntry]


@router.get("/all", response_model=AdminTemplateListResponse)
def list_all_templates(
    _: None = Depends(require_service_key),
    session: Session = Depends(get_session),
) -> AdminTemplateListResponse:
    """Every hireable template, including hidden ones (``is_built_in=false``)
    — the public list above can't show an operator what they've taken off
    the shelf. The starter crew is not here: it's Bench's core team, managed
    as Crew, not sold. Declared before ``/{slug}`` so "all" isn't a slug."""
    rows = session.exec(
        select(AgentTemplate)
        .where(AgentTemplate.is_starter == False)  # noqa: E712
        .order_by(AgentTemplate.category, AgentTemplate.sort_order, AgentTemplate.name)
    ).all()
    counts: dict[str, int] = {}
    for slug in session.exec(select(AgentTemplateVersion.slug)).all():
        counts[slug] = counts.get(slug, 0) + 1
    return AdminTemplateListResponse(
        templates=[
            AdminTemplateEntry(
                **_to_entry(t).model_dump(),
                maintainer=t.maintainer or "",
                admin_edited_at=t.admin_edited_at,
                version_count=counts.get(t.slug, 0),
                created_at=t.created_at,
            )
            for t in rows
        ]
    )


def _now() -> datetime:
    return datetime.now(timezone.utc)


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
    t = AgentTemplate(**body.model_dump(), admin_edited_at=_now())
    retired = session.get(RetiredSlug, body.slug)
    if retired is not None:
        session.delete(retired)
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
    # An operator's edit: the git sync must not undo it on the next boot.
    t.admin_edited_at = _now()
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
    # Remembered, so the git sync doesn't bring it back from agents/.
    if session.get(RetiredSlug, slug) is None:
        session.add(RetiredSlug(slug=slug))
    session.delete(t)
    session.commit()


# ---- rich-spec versions (build plan §4) ------------------------------------


class VersionSummary(BaseModel):
    """A published version's metadata — for the version list + 'upgrade
    available' checks. No prompt/spec body (see VersionDetail for that)."""

    slug: str
    version: str
    eval_passed: bool
    published_at: datetime


class VersionDetail(BaseModel):
    """A full published spec: identity fields (from the template) + the version
    body. This is what a client pulls to instantiate a runtime agent."""

    slug: str
    version: str
    name: str
    role: str
    category: str
    maintainer: str
    tagline: str
    system_prompt: str
    model_routing: dict
    tools: list
    config_schema: dict
    quality: dict
    budget_cents: int
    eval_passed: bool
    eval_report: dict
    published_at: datetime


def _semver_key(version: str) -> tuple[int, int, int]:
    """Sortable key for MAJOR.MINOR.PATCH (validated on publish, so safe)."""
    major, minor, patch = (int(p) for p in version.split("."))
    return (major, minor, patch)


def _version_detail(t: AgentTemplate, v: AgentTemplateVersion) -> VersionDetail:
    return VersionDetail(
        slug=v.slug,
        version=v.version,
        name=t.name,
        role=t.role,
        category=t.category,
        maintainer=t.maintainer or v.slug,
        tagline=t.tagline,
        system_prompt=v.system_prompt,
        model_routing=v.model_routing,
        tools=v.tools,
        config_schema=v.config_schema,
        quality=v.quality,
        budget_cents=v.budget_cents,
        eval_passed=v.eval_passed,
        eval_report=v.eval_report,
        published_at=v.published_at,
    )


@router.post("/{slug}/versions", response_model=VersionDetail, status_code=201)
def publish_version(
    slug: str,
    spec_body: dict,
    allow_uneval: bool = False,
    _: None = Depends(require_service_key),
    session: Session = Depends(get_session),
) -> VersionDetail:
    """Publish a new immutable version of a template's spec (operator-only).

    The body is a full agent spec (see ``app.spec.AgentSpec``); it is validated,
    then run through the **eval/quality gate** (build plan §7) before anything
    is written. The ``slug`` in the body must match the path. A published
    (slug, version) is immutable — re-publishing the same version is a 409.

    Gate rules:
    * spec has ``eval_cases`` → run them + the risk classifier; a failing report
      blocks the publish (422, report in the detail). The stored ``eval_report``
      records the run.
    * spec has NO ``eval_cases`` → there's nothing to gate on; blocked unless
      ``?allow_uneval=true`` is passed (the bootstrap escape hatch). Such a
      version is stored with ``eval_passed=false``.
    """
    try:
        spec = load_spec(spec_body)
    except SpecValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    if spec.slug != slug:
        raise HTTPException(
            status_code=400,
            detail=f"spec slug {spec.slug!r} does not match path slug {slug!r}",
        )

    template = session.exec(
        select(AgentTemplate).where(AgentTemplate.slug == slug)
    ).first()
    if template is None:
        raise HTTPException(
            status_code=404,
            detail=f"No template identity for slug {slug!r}; create the template first.",
        )

    existing = session.exec(
        select(AgentTemplateVersion)
        .where(AgentTemplateVersion.slug == slug)
        .where(AgentTemplateVersion.version == spec.version)
    ).first()
    if existing is not None:
        raise HTTPException(
            status_code=409,
            detail=f"version {spec.version} of {slug} is already published (immutable).",
        )

    # --- the eval/quality gate (build plan §7) ------------------------------
    # Strict unless ``allow_uneval``; with it, the same rule as the git sync: a
    # gate that can't run here (the image ships no claude CLI) or a failing
    # report still publishes, recorded as eval_passed=false with the reason.
    eval_passed = False
    eval_report: dict = {}
    if spec.quality.eval_cases:
        try:
            report = eval_gate.run_eval(spec)
        except eval_gate.EvalError as exc:
            if not allow_uneval:
                raise HTTPException(status_code=503, detail=f"Eval gate unavailable: {exc}")
            eval_report = {"reason": "published by an operator without a runnable eval gate", "error": str(exc)}
        else:
            eval_report = report.to_dict()
            if report.passed:
                eval_passed = True
            elif not allow_uneval:
                raise HTTPException(
                    status_code=422,
                    detail={
                        "message": (
                            f"{slug} v{spec.version} failed the eval/quality gate — "
                            "not published. Fix the prompt and bump the version."
                        ),
                        "report": eval_report,
                    },
                )
    elif not allow_uneval:
        raise HTTPException(
            status_code=422,
            detail=(
                "Spec has no quality.eval_cases, so it can't pass the eval gate. "
                "Add eval cases, or pass ?allow_uneval=true to publish ungated "
                "(it will be marked eval_passed=false)."
            ),
        )

    version = AgentTemplateVersion(
        slug=spec.slug,
        version=spec.version,
        system_prompt=spec.system_prompt,
        model_routing=spec.model.model_dump(),
        tools=[t.model_dump() for t in spec.tools],
        config_schema={k: v.model_dump() for k, v in spec.config_schema.items()},
        quality=spec.quality.model_dump(),
        budget_cents=spec.budget.default_monthly_cents,
        eval_passed=eval_passed,
        eval_report=eval_report,
    )
    session.add(version)

    # Keep the identity row's pointers in sync: latest_version = highest semver
    # published, and backfill maintainer from the spec if it was blank.
    all_versions = session.exec(
        select(AgentTemplateVersion.version).where(AgentTemplateVersion.slug == slug)
    ).all()
    candidates = list(all_versions) + [spec.version]
    template.latest_version = max(candidates, key=_semver_key)
    if not template.maintainer:
        template.maintainer = spec.maintainer
    # The listing follows the newest version, as it does after a git sync, so
    # the card and what a hire gets never disagree.
    if template.latest_version == spec.version:
        template.name = spec.name
        template.tagline = spec.tagline
        template.category = spec.category
        template.system_prompt = spec.system_prompt
        template.default_model = spec.model.default
        template.default_budget_cents = spec.budget.default_monthly_cents
    template.admin_edited_at = _now()
    session.add(template)

    session.commit()
    session.refresh(version)
    session.refresh(template)
    return _version_detail(template, version)


@router.get("/{slug}/versions", response_model=list[VersionSummary])
def list_versions(
    slug: str,
    _: None = Depends(verify_caller),
    session: Session = Depends(get_session),
) -> list[VersionSummary]:
    """List published versions for a slug, newest semver first."""
    rows = session.exec(
        select(AgentTemplateVersion).where(AgentTemplateVersion.slug == slug)
    ).all()
    rows.sort(key=lambda v: _semver_key(v.version), reverse=True)
    return [
        VersionSummary(
            slug=v.slug,
            version=v.version,
            eval_passed=v.eval_passed,
            published_at=v.published_at,
        )
        for v in rows
    ]


class ValidateConfigResponse(BaseModel):
    """The effective config after validating a client's overrides against a
    version's config_schema (defaults filled in)."""

    effective: dict


@router.post(
    "/{slug}/versions/{version}/validate-config",
    response_model=ValidateConfigResponse,
)
def validate_config(
    slug: str,
    version: str,
    config_overrides: dict,
    _: None = Depends(verify_caller),
    session: Session = Depends(get_session),
) -> ValidateConfigResponse:
    """Validate a client's config_overrides against a version's config_schema —
    the single authoritative implementation (the runtime calls this instead of
    re-implementing the rules; see DECISIONS D-0004). 422 with a readable detail
    when overrides are rejected."""
    v = session.exec(
        select(AgentTemplateVersion)
        .where(AgentTemplateVersion.slug == slug)
        .where(AgentTemplateVersion.version == version)
    ).first()
    if v is None:
        raise HTTPException(status_code=404, detail="Version not found")
    schema = {k: ConfigField(**vv) for k, vv in (v.config_schema or {}).items()}
    try:
        effective = validate_overrides(schema, config_overrides or {})
    except SpecValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    return ValidateConfigResponse(effective=effective)


@router.delete("/{slug}/versions/{version}", status_code=204)
def delete_version(
    slug: str,
    version: str,
    _: None = Depends(require_service_key),
    session: Session = Depends(get_session),
) -> None:
    """Remove one published version — an operator's mistake. Published versions
    never change, but they can go; the caller (Bench) refuses while a hired
    copy still runs it. The newest-version pointer and the listing's prompt,
    model and budget follow what's left, as they do after a publish."""
    template = session.exec(select(AgentTemplate).where(AgentTemplate.slug == slug)).first()
    v = session.exec(
        select(AgentTemplateVersion)
        .where(AgentTemplateVersion.slug == slug)
        .where(AgentTemplateVersion.version == version)
    ).first()
    if template is None or v is None:
        raise HTTPException(status_code=404, detail="Version not found")
    session.delete(v)
    session.flush()
    rest = session.exec(select(AgentTemplateVersion).where(AgentTemplateVersion.slug == slug)).all()
    if rest:
        newest = max(rest, key=lambda r: _semver_key(r.version))
        template.latest_version = newest.version
        template.system_prompt = newest.system_prompt
        template.default_model = (newest.model_routing or {}).get("default") or template.default_model
        template.default_budget_cents = newest.budget_cents
    else:
        template.latest_version = ""
    template.admin_edited_at = _now()
    session.add(template)
    session.commit()


@router.get("/{slug}/versions/{version}", response_model=VersionDetail)
def get_version(
    slug: str,
    version: str,
    _: None = Depends(verify_caller),
    session: Session = Depends(get_session),
) -> VersionDetail:
    """Fetch one full published spec — what a client pulls to instantiate."""
    template = session.exec(
        select(AgentTemplate).where(AgentTemplate.slug == slug)
    ).first()
    v = session.exec(
        select(AgentTemplateVersion)
        .where(AgentTemplateVersion.slug == slug)
        .where(AgentTemplateVersion.version == version)
    ).first()
    if template is None or v is None:
        raise HTTPException(status_code=404, detail="Version not found")
    return _version_detail(template, v)
