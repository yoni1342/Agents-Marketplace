"""agentctl — author, lint, eval, and publish marketplace agent specs.

The contributor on-ramp (build plan §8 M6): a dev writes a spec file, validates
it, runs the quality gate locally, and publishes — without touching platform
code.

Usage (from the Agents-Marketplace repo root, in its venv):

    python -m app.cli lint    <spec.yaml>
    python -m app.cli eval    <spec.yaml>
    python -m app.cli publish <spec.yaml> [--url URL] [--key KEY] [--allow-uneval]

  lint     Validate the spec against schema v1. No network. Exit 1 on error.
  eval     Run the eval/quality gate locally (makes LLM calls via the claude
           CLI) and print the report. Exit 1 if it would not pass.
  publish  POST the spec to a running catalog, which re-runs the gate
           server-side and stores the version. Exit 1 on rejection.

Start from ``examples/agent-spec.template.yaml`` and see ``docs/AUTHORING.md``.
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request

from .config import settings
from .spec import SpecValidationError, load_spec


def _read(path: str) -> str:
    try:
        with open(path, encoding="utf-8") as f:
            return f.read()
    except OSError as exc:
        _die(f"cannot read {path}: {exc}")


def _die(msg: str, code: int = 1) -> "None":
    print(f"error: {msg}", file=sys.stderr)
    sys.exit(code)


def cmd_lint(args: argparse.Namespace) -> int:
    text = _read(args.spec)
    try:
        spec = load_spec(text)
    except SpecValidationError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    pd = [t.id for t in spec.tools if t.via == "pipedream"]
    print(f"OK  {spec.slug} v{spec.version} — {spec.name}")
    print(f"    model: {spec.model.default}  tools: {len(spec.tools)}"
          f" (pipedream: {', '.join(pd) or 'none'})")
    print(f"    config fields: {', '.join(spec.config_schema) or 'none'}")
    print(f"    eval_cases: {len(spec.quality.eval_cases)}  "
          f"safety_dims: {', '.join(spec.quality.safety_dimensions) or 'none'}")
    if not spec.quality.eval_cases:
        print("    note: no eval_cases — this spec can't pass the eval gate "
              "(publish needs --allow-uneval).")
    return 0


def cmd_eval(args: argparse.Namespace) -> int:
    # Imported lazily so `lint` works even where the claude CLI is absent.
    from . import eval as eval_gate

    text = _read(args.spec)
    try:
        spec = load_spec(text)
    except SpecValidationError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    if not spec.quality.eval_cases:
        _die("spec has no quality.eval_cases — nothing to evaluate.")
    try:
        report = eval_gate.run_eval(spec)
    except eval_gate.EvalError as exc:
        _die(f"eval gate could not run: {exc}", code=2)
    print(json.dumps(report.to_dict(), indent=2, default=str))
    print(f"\n{'PASS' if report.passed else 'FAIL'} — overall={report.overall_score} "
          f"max_risk={report.max_risk} (threshold {report.risk_threshold})")
    return 0 if report.passed else 1


def cmd_publish(args: argparse.Namespace) -> int:
    text = _read(args.spec)
    try:
        spec = load_spec(text)  # fail fast before any network
    except SpecValidationError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    url = args.url.rstrip("/")
    qs = "?allow_uneval=true" if args.allow_uneval else ""
    endpoint = f"{url}/v1/templates/{spec.slug}/versions{qs}"
    req = urllib.request.Request(
        endpoint,
        data=json.dumps(spec.model_dump()).encode("utf-8"),
        method="POST",
        headers={"Content-Type": "application/json", "X-Marketplace-Key": args.key},
    )
    try:
        with urllib.request.urlopen(req, timeout=300) as resp:
            body = json.load(resp)
        print(f"published {body['slug']} v{body['version']} "
              f"(eval_passed={body.get('eval_passed')})")
        return 0
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        print(f"rejected (HTTP {exc.code}): {detail}", file=sys.stderr)
        return 1
    except urllib.error.URLError as exc:
        _die(f"catalog unreachable at {url}: {exc.reason}")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="agentctl", description=__doc__)
    sub = p.add_subparsers(dest="command", required=True)

    sp = sub.add_parser("lint", help="validate a spec (no network)")
    sp.add_argument("spec")
    sp.set_defaults(func=cmd_lint)

    se = sub.add_parser("eval", help="run the eval gate locally")
    se.add_argument("spec")
    se.set_defaults(func=cmd_eval)

    pub = sub.add_parser("publish", help="publish a spec to a catalog")
    pub.add_argument("spec")
    pub.add_argument("--url", default="http://127.0.0.1:8002", help="catalog base URL")
    pub.add_argument("--key", default=settings.marketplace_api_key, help="X-Marketplace-Key")
    pub.add_argument("--allow-uneval", action="store_true",
                     help="publish a spec with no eval_cases (eval_passed=false)")
    pub.set_defaults(func=cmd_publish)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
