"""Sync git-authored specs into the marketplace database."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from sqlmodel import Session, select

from . import eval as eval_gate
from .models import AgentTemplate, AgentTemplateVersion
from .spec import AgentSpec, SpecValidationError
from .spec_repo import AgentPackage, RepoValidationError, discover_packages


def semver_key(version: str) -> tuple[int, int, int]:
    major, minor, patch = (int(p) for p in version.split("."))
    return (major, minor, patch)


@dataclass
class SyncedVersion:
    slug: str
    version: str
    action: str
    eval_passed: bool


@dataclass
class SyncReport:
    packages: int = 0
    identities_created: int = 0
    identities_updated: int = 0
    versions_created: int = 0
    versions_skipped: int = 0
    versions: list[SyncedVersion] = field(default_factory=list)


def _latest_version(package: AgentPackage) -> AgentSpec:
    return max((vf.spec for vf in package.versions), key=lambda spec: semver_key(spec.version))


def _upsert_identity(session: Session, package: AgentPackage) -> tuple[AgentTemplate, str]:
    latest = _latest_version(package)
    manifest = package.manifest
    existing = session.exec(
        select(AgentTemplate).where(AgentTemplate.slug == manifest.slug)
    ).first()
    action = "updated"
    if existing is None:
        existing = AgentTemplate(
            slug=manifest.slug,
            name=latest.name,
            tagline=latest.tagline,
            role=manifest.role,
            system_prompt=latest.system_prompt,
            default_model=latest.model.default,
            default_budget_cents=latest.budget.default_monthly_cents,
            category=latest.category,
            sort_order=manifest.sort_order,
            is_built_in=manifest.is_built_in,
            is_starter=manifest.is_starter,
            maintainer=latest.maintainer,
        )
        session.add(existing)
        action = "created"
    else:
        existing.name = latest.name
        existing.tagline = latest.tagline
        existing.role = manifest.role
        existing.system_prompt = latest.system_prompt
        existing.default_model = latest.model.default
        existing.default_budget_cents = latest.budget.default_monthly_cents
        existing.category = latest.category
        existing.sort_order = manifest.sort_order
        existing.is_built_in = manifest.is_built_in
        existing.is_starter = manifest.is_starter
        existing.maintainer = latest.maintainer
        session.add(existing)
    session.flush()
    return existing, action


def _eval_spec(spec: AgentSpec, allow_uneval: bool) -> tuple[bool, dict[str, Any]]:
    if spec.quality.eval_cases:
        try:
            report = eval_gate.run_eval(spec)
        except eval_gate.EvalError as exc:
            if allow_uneval:
                return False, {
                    "reason": "published from git sync without a runnable eval gate",
                    "error": str(exc),
                }
            raise RepoValidationError(
                f"{spec.slug} v{spec.version}: eval gate could not run: {exc}"
            ) from exc
        if not report.passed:
            if allow_uneval:
                return False, report.to_dict()
            raise RepoValidationError(
                f"{spec.slug} v{spec.version}: eval gate rejected publish: {report.to_dict()}"
            )
        return True, report.to_dict()
    if not allow_uneval:
        raise RepoValidationError(
            f"{spec.slug} v{spec.version}: no quality.eval_cases; sync requires --allow-uneval"
        )
    return False, {"reason": "published from git sync without eval_cases"}


def sync_specs(
    session: Session,
    root: str | Path,
    *,
    allow_uneval: bool = False,
) -> SyncReport:
    packages = discover_packages(root)
    report = SyncReport(packages=len(packages))

    for package in packages:
        template, identity_action = _upsert_identity(session, package)
        if identity_action == "created":
            report.identities_created += 1
        else:
            report.identities_updated += 1

        latest_existing = template.latest_version or ""
        for version_file in sorted(package.versions, key=lambda vf: semver_key(vf.spec.version)):
            spec = version_file.spec
            existing = session.exec(
                select(AgentTemplateVersion)
                .where(AgentTemplateVersion.slug == spec.slug)
                .where(AgentTemplateVersion.version == spec.version)
            ).first()
            if existing is not None:
                report.versions_skipped += 1
                report.versions.append(
                    SyncedVersion(
                        slug=spec.slug,
                        version=spec.version,
                        action="skipped",
                        eval_passed=existing.eval_passed,
                    )
                )
                if not latest_existing or semver_key(spec.version) > semver_key(latest_existing):
                    latest_existing = spec.version
                continue

            eval_passed, eval_report = _eval_spec(spec, allow_uneval=allow_uneval)
            row = AgentTemplateVersion(
                slug=spec.slug,
                version=spec.version,
                system_prompt=spec.system_prompt,
                model_routing=spec.model.model_dump(exclude_none=True),
                tools=[t.model_dump(exclude_none=True) for t in spec.tools],
                config_schema={k: v.model_dump(exclude_none=True) for k, v in spec.config_schema.items()},
                quality=spec.quality.model_dump(exclude_none=True),
                budget_cents=spec.budget.default_monthly_cents,
                eval_passed=eval_passed,
                eval_report=eval_report,
            )
            session.add(row)
            report.versions_created += 1
            report.versions.append(
                SyncedVersion(
                    slug=spec.slug,
                    version=spec.version,
                    action="created",
                    eval_passed=eval_passed,
                )
            )
            if not latest_existing or semver_key(spec.version) > semver_key(latest_existing):
                latest_existing = spec.version

        template.latest_version = latest_existing
        latest = _latest_version(package)
        template.name = latest.name
        template.tagline = latest.tagline
        template.category = latest.category
        template.maintainer = latest.maintainer
        template.system_prompt = latest.system_prompt
        template.default_model = latest.model.default
        template.default_budget_cents = latest.budget.default_monthly_cents
        session.add(template)

    session.commit()
    return report
