# Write a Great Agent

The marketplace is dev-curated: quality is the moat, not the catalog UI. This is
the bar a spec should clear before you publish. Field mechanics are in
[SPEC.md](./SPEC.md); this doc is the *craft*.

## Package structure

Specialized agents now live in git as packages:

```text
specs/<slug>/
  agent.yaml
  versions/
    1.0.0.yaml
```

- `agent.yaml` holds the stable marketplace metadata (`role`, `sort_order`,
  starter vs hireable).
- `versions/*.yaml` are the immutable published agent specs.

Local commands:

```bash
python -m app.cli lint-all specs
python -m app.cli sync specs --allow-uneval
```

`sync` writes the git-authored packages into the local marketplace DB so you can
test the real browse/pull behavior end to end.

## The loop

```
cp examples/agent-spec.template.yaml my-agent.yaml
# edit...
python -m app.cli lint    my-agent.yaml     # schema valid?
python -m app.cli eval    my-agent.yaml     # does it pass the quality gate?
python -m app.cli publish my-agent.yaml     # ship it (re-gated server-side)
```
Bump `version` every time you publish — versions are immutable, and clients on an
older version see "upgrade available".

## 1. The system prompt is most of the quality

- **Be a specialist, not a chatbot.** State the role, what "done" looks like, and
  the format of the deliverable. "Produce the actual deliverable, not a plan to
  produce it."
- **Encode the method.** The good version of an SEO agent says *how* it does
  keyword research and *what* each recommendation must include — not just "do SEO".
- **Name the anti-patterns.** "Never keyword-stuff. Write for humans first."
- **Keep it portable.** The client customizes via `config_schema`, not by editing
  the prompt — so don't hard-code one client's brand into the prompt.

## 2. Route models by difficulty

`default` carries the work; set `cheap` (haiku) for trivial steps and `hard`
(opus) only for genuinely hard generation. Don't default everything to opus —
cost shows up on the dev per-version health dashboard.

## 3. Tools: grant the capability, not the kitchen sink

- `via: pipedream` tools run in the **client's** connected account — you hold no
  credentials. Map each to its `app` slug.
- Use `actions:` to expose only the MCP tools the agent actually needs. A
  spreadsheet-writer doesn't need every Google Sheets tool; scope it down. Fewer
  tools = less for the model to misuse and a cleaner client onboarding.

## 4. config_schema is the guardrail contract

Expose what a client *should* tune (brand voice, word count, off-limits topics)
and nothing that would let them break the agent. Mark the truly-required ones
`required: true`; give everything else a sensible `default`.

## 5. Quality is shipped, not hoped

This is what the eval gate enforces:

- **Rubric:** describe how to score an output 0–1 — what earns points, what loses
  them. Be specific enough that two readers would grade alike.
- **eval_cases:** at least one realistic input with an `expect`:
  - `min_score` — the rubric bar (start ~0.7).
  - `must_include` / `must_not` — cheap, deterministic guards for things that must
    (or must never) appear. Use substrings the agent can plausibly hit, not exact
    phrasings you're hoping for.
- **safety_dimensions:** the axes the adversarial classifier scores
  (hallucination, brand_drift, plagiarism, topical_drift, …). The gate fails if
  the worst risk reaches 0.5, and is **fail-closed** — a classifier error counts
  as max risk.

Add cases for the failure modes you actually worry about; a case is a regression
test for prompt edits.

## 6. Iterate against the gate

`python -m app.cli eval` runs the real gate locally and prints per-case scores +
safety. Tighten the prompt until it passes for the right reasons (read the
outputs — don't just chase the number). Then `publish`.

## Checklist before publishing

- [ ] `lint` is clean.
- [ ] System prompt names role, method, deliverable format, and anti-patterns.
- [ ] Models routed by difficulty (not all opus).
- [ ] Pipedream tools scoped with `actions:` where practical.
- [ ] `config_schema` covers what clients tune; required vs default set sensibly.
- [ ] Rubric is specific; ≥1 eval_case with must_include/must_not; safety dims set.
- [ ] `eval` passes for the right reasons. Version bumped.
