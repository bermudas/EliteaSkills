# ELITEA Conventions — Quick Reference

The 90% of the platform you'll touch every day. For full endpoint details load `api-reference.md`.

## 1. Base URLs & API versioning

| Environment | Base URL |
|---|---|
| ELITEA (sole environment) | `https://next.elitea.ai/` |

> **History note.** Older docs and existing scripts in the wild reference `https://nexus.elitea.ai/` as "production". That host has been retired — `next.elitea.ai` is now the only ELITEA environment. If you see `nexus.elitea.ai` in a config, PAT example, or old code path, replace it with `next.elitea.ai`. Symptom of the old host still being targeted: a `307 → 302 → 400 access_denied` redirect chain through Centry's OIDC gateway. There is no separate "production" vs "pre-prod" — they were consolidated.

**v2 is canonical** — use `/api/v2/elitea_core/...` for everything except these v1-only subsystems:

| Subsystem | Path |
|---|---|
| Configurations / Credentials | `/api/v1/configurations/...` |
| Artifacts / Buckets | `/api/v1/artifacts/...` |
| Secrets | `/api/v1/secrets/...` |

## 2. The `mode` URL segment

Most v2 endpoints embed `<mode>` between the resource and `{project_id}`:

```
/api/v2/elitea_core/<resource>/<mode>/<project_id>/...
```

| `<mode>` | When |
|---|---|
| `prompt_lib` | ~95% of endpoints — default |
| `default` | MCP proxies, secrets, artifacts, tools_list, tools_call |
| `administration` | Admin-only endpoints (e.g., vectorstore) |

## 3. Authentication

Every request needs:

```
Authorization: Bearer <PAT>
Accept: */*                           # auto-added by most clients
Content-Type: application/json        # ONLY for POST/PUT/PATCH with a body
```

> **Do NOT send `Content-Type: application/json` on GET requests** — some proxies/WAFs reject it with a 400. Use `Accept: application/json` instead.

PATs are issued at: **ELITEA Settings → Profile → API Tokens**.

This repo standardizes on env var name **`ELITEA_TOKEN`**. Older code may use `ELITEA_API_TOKEN` or `ELITEA_NEXT_API_KEY` — same value.

### Special headers (rare)

| Header | Where | Why |
|---|---|---|
| `X-SECRET` | `PATCH /version/...` | Server-to-server "expanded view": returns version with credentials resolved inline |
| `X-USERSESSION` | with `X-SECRET` | Auth context; pass `-` for current user |
| `X-Toolkit-Tokens` | `toolkit_validator` | JSON-encoded OAuth tokens for MCP connection test |
| `X-Hub-Signature-256` / `X-Gitlab-Token` | `POST /webhook/...` | Webhook signature verification |

## 4. ID conventions — `id` vs `uuid`

The single most-common integrator bug. Memorize this:

| Resource | Integer `id` used in… | UUID/string used in… |
|---|---|---|
| **Conversation** | participants endpoints, conversation update/delete, entity_settings, attachments | `POST /messages/.../{conversation_uuid}` (send message) |
| **Message group** | (rare) | `GET /message/.../{uuid}`, `DELETE /message/.../{uuid}`, `POST /regenerate/.../{uuid}` |
| **Canvas** | — | `GET/PUT /canvas/.../{canvas_uuid}` |
| **Configuration** | `PUT /configuration/{project_id}/{configuration_id}` | When referenced inside toolkit settings: `{"elitea_title": "...", "private": <bool>}` instead of id |

> **Rule of thumb:** if you got the value from `POST .../conversations` and are about to call `.../messages/`, use the `uuid` field. Everywhere else use `id`.

## 5. Secret placeholders

When you `GET` a configuration, credential, or toolkit settings, **secret-typed fields come back as templated placeholders**, not `null` and not the raw value:

```json
{ "data": { "access_token": "{{secret.gh_pat_abc123}}" } }
```

To resolve:
- `GET /api/v1/secrets/secret/default/{project_id}/{secret_name}` → `{"value": "ghp_..."}`
- OR call `PATCH /api/v2/elitea_core/version/prompt_lib/{project_id}/{application_id}/{version_id}` with the `X-SECRET` header — returns the version with all configuration references resolved inline

Fields auto-vaulted (from `SENSITIVE_TOOLKIT_SETTINGS`): `access_key, password, username, api_key, access_token, token, app_private_key, google_cse_id, google_api_key, app_id, client_secret, gitlab_personal_access_token, private_token, sonar_token, qtest_api_token, client_id, oauth2`.

## 6. Credential references inside toolkits

When a toolkit's `settings` needs a credential, use the **name reference**, NOT a raw integer id:

```json
{
  "settings": {
    "github_configuration": {
      "elitea_title": "my-github-token",
      "private": true
    }
  }
}
```

- `elitea_title` matches the credential's `alita_title` (or `elitea_title`) field
- `private = not credential.shared` (a credential is "private" when not shared)

