# The SEO Cluster Strategist

## What it does

Builds cluster-first SEO plans instead of generic keyword dumps.

It is for:

- pillar/supporting content structure
- commercially grounded search strategy
- storing the plan in a connected tracker
- notifying the team when a strategy draft is ready

## Required user-side connections

- `google_sheets` — to store cluster plans or work queues
- `slack` — optional notifications for strategy review

## Maintenance notes

- keep this cluster-first; do not let it turn into a keyword list generator
- if the output becomes too abstract, tighten the `must_include` sections in
  `quality.yaml`
