"""Git-backed agent spec repository.

The marketplace serves from Postgres, but developers author agents in git. This
module defines the file layout and loads agent packages from ``specs/`` so CI,
CLI tools, and deploy-time sync all use the same rules.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, ValidationError, field_validator

from .spec import AgentSpec, SpecValidationError, _SLUG_RE, load_spec


class RepoValidationError(ValueError):
    """A git-backed spec package is malformed."""


class AgentManifest(BaseModel):
    """Stable identity + marketplace metadata for a file-authored agent."""

    model_config = ConfigDict(extra="forbid")

    slug: str
    role: str
    sort_order: int = 0
    is_starter: bool = False
    is_built_in: bool = True

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


def _load_versions(slug: str, version_dir: Path) -> tuple[VersionFile, ...]:
    if not version_dir.exists():
        raise RepoValidationError(f"{version_dir}: missing versions/ directory")
    files = sorted(
        [p for p in version_dir.iterdir() if p.is_file() and p.suffix in {".yaml", ".yml"}]
    )
    if not files:
        raise RepoValidationError(f"{version_dir}: no version spec files found")

    loaded: list[VersionFile] = []
    seen_versions: set[str] = set()
    for path in files:
        try:
            spec = load_spec(path.read_text(encoding="utf-8"))
        except OSError as exc:
            raise RepoValidationError(f"cannot read {path}: {exc}") from exc
        except SpecValidationError as exc:
            raise RepoValidationError(f"{path}: {exc}") from exc
        if spec.slug != slug:
            raise RepoValidationError(
                f"{path}: spec slug {spec.slug!r} does not match package slug {slug!r}"
            )
        if spec.version in seen_versions:
            raise RepoValidationError(f"{path}: duplicate version {spec.version!r}")
        seen_versions.add(spec.version)
        loaded.append(VersionFile(path=path, spec=spec))
    return tuple(loaded)


def discover_packages(root: str | Path) -> list[AgentPackage]:
    """Load all file-authored agent packages from ``specs/``.

    Layout:

    ``specs/<slug>/agent.yaml``     stable identity / marketplace metadata
    ``specs/<slug>/versions/*.yaml`` immutable versioned agent specs
    """

    root_path = Path(root)
    if not root_path.exists():
        raise RepoValidationError(f"{root_path}: specs root does not exist")
    if not root_path.is_dir():
        raise RepoValidationError(f"{root_path}: specs root is not a directory")

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