The same pattern applies for `pgvector_configuration`, `embedding_model.ai_credentials`, etc.

## 7. Status codes & their meanings

| Code | Meaning in this API |
|---|---|
| 200 | OK; also returned by **configuration create** (`POST /api/v1/configurations/...`) — unlike most other creates |
| 201 | Created (standard POST result) |
| 202 | Accepted — message still streaming, poll for completion |
| 204 | No Content — typical DELETE |
| 207 | Multi-Status — used by `import_wizard` and `fork` when some sub-entities imported and others failed |
| 400 | Validation / business-rule failure — body usually `{"error": "..."}` or `{"detail": "..."}` |
| 403 | RBAC denied; project blocks publishing |
| 404 | Entity not found |
| 408 | MCP sync timeout (`mcp_sync_tools`) |
| 409 | Already published |
| 422 | Publish validation `FAIL` state |
| 500 | Internal error |

## 8. The "always-true" workflow patterns

### Conversation → participant → message

```
1. POST /api/v2/elitea_core/conversations/prompt_lib/{project_id}
       body: {"name": "...", "is_private": true, "participants": []}
       → save id + uuid

2. POST /api/v2/elitea_core/participants/prompt_lib/{project_id}/{conv_id}
       body: [{"entity_name": "application", "entity_meta": {"id": agent_id, "project_id": project_id}, "entity_settings": {"version_id": ver_id}}]
       → save response[0].id as participant_id

3. POST /api/v2/elitea_core/messages/prompt_lib/{project_id}/{conv_UUID}     ← UUID not id!
       body: {"participant_id": participant_id, "user_input": "...", "await_task_timeout": 60}
       → 201 with message_groups OR 202 streaming OR 200 with task_id
```

### Stateless single-shot predict (no conversation)

```
POST /api/v2/elitea_core/predict/prompt_lib/{project_id}/{version_id}
     body: {"user_input": "...", "chat_history": []}
     → {"result": "...", "task_id": "..."}
```

### Create agent

```
POST /api/v2/elitea_core/applications/prompt_lib/{project_id}
     body: {
       "name": "My agent",
       "description": "...",
       "type": "interface",
       "versions": [
         {
           "name": "base",                              ← MUST be "base"
           "agent_type": "openai"|"pipeline"|"react",
           "instructions": "<system prompt or pipeline YAML>",
           "llm_settings": {model_name, model_project_id, temperature, max_tokens},
           "variables": [], "tools": [], "tags": [],
           "conversation_starters": [], "welcome_message": "...",
           "meta": {"step_limit": 25}
         }
       ]
     }
     → 201 with version_details.id
```

### Create credential

```
POST /api/v1/configurations/configurations/{project_id}
     body: {
       "elitea_title": "name-for-reference-from-toolkits",
       "label": "Human label",
       "type": "github"|"azure_open_ai"|"amazon_bedrock"|"pgvector"|...,
       "data": {...type-specific fields, secrets auto-vaulted...},
       "shared": false
     }
     → 200 (not 201!)
```

## 9. Inside-pipeline runtime helpers

When code runs **inside an ELITEA pipeline** (in a `code` node), the runtime injects helpers — do NOT read `.env`:

```python
# Auth & base URL — already authenticated as the calling user
elitea_client.auth_token        # the calling user's PAT
elitea_client.base_url          # base URL of the platform

# State access
elitea_state.get('var_name', default)

# alita_client (alias for some operations)
alita_client.unsecret('SECRET_NAME')         # resolve a stored secret
alita_client.artifact('bucket-name')         # artifact bucket helpers
alita_client.get_app_details(application_id) # introspect another agent
alita_client.mcp_tool_call(params)           # call an MCP tool
```

The `FetchUIContext.yaml` example pipeline shows all of these in action.

## 10. Misc one-liners worth remembering

- **First agent version MUST be named `"base"`.** Subsequent versions MUST NOT be `"base"`.
- **`POST /participants/...` body is a LIST**, even for one participant. Response is a list. Use `response[0]`.
- **`POST /import_wizard/...` body is a LIST**, not `{items: [...]}`.
- **`section` field on configurations is server-assigned** — don't send it on create.
- **`agent_type: "pipeline"` requires `instructions` to be valid YAML.**
- **Step limit defaults to 25** if `meta.step_limit` is not set on the version.
- **`return_task_id=true` is mutex with `await_task_timeout > 0`** on `POST /messages/...`.
- **Toolkit name gets sanitized server-side**: `re.sub(r'[^a-zA-Z0-9_.-]', '', name).replace('.', '_')`. Response `toolkit_name` is the sanitized form.
- **Tools array shape differs between CREATE and UPDATE.** On `POST /applications/...` each tool entry needs `type`, `toolkit_id`, `toolkit_name`, `name`, `settings`, `selected_tools` (description optional). On `PUT /version/.../{ver_id}` the same entry also needs `author_id`. Missing `author_id` returns `400 [{"loc": ["tools", N, "author_id"], "msg": "Field required"}]`. Easiest path: GET the existing version, mutate, PUT back — see `scripts/update_version_field.py`.

