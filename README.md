# Agent Marketplace

A standalone service that owns the **catalog of activatable agent
specialists** ("templates") for the [Bench platform](https://bench.nova4.ai).
It was extracted from Bench's monolith so the marketplace can be developed,
deployed, and scaled independently — while staying fully integrated with
Bench.

## What it is (and isn't)

- **Owns:** the `agent_templates` catalog — pure specs (name, tagline, role,
  system prompt, default model/budget, category). Its own Postgres database.
- **Does not own:** anything org- or user-scoped. It has no idea which org
  activated which template. It never touches Bench's database.

The seven canonical starter agents (Strategist, Marketer, Closer, …) are
**not** here — Bench seeds those into every org. This catalog is the
*additional* specialists an admin can hire (Bookkeeper, Recruiter, …).

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

**Activate** (`POST /v1/agent-templates/{slug}/activate` on Bench, admin-only):
1. Bench backend calls `GET /v1/templates/{slug}` here to fetch the full spec
   (including `system_prompt`).
2. Bench creates an ordinary `Agent` in the caller's org from that spec and
   stamps `Agent.template_slug = slug`. Idempotent, exactly as before.

Bench remains the source of truth for `agents`; the marketplace is the source
of truth for the catalog.

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
| GET | `/v1/templates` | caller | List built-in catalog (org-agnostic). |
| GET | `/v1/templates/{slug}` | caller | Full spec incl. `system_prompt`. |
| POST | `/v1/templates` | service key | Create a catalog entry. |
| PATCH | `/v1/templates/{slug}` | service key | Update an entry. |
| DELETE | `/v1/templates/{slug}` | service key | Remove an entry. |

## Local development

```bash
python -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env            # set MARKETPLACE_API_KEY
createdb agent_marketplace
alembic upgrade head            # creates table + seeds 6 built-ins
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
