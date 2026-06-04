# The LinkedIn Thought Leadership Writer

## What it does

Turns one operator insight, news item, case study, or rough idea into a
publish-ready LinkedIn post.

This is not a generic content bot. The package is tuned for:

- founder/operator voice
- clear thesis-first writing
- practical posting notes
- explicit declaration of the user-side apps needed to save or queue the result

## Required user-side connections

- `linkedin` — to queue or publish posts through Pipedream
- `google_sheets` — to store ideas or review rows
- `slack` — to notify an editor or strategist

## Maintenance notes

- keep the voice rules in `system_prompt.md` specific and non-generic
- if the agent starts to overuse hype or engagement bait, add that failure mode
  to `quality.yaml`
- if the downstream execution changes, update both `tools.yaml` and
  `connections.yaml` together
