"""Agent spec schema v1 — the declarative definition of an agent.

This is "an agent is data, not code" made concrete (see
``docs/PLATFORM-BUILD-PLAN.md`` §4 and ``DECISIONS.md`` D-0006 in the
agent-platform repo). A developer authors one spec; the catalog stores it as a
published *version*; a client pulls a version and instantiates a runtime agent.

The models here are the single source of truth for the spec shape. They serve
three jobs:

1. **Validate on publish** — ``load_spec`` parses a dict or YAML string into a
   fully-typed :class:`AgentSpec`, raising :class:`SpecValidationError` with a
   readable message when a dev's spec is malformed. The future CI quality gate
   builds on this.
2. **Persist** — ``AgentSpec`` maps cleanly onto the ``agent_template_versions``
   row (jsonb columns for model/tools/config_schema/quality).
3. **Constrain client customization** — ``validate_overrides`` checks a client's
   ``config_overrides`` against the spec's ``config_schema`` (the guardrails),
   so a client can only customize what the dev allowed.

Pure data + pure functions, no DB or network — easy to unit-test and to reuse
from the runtime side.
"""
from __future__ import annotations

import re
from typing import Any, Literal

import yaml
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    field_validator,
    model_validator,
)

# semver MAJOR.MINOR.PATCH (no pre-release/build metadata in v1 — keep it tight).
_SEMVER_RE = re.compile(r"^\d+\.\d+\.\d+$")
# lowercase kebab-case slug, matching the catalog's existing convention.
_SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
# Pipedream app slugs use underscores (e.g. ``google_sheets``); allow both
# underscores and hyphens between alphanumeric segments.
_APP_SLUG_RE = re.compile(r"^[a-z0-9]+(?:[_-][a-z0-9]+)*$")

# Config-field types a client override may declare. Mirrors a minimal JSON-schema
# subset — enough for the guardrails in the plan (string/int/array/…).
ConfigType = Literal["string", "integer", "number", "boolean", "array", "object"]

# The safety axes the eval gate scores against. Open-ended (devs may add their
# own), but these are the canonical four from the plan.
DEFAULT_SAFETY_DIMENSIONS = ["hallucination", "brand_drift", "plagiarism", "topical_drift"]

# What a per-invocation metric record may track (see plan §6). Used as the
# default when a spec doesn't override ``monitoring.track``.
DEFAULT_MONITORING_TRACK = ["tokens", "cost", "latency", "quality_score", "flag_rate"]


class SpecValidationError(ValueError):
    """A spec failed schema validation. ``str(exc)`` is human-readable."""


class ModelRouting(BaseModel):
    """Multi-model routing (the aumata trick): a cheap/default/hard ladder so a
    spec can escalate only the steps that need it."""

    model_config = ConfigDict(extra="forbid")
    default: str
    hard: str | None = None
    cheap: str | None = None


class ToolDecl(BaseModel):
    """A capability the agent declares. ``via`` says how it's executed:
    ``pipedream`` → runs in the client's connected account; ``builtin`` (or
    omitted) → a platform-native tool (web_search, delegate_to_agent, …).

    ``app`` is the Pipedream app slug this tool maps to (e.g. ``google_sheets``,
    ``slack``); required when ``via == "pipedream"`` so the runtime knows which
    app's tools to surface. This is the minimal interim form of the tool→app
    mapping; the richer tool-id→workflow registry is M3."""

    model_config = ConfigDict(extra="forbid")
    id: str
    via: Literal["pipedream", "builtin"] = "builtin"
    app: str | None = None
    # Optional precise tool→workflow mapping (build plan M3): the specific
    # Pipedream MCP tool names to expose for this app (e.g.
    # ["google_sheets-add-single-row"]). When omitted, ALL of the app's tools
    # are surfaced (the M1 behavior). Lets a spec grant just the capability it
    # needs rather than the whole app surface.
    actions: list[str] | None = None

    @field_validator("app")
    @classmethod
    def _app_slug_ok(cls, v: str | None) -> str | None:
        if v is not None and not _APP_SLUG_RE.match(v):
            raise ValueError(f"app {v!r} must be a lowercase pipedream app slug")
        return v

    @model_validator(mode="after")
    def _pipedream_needs_app(self) -> "ToolDecl":
        if self.via == "pipedream" and not self.app:
            raise ValueError(f"tool {self.id!r}: via=pipedream requires an 'app' slug")
        return self


class ConfigField(BaseModel):
    """One client-customizable field — the guardrail definition. ``required``
    fields must be supplied at pull time; others fall back to ``default``."""

    model_config = ConfigDict(extra="forbid")
    type: ConfigType
    required: bool = False
    default: Any | None = None


class EvalExpect(BaseModel):
    model_config = ConfigDict(extra="forbid")
    min_score: float | None = None
    must_include: list[str] = Field(default_factory=list)
    must_not: list[str] = Field(default_factory=list)


