# Agent Marketplace

A standalone service that is the **single source of truth for every agent
definition** ("templates") on the [Bench platform](https://bench.nova4.ai).
It was extracted from Bench's monolith so agent definitions can be authored,
deployed, and scaled independently — while staying fully integrated with
Bench.

## What it is (and isn't)

- **Owns:** the `agent_templates` catalog — pure specs (name, tagline, role,
  system prompt, default model/budget, category). Its own Postgres database.
- **Does not own:** anything org- or user-scoped. It has no idea which org
  activated which template. It never touches Bench's database, and it is not
  involved at agent *run* time (see below).

The catalog holds **two kinds** of agent, distinguished by `is_starter`:

- **Starter team** (`is_starter = true`) — the CEO + seven canonical roles
  (Strategist, Marketer, Closer, Concierge, Operator, Grant Writer, Analyst)
  that Bench auto-seeds into **every** org at signup. Hidden from the
  hireable browse list; served only via `GET /v1/templates/starter`.
- **Hireable specialists** (`is_starter = false`) — extras an admin can add
  on demand (Bookkeeper, Recruiter, Newsletter Writer, PR Officer, Project
  Manager, Customer Researcher, SEO Specialist). These are what the
  marketplace browse page shows.

## Definition time vs. run time

The marketplace is involved only when an agent is **defined / seeded / hired**
— Bench copies the spec into an ordinary `Agent` row in its own DB at that
moment. At **run time** the executor reads that Agent row's `system_prompt`
and `model`; it never calls the marketplace. So editing a template only
affects orgs seeded/hired **after** the change (copy-on-seed, not live sync).

## Architecture & integration

```
Browser ──► Bench frontend ──► Bench backend ──HTTP(X-Marketplace-Key)──► Marketplace
                                   │                                          │
                                   │ owns: users/orgs/agents (Bench DB)       │ owns: agent_templates (Marketplace DB)
                                   ▼                                          ▼
                              creates Agent                              serves catalog spec
```

The integration is **server-to-server HTTP**, with Bench's backend as the
shim. The browser and Bench's `api.ts` are unchanged — Bench's
`/v1/agent-templates` router was rerouted from "read local table" to "call
this service + enrich".

**Browse** (`GET /v1/agent-templates` on Bench):
1. Bench backend calls `GET /v1/templates` here (with `X-Marketplace-Key`).
2. Bench enriches each entry with org-scoped `already_activated` /
   `activated_agent_id` from its **own** `agents` table.
3. Returns the merged list to the frontend.

**Activate / hire** (`POST /v1/agent-templates/{slug}/activate` on Bench, admin-only):
1. Bench backend calls `GET /v1/templates/{slug}` here to fetch the full spec
   (including `system_prompt`).
2. Bench creates an ordinary `Agent` in the caller's org from that spec and
   stamps `Agent.template_slug = slug`. Idempotent.

**Seed the starter team** (Bench `ensure_default_agents`, run at org provisioning):
1. Bench backend calls `GET /v1/templates/starter` here for the full starter specs.
2. Bench creates the starter agents in the new org from them. If the
   marketplace is unreachable, Bench falls back to a bundled copy so signups
   never break.

Bench remains the source of truth for `agents`; the marketplace is the source
of truth for the catalog (definitions).

## Auth

Two accepted credentials (see `app/auth.py`):

| Credential | Header | Used for |
|---|---|---|
| Service key | `X-Marketplace-Key: <key>` | Bench → marketplace (primary). Required for all write endpoints. |
| better-auth JWT | `Authorization: Bearer <jwt>` | Optional browser-direct reads; only when `BETTER_AUTH_JWKS_URL` is set. Validated against Bench's JWKS (EdDSA). |

Reads accept either; writes (catalog curation) require the service key.

## API

| Method | Path | Auth | Purpose |
|---|---|---|---|
| GET | `/health` | none | Liveness. |
| GET | `/v1/templates` | caller | List the **hireable** catalog (starters excluded). |
| GET | `/v1/templates/starter` | caller | Full starter-team specs, ordered (CEO first). |
| GET | `/v1/templates/{slug}` | caller | Full spec incl. `system_prompt`. |
| POST | `/v1/templates` | service key | Create a catalog entry. |
| PATCH | `/v1/templates/{slug}` | service key | Update an entry. |
| DELETE | `/v1/templates/{slug}` | service key | Remove an entry. |

## Adding or editing an agent

This is the only place you edit to add a new agent — Bench needs **no changes**
and picks it up automatically.

**Permanent (version-controlled) — recommended:**
1. Add an entry to the catalog source in `app/builtin_templates.py`:
   - `BUILTIN_TEMPLATES` for a hireable specialist, or
   - `STARTER_TEMPLATES` for a starter-team agent.
   Fields: `slug` (kebab-case, unique), `name`, `tagline` (first-person, role-
   voiced), `role`, `category`, `sort_order`, `default_model`,
   `default_budget_cents`, `system_prompt` (wrap role text in `_p(...)` so it
   gets the shared preamble).
2. Add an Alembic migration that inserts the row (see
   `0003_add_seo_specialist.py` — it imports the entry from
   `builtin_templates.py` and uses `ON CONFLICT (slug) DO NOTHING` so it's
   safe on both fresh and existing databases).
3. `alembic upgrade head` (the systemd unit does this on restart).

**Quick (no deploy) — for one-offs:** `POST /v1/templates` with the service
key. Good for experiments; prefer the code path for anything you want to keep.

Either way, the new agent appears in Bench immediately (hireable specialists on
the marketplace page; starter agents in the next org that's provisioned).
Editing the shared preamble? Keep it identical to Bench's
`default_agents._COMMON_PREAMBLE`.

## Local development

```bash
python -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env            # set MARKETPLACE_API_KEY
createdb agent_marketplace
alembic upgrade head            # creates table + seeds the catalog (starters + specialists)
uvicorn app.main:app --reload --port 8002

# smoke test
curl -s localhost:8002/health
curl -s -H "X-Marketplace-Key: $MARKETPLACE_API_KEY" localhost:8002/v1/templates | jq
```

## Bench-side configuration

Bench's backend needs two env vars (see Bench `.env.example`):

```
MARKETPLACE_URL=http://localhost:8002        # prod: internal service URL
MARKETPLACE_API_KEY=<same value as here>
```

## Deploy

Container listens on **:8002**. `Dockerfile` runs `alembic upgrade head`
then boots uvicorn. On the prod box, run alongside Bench (e.g. a
`marketplace` systemd unit + its own Postgres database), reachable from
Bench's backend over the internal network.
