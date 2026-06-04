# Agents

One folder per marketplace agent.

Each package contains:

- `agent.yaml` — stable marketplace identity
- `README.md` — what the agent does, what it needs, how to maintain it
- `versions/<semver>/` — immutable shipped versions

Each version bundle contains:

- `version.yaml`
- `system_prompt.md`
- `tools.yaml`
- `connections.yaml`
- `config.schema.yaml`
- `quality.yaml`
- optional `scripts/`

This keeps the package rich enough for developer work, while the marketplace
still compiles it into the runtime `AgentSpec` shape Bench already understands.
