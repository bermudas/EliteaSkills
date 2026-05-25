# ELITEA Conventions — Quick Reference

The 90% of the platform you'll touch every day. For full endpoint details load `api-reference.md`.

## 1. Base URLs & API versioning

| Environment | Base URL |
|---|---|
| Production | `https://nexus.elitea.ai/` |
| Pre-prod / "next" | `https://next.elitea.ai/` |

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
