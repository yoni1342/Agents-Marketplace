# Agent Spec Reference (schema v1)

The declarative definition of a marketplace agent. One spec file = one published
*version*. This reference matches `app/spec.py` (the validating loader) exactly —
if they ever disagree, the loader wins; file a fix. Copy
[`examples/agent-spec.template.yaml`](../examples/agent-spec.template.yaml) to
start. See [AUTHORING.md](./AUTHORING.md) for *how to write a good one*.

Validate / gate / publish with the CLI:

```
python -m app.cli lint    my-agent.yaml
python -m app.cli eval    my-agent.yaml
python -m app.cli publish my-agent.yaml
```

## Top-level fields

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `slug` | string | ✓ | Lowercase kebab-case stable id (`seo-specialist`). Never reuse/rename. |
| `version` | string | ✓ | Semver `MAJOR.MINOR.PATCH`. Bump every publish; versions are immutable. |
| `name` | string | ✓ | Display name; include the article ("The SEO Specialist"). |
| `category` | string | ✓ | UI grouping (Marketing, Finance, Operations, People, Research…). |
| `maintainer` | string | ✓ | Who owns/tunes this agent. |
| `tagline` | string | | First-person hook shown on the card. |
| `model` | object | ✓ | Model routing — see below. |
| `system_prompt` | string | ✓ | The prompt. Most of the agent's quality lives here. |
| `tools` | list | | Declared capabilities — see below. |
| `config_schema` | object | | Client-customizable fields (the guardrails). |
| `quality` | object | | Rubric + eval cases + safety dims (the eval gate). |
| `budget` | object | | `default_monthly_cents` the activated agent ships with. |
| `monitoring` | object | | `track`: which metrics to record per run. |

Unknown top-level keys are **rejected** (`extra="forbid"`) — typos fail lint.

## `model` — multi-model routing
```yaml
model:
  default: claude-sonnet-4-6   # required
  hard: claude-opus-4-6        # optional — escalate hard steps
  cheap: claude-haiku-4-5      # optional — trivial steps
```

## `tools`
Each entry:
| Key | Type | Notes |
|-----|------|-------|
| `id` | string | Logical capability name. |
| `via` | `builtin` \| `pipedream` | Default `builtin` (platform-native: web_search, …). |
| `app` | string | **Required when `via: pipedream`** — the Pipedream app slug (`google_sheets`, `slack`). |
| `actions` | list[string] | Optional. Expose only these specific MCP tool names; omit to expose the whole app. |

## `config_schema`
A map of `field → {type, required, default}`. `type` is one of
`string | integer | number | boolean | array | object`. At activation the client
supplies values; required fields must be present, types are checked, unknown
fields rejected. Validated by `validate_overrides` at pull time.

## `quality` — the eval gate (see build plan §7)
```yaml
quality:
  rubric: |
    How to grade an output 0.0–1.0: reward …; penalize …
  eval_cases:
    - input: { ... }            # fed to the agent
      expect:
        min_score: 0.7          # rubric score the output must reach (default 0.7)
        must_include: ["..."]   # substrings the output must contain
        must_not: ["..."]       # substrings it must not contain
  safety_dimensions: [hallucination, brand_drift, plagiarism, topical_drift]
```
A version **cannot publish** unless every eval case passes AND the worst safety
risk stays under the threshold (0.5). A spec with no `eval_cases` can only be
published with `--allow-uneval` (stored `eval_passed=false`).

## Versioning
- Published `(slug, version)` is **immutable** — fix-forward by bumping `version`.
- The catalog tracks `latest_version`; clients pull a specific version and see
  "upgrade available" when a newer one ships.