class EvalCase(BaseModel):
    """One graded example: feed ``input`` to the agent, assert on ``expect``."""

    model_config = ConfigDict(extra="forbid")
    input: dict[str, Any] = Field(default_factory=dict)
    expect: EvalExpect = Field(default_factory=EvalExpect)


class Quality(BaseModel):
    """The moat — ships WITH the agent. The eval gate runs ``eval_cases`` and
    scores the ``safety_dimensions`` before a version may publish."""

    model_config = ConfigDict(extra="forbid")
    rubric: str = ""
    eval_cases: list[EvalCase] = Field(default_factory=list)
    safety_dimensions: list[str] = Field(default_factory=lambda: list(DEFAULT_SAFETY_DIMENSIONS))


class Budget(BaseModel):
    model_config = ConfigDict(extra="forbid")
    default_monthly_cents: int = 2500


class Monitoring(BaseModel):
    model_config = ConfigDict(extra="forbid")
    track: list[str] = Field(default_factory=lambda: list(DEFAULT_MONITORING_TRACK))


class AgentSpec(BaseModel):
    """A complete, versioned agent definition. Rich like aumata, pure data like
    the catalog. One published version == one of these."""

    model_config = ConfigDict(extra="forbid")

    slug: str
    version: str
    name: str
    category: str
    maintainer: str
    tagline: str = ""
    model: ModelRouting
    system_prompt: str
    tools: list[ToolDecl] = Field(default_factory=list)
    config_schema: dict[str, ConfigField] = Field(default_factory=dict)
    quality: Quality = Field(default_factory=Quality)
    budget: Budget = Field(default_factory=Budget)
    monitoring: Monitoring = Field(default_factory=Monitoring)

    @field_validator("slug")
    @classmethod
    def _slug_ok(cls, v: str) -> str:
        if not _SLUG_RE.match(v):
            raise ValueError(f"slug {v!r} must be lowercase kebab-case")
        return v

    @field_validator("version")
    @classmethod
    def _version_ok(cls, v: str) -> str:
        if not _SEMVER_RE.match(v):
            raise ValueError(f"version {v!r} must be semver MAJOR.MINOR.PATCH")
        return v

    @field_validator("system_prompt", "name", "category", "maintainer")
    @classmethod
    def _non_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("must not be empty")
        return v


def load_spec(data: str | dict[str, Any]) -> AgentSpec:
    """Parse + validate a spec from a YAML string or a dict.

    Raises :class:`SpecValidationError` (a ``ValueError``) with a readable,
    multi-line message on malformed YAML or schema violations.
    """
    if isinstance(data, str):
        try:
            parsed = yaml.safe_load(data)
        except yaml.YAMLError as exc:
            raise SpecValidationError(f"spec is not valid YAML: {exc}") from exc
    else:
        parsed = data
    if not isinstance(parsed, dict):
        raise SpecValidationError("spec must be a mapping (got %s)" % type(parsed).__name__)
    try:
        return AgentSpec.model_validate(parsed)
    except ValidationError as exc:
        lines = [
            f"  - {'.'.join(str(p) for p in e['loc'])}: {e['msg']}"
            for e in exc.errors()
        ]
        raise SpecValidationError(
            "agent spec failed validation:\n" + "\n".join(lines)
        ) from exc


def validate_overrides(
    config_schema: dict[str, ConfigField], overrides: dict[str, Any]
) -> dict[str, Any]:
    """Validate a client's ``config_overrides`` against the spec's guardrails.

    Returns the effective config (defaults filled in, overrides applied). Raises
    :class:`SpecValidationError` if a required field is missing, an unknown field
    is supplied, or a value's type doesn't match. This is the boundary of safe
    client customization — used at pull time on the runtime side.
    """
    errors: list[str] = []
    effective: dict[str, Any] = {}

    unknown = set(overrides) - set(config_schema)
    for key in sorted(unknown):
        errors.append(f"{key}: not a customizable field for this agent")

    for name, field in config_schema.items():
        if name in overrides:
            value = overrides[name]
            if not _type_ok(value, field.type):
                errors.append(f"{name}: expected {field.type}, got {type(value).__name__}")
            else:
                effective[name] = value
        elif field.required:
            errors.append(f"{name}: required")
        else:
            effective[name] = field.default

    if errors:
        raise SpecValidationError(
            "config overrides rejected:\n" + "\n".join(f"  - {e}" for e in errors)
        )
    return effective


_PY_TYPES: dict[str, tuple[type, ...]] = {
    "string": (str,),
    "integer": (int,),
    "number": (int, float),
    "boolean": (bool,),
    "array": (list,),
    "object": (dict,),
}


def _type_ok(value: Any, declared: str) -> bool:
    expected = _PY_TYPES[declared]
    # bool is a subclass of int — reject it where a number/integer is wanted so
    # ``True`` doesn't sneak past an integer field, and vice-versa.
    if declared in ("integer", "number") and isinstance(value, bool):
        return False
    if declared == "boolean":
        return isinstance(value, bool)
    return isinstance(value, expected)
