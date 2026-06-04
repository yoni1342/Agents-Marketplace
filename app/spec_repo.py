"""Git-backed agent package repository.

The marketplace serves published versions from Postgres, but developers author
agents in git. Each agent lives under ``agents/<slug>/`` and each published
version is a bundle of files (prompt, tools, config, quality, connections).
The bundle is compiled into the runtime ``AgentSpec`` shape before syncing to
the DB.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from .spec import (
    AgentSpec,
    Budget,
    ConfigField,
    Monitoring,
    Quality,
    SpecValidationError,
    ToolDecl,
    _APP_SLUG_RE,
    _SLUG_RE,
    load_spec,
)


class RepoValidationError(ValueError):
    """A git-backed agent package is malformed."""


class AgentManifest(BaseModel):
    """Stable identity + marketplace metadata for a file-authored agent."""

    model_config = ConfigDict(extra="forbid")

    slug: str
    role: str
    sort_order: int = 0
    is_starter: bool = False
    is_built_in: bool = True
    summary: str = ""

    @field_validator("slug")
    @classmethod
    def _slug_ok(cls, v: str) -> str:
        if not _SLUG_RE.match(v):
            raise ValueError(f"slug {v!r} must be lowercase kebab-case")
        return v

    @field_validator("role")
    @classmethod
    def _role_non_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("role must not be empty")
        return v


class VersionManifest(BaseModel):
    """Version metadata separated from the prompt/tools bundle."""

    model_config = ConfigDict(extra="forbid")

    version: str
    name: str
    category: str
    maintainer: str
    tagline: str = ""
    model: dict
    budget: Budget = Field(default_factory=Budget)
    monitoring: Monitoring = Field(default_factory=Monitoring)


class ToolingFile(BaseModel):
    """Tool contract for a version bundle.

    ``skills`` and ``scripts`` are package-only metadata for future runtime DX
    and for human review. They don't compile into the runtime AgentSpec yet,
    but they belong with the agent package.
    """

    model_config = ConfigDict(extra="forbid")

    tools: list[ToolDecl] = Field(default_factory=list)
    skills: list[str] = Field(default_factory=list)
    scripts: list[str] = Field(default_factory=list)


class ConnectionDecl(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    app: str
    required: bool = True
    purpose: str
    user_configures: bool = True
    actions: list[str] = Field(default_factory=list)

    @field_validator("app")
    @classmethod
    def _app_slug_ok(cls, v: str) -> str:
        if not _APP_SLUG_RE.match(v):
            raise ValueError(f"app {v!r} must be a lowercase pipedream app slug")
        return v


class ConnectionsFile(BaseModel):
    model_config = ConfigDict(extra="forbid")
    connections: list[ConnectionDecl] = Field(default_factory=list)


@dataclass(frozen=True)
class VersionFile:
    path: Path
    spec: AgentSpec


@dataclass(frozen=True)
class AgentPackage:
    root: Path
    manifest_path: Path
    manifest: AgentManifest
    versions: tuple[VersionFile, ...]


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError as exc:
        raise RepoValidationError(f"cannot read {path}: {exc}") from exc


def _read_yaml(path: Path) -> object:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise RepoValidationError(f"cannot read {path}: {exc}") from exc
    try:
        return yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise RepoValidationError(f"{path}: invalid YAML: {exc}") from exc


def _load_manifest(path: Path) -> AgentManifest:
    data = _read_yaml(path)
    if not isinstance(data, dict):
        raise RepoValidationError(f"{path}: manifest must be a mapping")
    try:
        return AgentManifest.model_validate(data)
    except ValidationError as exc:
        lines = [
            f"  - {'.'.join(str(p) for p in e['loc'])}: {e['msg']}"
            for e in exc.errors()
        ]
        raise RepoValidationError(
            f"{path}: manifest failed validation:\n" + "\n".join(lines)
        ) from exc


def _model_validate_or_die(model_cls: type[BaseModel], path: Path, data: object) -> BaseModel:
    if data is None:
        data = {}
    if not isinstance(data, dict):
        raise RepoValidationError(f"{path}: expected a YAML mapping")
    try:
        return model_cls.model_validate(data)
    except ValidationError as exc:
        lines = [
            f"  - {'.'.join(str(p) for p in e['loc'])}: {e['msg']}"
            for e in exc.errors()
        ]
        raise RepoValidationError(f"{path}: validation failed:\n" + "\n".join(lines)) from exc


def _load_version_bundle(slug: str, bundle_dir: Path) -> VersionFile:
    version_meta = _model_validate_or_die(
        VersionManifest, bundle_dir / "version.yaml", _read_yaml(bundle_dir / "version.yaml")
    )
    system_prompt = _read_text(bundle_dir / "system_prompt.md").strip()
    if not system_prompt:
        raise RepoValidationError(f"{bundle_dir / 'system_prompt.md'}: system prompt must not be empty")

    tools_file = bundle_dir / "tools.yaml"
    tooling = ToolingFile()
    if tools_file.exists():
        tooling = _model_validate_or_die(ToolingFile, tools_file, _read_yaml(tools_file))  # type: ignore[assignment]
        for rel in tooling.scripts:
            script_path = bundle_dir / rel
            if not script_path.exists():
                raise RepoValidationError(f"{tools_file}: referenced script {rel!r} does not exist")

    config_path = bundle_dir / "config.schema.yaml"
    config_schema: dict[str, ConfigField] = {}
    if config_path.exists():
        data = _read_yaml(config_path)
        if data is None:
            data = {}
        if not isinstance(data, dict):
            raise RepoValidationError(f"{config_path}: expected a mapping of config fields")
        parsed: dict[str, ConfigField] = {}
        for key, value in data.items():
            try:
                parsed[key] = ConfigField.model_validate(value)
            except ValidationError as exc:
                lines = [
                    f"  - {'.'.join(str(p) for p in e['loc'])}: {e['msg']}"
                    for e in exc.errors()
                ]
                raise RepoValidationError(
                    f"{config_path}: config field {key!r} failed validation:\n" + "\n".join(lines)
                ) from exc
        config_schema = parsed

    quality_path = bundle_dir / "quality.yaml"
    quality = Quality()
    if quality_path.exists():
        quality = _model_validate_or_die(Quality, quality_path, _read_yaml(quality_path))  # type: ignore[assignment]

    connections_path = bundle_dir / "connections.yaml"
    if connections_path.exists():
        connections = _model_validate_or_die(
            ConnectionsFile, connections_path, _read_yaml(connections_path)
        )
        pipedream_tools = {
            t.app: t
            for t in tooling.tools
            if t.via == "pipedream" and t.app
        }
        for conn in connections.connections:
            if conn.app not in pipedream_tools:
                raise RepoValidationError(
                    f"{connections_path}: connection app {conn.app!r} has no matching via=pipedream tool"
                )

    spec_data = {
        "slug": slug,
        "version": version_meta.version,
        "name": version_meta.name,
        "category": version_meta.category,
        "maintainer": version_meta.maintainer,
        "tagline": version_meta.tagline,
        "model": version_meta.model,
        "system_prompt": system_prompt,
        "tools": [t.model_dump(exclude_none=True) for t in tooling.tools],
        "config_schema": {
            k: v.model_dump(exclude_none=True) for k, v in config_schema.items()
        },
        "quality": quality.model_dump(exclude_none=True),
        "budget": version_meta.budget.model_dump(exclude_none=True),
        "monitoring": version_meta.monitoring.model_dump(exclude_none=True),
    }
    try:
        spec = load_spec(spec_data)
    except SpecValidationError as exc:
        raise RepoValidationError(f"{bundle_dir}: {exc}") from exc
    return VersionFile(path=bundle_dir, spec=spec)


def _load_version_item(slug: str, path: Path) -> VersionFile:
    if path.is_file() and path.suffix in {".yaml", ".yml"}:
        try:
            spec = load_spec(_read_text(path))
        except SpecValidationError as exc:
            raise RepoValidationError(f"{path}: {exc}") from exc
        if spec.slug != slug:
            raise RepoValidationError(
                f"{path}: spec slug {spec.slug!r} does not match package slug {slug!r}"
            )
        return VersionFile(path=path, spec=spec)
    if path.is_dir():
        return _load_version_bundle(slug, path)
    raise RepoValidationError(f"{path}: unsupported version item")


def _load_versions(slug: str, version_dir: Path) -> tuple[VersionFile, ...]:
    if not version_dir.exists():
        raise RepoValidationError(f"{version_dir}: missing versions/ directory")
    items = sorted(
        [p for p in version_dir.iterdir() if p.is_dir() or p.suffix in {".yaml", ".yml"}],
        key=lambda p: p.name,
    )
    if not items:
        raise RepoValidationError(f"{version_dir}: no version specs found")

    loaded: list[VersionFile] = []
    seen_versions: set[str] = set()
    for path in items:
        version_file = _load_version_item(slug, path)
        if version_file.spec.version in seen_versions:
            raise RepoValidationError(
                f"{path}: duplicate version {version_file.spec.version!r}"
            )
        seen_versions.add(version_file.spec.version)
        loaded.append(version_file)
    return tuple(loaded)


def discover_packages(root: str | Path) -> list[AgentPackage]:
    """Load all git-authored agent packages from ``agents/``.

    Preferred layout:

    ``agents/<slug>/agent.yaml``
    ``agents/<slug>/versions/<version>/version.yaml``
    ``agents/<slug>/versions/<version>/system_prompt.md``
    ``agents/<slug>/versions/<version>/tools.yaml``
    ``agents/<slug>/versions/<version>/config.schema.yaml``
    ``agents/<slug>/versions/<version>/quality.yaml``
    ``agents/<slug>/versions/<version>/connections.yaml``

    Legacy flat version files (``versions/1.0.0.yaml``) still load so the
    transition doesn't break earlier specs.
    """

    root_path = Path(root)
    if not root_path.exists():
        raise RepoValidationError(f"{root_path}: agents root does not exist")
    if not root_path.is_dir():
        raise RepoValidationError(f"{root_path}: agents root is not a directory")

    packages: list[AgentPackage] = []
    seen_slugs: set[str] = set()
    for child in sorted([p for p in root_path.iterdir() if p.is_dir()]):
        manifest_path = child / "agent.yaml"
        if not manifest_path.exists():
            continue
        manifest = _load_manifest(manifest_path)
        if manifest.slug != child.name:
            raise RepoValidationError(
                f"{manifest_path}: slug {manifest.slug!r} must match directory name {child.name!r}"
            )
        if manifest.slug in seen_slugs:
            raise RepoValidationError(f"{manifest_path}: duplicate package slug {manifest.slug!r}")
        seen_slugs.add(manifest.slug)
        versions = _load_versions(manifest.slug, child / "versions")
        packages.append(
            AgentPackage(
                root=child,
                manifest_path=manifest_path,
                manifest=manifest,
                versions=versions,
            )
        )
    return packages
