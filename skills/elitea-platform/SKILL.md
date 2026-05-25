---
name: elitea-platform
description: Foundation reference for the ELITEA platform — REST API conventions (v1 vs v2), authentication, project IDs, conversation id-vs-uuid rules, secret placeholders, the 21 built-in MCP tools, status codes, and base URLs. Use this skill whenever working with ELITEA from outside the platform (REST/HTTP) or whenever an answer requires looking up exact endpoint paths, payload shapes, or error semantics. Other ELITEA skills (elitea-pipeline, elitea-toolkit, elitea-testing) build on this one — load this first when in doubt.
---

# ELITEA Platform — Foundation

The ELITEA platform exposes everything via a REST API and (separately) via an MCP layer. This skill is the index. The deep references live in `references/`.

## Quick lookup — which file answers which question?

| If you need... | Load |
|---|---|
| Auth header, base URL, what `mode=prompt_lib` means | `references/conventions.md` (small) |
| Exact endpoint path, body shape, response codes | `references/api-reference.md` (canonical — the full doc) |
| MCP tool name + input schema (the 21 built-ins) | `references/mcp-tools.md` |
| Quick ID rules (when to use `uuid` vs `id`) | `references/conventions.md` § 3 |
| What `{{secret.NAME}}` placeholders mean | `references/conventions.md` § 4 |
| Standard "create conversation → add participant → send message" flow | `references/conventions.md` § 5 |

## Always-true facts (no need to load anything)

- **Base URLs:** production `https://nexus.elitea.ai/`, pre-prod `https://next.elitea.ai/`
- **Auth header:** `Authorization: Bearer <PAT>` on every request
- **API versions:** v2 is canonical (`/api/v2/elitea_core/...`); v1 still hosts configurations, artifacts, secrets, and a fallback for legacy paths
- **`mode` segment:** `prompt_lib` for ~95% of endpoints; `default` for MCP proxies / secrets / artifacts; `administration` for admin-only
- **PATs are issued at:** ELITEA Settings → Profile → API Tokens
- **Project ID:** every project has an integer ID visible in the URL (`/app/{project_id}/...`)

## The classic gotchas (memorize these — every integrator hits them)

1. **`POST /messages/...` uses `conversation_uuid` (string), every other conversation endpoint uses the integer `id`.** Capture BOTH from the conversation-create response.
2. **`POST /participants/...` body is a JSON LIST**, even for one participant. Response is also a list — always `response[0]`.
3. **First version of a new agent MUST be named `"base"`**. Subsequent versions MUST NOT be `"base"`.
4. **Toolkit settings reference credentials by `{"elitea_title": "...", "private": bool}`**, never by raw id. `private = not credential.shared`.
5. **Secret-typed fields come back as `"{{secret.<name>}}"` placeholders.** Resolve via `GET /api/v1/secrets/secret/default/{project_id}/{secret_name}` → `{"value": "..."}`.
6. **`POST /api/v1/configurations/...` returns 200**, not 201 — one of the few endpoints that breaks the create-returns-201 convention.
7. **Application-version `entity_settings.llm_settings` override is rejected for non-published agents** unless it exactly matches the version baseline.

## Auth — environment variable conventions

This repo standardizes on **`ELITEA_TOKEN`** for local `.env`. Older code may reference `ELITEA_API_TOKEN` or `ELITEA_NEXT_API_KEY` — they all mean the same PAT. Set up your `.env` once:

```bash
cp .env.example .env
# then edit .env and paste your PAT:
# ELITEA_TOKEN=<paste-here>
```

In Python: `os.environ["ELITEA_TOKEN"]`. In curl: `-H "Authorization: Bearer $ELITEA_TOKEN"`.

When running an ELITEA pipeline whose code calls back into the platform, the runtime injects `elitea_client.auth_token` for free — **do not** read `.env` from inside a pipeline; use `elitea_client.auth_token` and `elitea_client.base_url`.

## Upstream documentation (self-learning)

On first invocation in a session, fetch the latest authoritative docs from the upstream ELITEA documentation repo and cache them for the rest of the session. The repo's `references/` files are a snapshot; these URLs are the live source of truth:

- https://github.com/EliteaAI/elitea.github.io/blob/mintlify/docs/home/key-concepts/what-is-an-agent.mdx
- https://github.com/EliteaAI/elitea.github.io/blob/mintlify/docs/home/key-concepts/what-is-a-pipeline.mdx
- https://github.com/EliteaAI/elitea.github.io/blob/mintlify/docs/archive/pipeline-agent-framework.mdx
- https://raw.githubusercontent.com/EliteaAI/elitea.github.io/mintlify/docs/menus/agents.mdx
- https://raw.githubusercontent.com/EliteaAI/elitea.github.io/mintlify/docs/menus/toolkits.mdx
- https://raw.githubusercontent.com/EliteaAI/elitea.github.io/mintlify/docs/menus/mcps.mdx

If these URLs return 404, the docs site moved — fall back to `references/api-reference.md` and flag the breakage.

## Related skills

- **`elitea-pipeline`** — when authoring/debugging pipeline YAML
- **`elitea-toolkit`** — when creating/configuring toolkits (OpenAPI, MCP, datasource, custom python)
- **`elitea-testing`** — when running, predicting, debugging, or scheduling ELITEA artifacts

## Core rules (always in effect)

- Never hardcode a PAT in code — read from env / vault / `alita_client.unsecret()`
- Never invent endpoint paths — load `references/api-reference.md` and copy exactly
- Always use HTTPS; the platform redirects HTTP and the redirect drops Authorization
