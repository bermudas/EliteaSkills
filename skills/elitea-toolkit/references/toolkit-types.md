# Toolkit Types — Reference

The ELITEA platform supports a fixed set of toolkit types, each with its own `settings` schema. To get the live registry (JSON-schemas), call:

```
GET /api/v2/elitea_core/toolkits/prompt_lib/{project_id}
```

The response's `<type>.properties.selected_tools.args_schemas` keys enumerate the available operations per type.

## Common toolkit types

### `openapi` — Wrap any REST API by OpenAPI spec

Best for: third-party APIs with a spec or that you can describe with one.

```json
{
  "type": "openapi",
  "name": "My Toolkit",
  "settings": {
    "schema": "<inline-YAML-or-JSON-OpenAPI-spec>",
    "credentials_configuration": {
      "elitea_title": "my-api-creds",
      "private": true
    },
    "selected_tools": []
  }
}
```

Details and an example walk-through in `openapi-toolkits.md`. Reference spec: `examples/elitea-api.yaml`.

### `mcp_<flavor>` — Live MCP server

Best for: stdio/SSE MCP servers (`mcp_filesystem`, `mcp_slack`, `mcp_brave`, custom `mcp_*`).

```json
{
  "type": "mcp_filesystem",
  "name": "Local FS MCP",
  "settings": {
    "url": "https://mcp.example.com/sse",
    "ssl_verify": true,
    "selected_tools": []
  }
}
```

After create, sync tools:

```
POST /api/v2/elitea_core/mcp_sync_tools/prompt_lib/{project_id}
body: {"url": "https://mcp.example.com/sse", "toolkit_type": "mcp_filesystem"}
```

If OAuth-protected:
1. `POST /api/v2/elitea_core/mcp_dcr_proxy/default/{project_id}` for RFC 7591 dynamic client registration
2. `POST /api/v2/elitea_core/mcp_oauth_proxy/default/{project_id}` for the token exchange

### `datasource` — Vector RAG over a stored datasource

Best for: company knowledge bases, indexed docs, semantic search.

```json
{
  "type": "datasource",
  "name": "Company KB",
  "settings": {
    "datasource_id": 12345,
    "embedding_model": {
      "name": "text-embedding-ada-002",
      "ai_credentials": {"elitea_title": "azure-openai", "private": true}
    },
    "vectorstore_model": {
      "model_name": "pinecone",
      "model_project_id": 1
    },
    "search_config": {
      "top_k": 5,
      "similarity_threshold": 0.7,
      "search_type": "similarity"
    }
  }
}
```

### `application` — Agent-as-tool

Best for: composing agents (one agent calling another).

```json
{
  "type": "application",
  "name": "Sub-agent: KB Lookup",
  "settings": {
    "variables": [],
    "application_id": 17,
    "application_version_id": 88
  }
}
```

Inside a pipeline, the alternative is the `agent` node — see `elitea-pipeline/references/yaml-schema.md`.

### `custom_python` — In-platform sandbox code

Best for: short transforms, ad-hoc utilities you'd otherwise wrap in an external service.

```json
{
  "type": "custom_python",
  "name": "Text utils",
  "settings": {
    "python_version": "3.11",
    "dependencies": ["regex>=2023.0.0"],
    "tools": [
      {
        "name": "normalize_phone",
        "description": "Strip phone to E.164",
        "code": "def normalize_phone(phone: str) -> str:\n    return phone.replace(' ', '').replace('-', '')",
        "input_schema": {"type": "object", "properties": {"phone": {"type": "string"}}}
      }
    ],
    "execution_timeout": 300,
    "memory_limit_mb": 512
  }
}
```

### `github`, `jira`, `confluence`, `gitlab`, `azure_devops` — First-class integration types

Pre-canned toolkits with built-in operation catalogs. Pass `type: "github"` and only fill credentials + repo/project scope:

```json
{
  "type": "github",
  "name": "GH Toolkit",
  "settings": {
    "github_configuration": {"elitea_title": "my-gh-creds", "private": true},
    "repository": "octocat/Hello-World",
    "active_branch": "main",
    "base_branch": "main",
    "pgvector_configuration": {"elitea_title": "shared-pgvector", "private": false},
    "embedding_model": "text-embedding-ada-002",
    "selected_tools": ["get_files_from_directory", "list_branches_in_repo"]
  }
}
```

Inspect the available operations per type via `GET /toolkit_available_tools/prompt_lib/{project_id}/{toolkit_id}` after create.

### `artifact` — Project artifact storage (for chat attachments)

Best for: persistent chat attachments / agent memory storage.

```json
{
  "type": "artifact",
  "name": "Email attachments",
  "settings": {
    "bucket": "emailattachments",
    "pgvector_configuration": {"elitea_title": "shared-pgvector", "private": false},
    "embedding_model": "text-embedding-ada-002",
    "selected_tools": []
  }
}
```

Set as the conversation's attachment toolkit via `PUT /chat/attachment_storage/...` or as the agent's via `PUT /application_attachment_storage/...`.

## Picking the right type

| You have… | Use type |
|---|---|
| An OpenAPI spec or a REST API to wrap | `openapi` |
| A running MCP server (URL) | `mcp_<flavor>` |
| Indexed docs / vector store | `datasource` |
| Another agent in this project | `application` (or `agent` node in a pipeline) |
| Short Python utility | `custom_python` |
| GitHub / Jira / Confluence access | first-class type (`github`, `jira`, ...) |
| Project bucket for files | `artifact` |

## Linking a toolkit to an agent

After creation, attach a toolkit to an agent VERSION via PATCH:

```
PATCH /api/v2/elitea_core/tool/prompt_lib/{project_id}/{toolkit_id}
body: {
  "entity_id": <agent_id>,
  "entity_version_id": <version_id>,
  "entity_type": "agent",
  "has_relation": true,
  "selected_tools": ["operation_name_1", "operation_name_2"]
}
```

- `selected_tools` **filters** which operations are exposed to the agent. Pass `null`/omit to expose everything the toolkit defines.
- To unlink: same call with `has_relation: false`.

## Gotchas

- **Credential references use `elitea_title` and `private`, NOT raw ids.** The same value can appear in many toolkits.
- **Sensitive fields come back as `"{{secret.NAME}}"`** placeholders on subsequent GETs. Resolve via the secrets endpoint (see `elitea-platform/references/conventions.md` § 5).
- **`toolkit_name`** in responses is the sanitized form of `name` (server strips chars outside `[a-zA-Z0-9_.-]`, then replaces `.` → `_`).
- **MCP toolkits' `online` field is `null` until sync succeeds.** Run `mcp_sync_tools` immediately after create.
- **Test before linking** via `POST /test_toolkit_tool/...` — see `elitea-testing/SKILL.md`.