## 11. Model name resolution — do NOT trust short identifiers

`llm_settings.model_name` must be the **exact identifier** returned by the project's models endpoint, not a friendly short name. Wrong names do not error — they silently fall back to the project default (often `gpt-5-mini` or `gpt-5.4-mini`).

Query the live catalog first:

```
GET /api/v1/configurations/models/{project_id}?include_shared=true
→ { "total": N, "items": [
      { "name": "eu.anthropic.claude-sonnet-4-6", "display_name": "Anthropic Claude 4.6 Sonnet",
        "project_id": 1, "shared": true, "context_window": 400000, "max_output_tokens": 128000,
        "supports_reasoning": true, "supports_vision": true, ... },
      ...
    ] }
```

Copy `items[].name` verbatim into `llm_settings.model_name` and use `items[].project_id` as `llm_settings.model_project_id`. The shared catalog lives in `project_id=1` (the `promptlib_public` project). Use `scripts/list_models.py` to print a project's catalog.

**To verify your choice actually took effect**, fire a predict and inspect `thinking_steps[].generation_info.model_name` in the response — if it doesn't match what you configured, the runtime fell back. The api-reference dummy examples (`claude-sonnet-4-5`, `claude-opus-4-6`) are **illustrative only**; do not paste them into production payloads without confirming via the models endpoint.

## 12. Direct REST vs MCP — when each one works

ELITEA exposes two surfaces:

| Surface | Read | Write |
|---|---|---|
| **MCP (`mcp__elitea-next__*`)** | ✅ Works for GETs (`getProjectsProject`, `getEliteaCoreApplications`, `getEliteaCoreTools`, `getAuthUser`) | ❌ Most write tools (`postEliteaCoreApplications`, `postEliteaCorePredict`, `postEliteaCoreVersions`, `putEliteaCoreVersion`, etc.) expose only `mode`/`project_id` in their schema with `additionalProperties: false` — they cannot carry a JSON body and 415 immediately. |
| **Direct REST (curl/httpx)** | ✅ | ✅ — required for any operation that needs a body |

> **Rule of thumb:** use MCP tools for reads (cleaner, no auth-host juggling); fall back to direct REST against `next.elitea.ai` (or whichever host your PAT covers — see §1) for any create/update/predict call. The `scripts/build_agent_payload.py` and `scripts/update_version_field.py` helpers exist because of this asymmetry — both pull live state via REST, mutate, and PUT/POST back.

Tangentially: `mcp__elitea-next__getProjectsProject` is mis-described in its schema as "Retrieve a single project" but actually returns **all projects accessible to the caller** when given any valid `project_id` (e.g., your `personal_project_id` from `getAuthUser`). Use that to discover project IDs by name without crawling.

## 13. ELITEA 2.0.3+ changes worth knowing

These shipped with the 2.0.3 release; if you're working on a pre-2.0.3 ELITEA instance some of this won't apply yet.

- **Pipeline entry-point triggers** — pipelines can declare a `chat` (default), `scheduled` (cron), or `webhook` trigger at the entry-point node. **Constraint:** `scheduled` and `webhook` pipelines cannot contain HITL, Printer, or interrupt-requiring nodes. See `elitea-pipeline/references/workflows.md` § "Pipeline entry-point triggers".
- **Native cron** — once a pipeline has a `scheduled` trigger, ELITEA fires it directly; no need for external GH Actions cron + REST shim. The external shim is still recommended when the pipeline has interactive nodes OR you need pre/post logic. See `elitea-testing/references/nudge-case-study.md` § "Scheduling".
- **Sub-agents as standard tools + explicit `task` contract** — sub-agents called as tools no longer inherit the parent's chat history implicitly. The parent must pass everything the child needs via the `task` field. Multi-agent pipelines written pre-2.0.3 may behave differently after upgrade — audit and add explicit task context where needed. See `elitea-toolkit/references/toolkit-types.md` § `application`.
- **Pipeline file attachments as input** — uploaded files are stored in the artifact bucket, and the pipeline receives the file path as an input field. Code nodes retrieve via `alita_client.artifact('bucket').get(path)`.
- **Scoped index creation** — datasource indexers can target a folder within a bucket, not just the whole bucket. Lets one bucket back multiple datasources.
- **ADO project at toolkit level** — for Azure DevOps toolkits, the project is now selected in the toolkit settings (not the credential). One ADO credential can back many toolkits each pointing at a different project. Old toolkits keep working with their existing project-in-credential value until edited.
- **Published-agent per-conversation LLM overrides** — for published agents (in Agent Studio published state), users can override `model_name`, `temperature`, etc. via `entity_settings.llm_settings` on the conversation participant without modifying the agent version. Previously this was rejected with `400 "LLM settings override is only allowed for published agents from agent studio"` for non-published agents — that rule still holds for unpublished agents.
