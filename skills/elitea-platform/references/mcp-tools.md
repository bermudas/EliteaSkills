# ELITEA Built-in MCP Tools — Catalog

Each REST endpoint marked with `mcp_tool=True` in the ELITEA source is auto-exposed as an MCP tool. The MCP layer is a thin wrapper — the input schema mirrors the REST endpoint's query/path/body params.

For each tool: its REST endpoint and the **`mode` + `project_id` defaults that get injected**. Full input schemas live in `api-reference.md` under the corresponding endpoint section.

## Common path params (injected on most tools)

| Param | Type | Default | Notes |
|---|---|---|---|
| `mode` | str | `"prompt_lib"` | Operating mode |
| `project_id` | int | required | Project ID |

## Tool catalog (21 built-ins)

| # | Tool name | Method | REST endpoint | API-ref §  | One-line purpose |
|---|---|---|---|---|---|
| 1 | `getAuthUser` | GET | `/api/v1/auth/me` | — | Get current authenticated user (name, email, personal_project_id, avatar) |
| 2 | `getProjectsProject` | GET | `/api/v1/projects/projects` | — | List projects the user can access |
| 3 | `getEliteaCoreApplication` | GET | `/application/{mode}/{project_id}/{application_id}[/{version_name}]` | §1.1 | Get agent details (incl. version_details) |
| 4 | `putEliteaCoreApplicationAttachmentStorage` | PUT | `/application_attachment_storage/...` | §1 | Attach/detach toolkit from an agent VERSION (artifact storage binding) |
| 5 | `getEliteaCoreApplications` | GET | `/applications/{mode}/{project_id}` | §1 | List agents with filter, sort, pagination |
| 6 | `postEliteaCoreApplications` | POST | `/applications/{mode}/{project_id}` | §1.1 | Create a new agent (with initial `base` version) |
| 7 | `putEliteaCoreAttachmentStorage` | PUT | `/chat/attachment_storage/{mode}/{project_id}/{conversation_id}` | §6 | Set or remove the artifact toolkit on a conversation |
| 8 | `postEliteaCoreAttachments` | POST | `/attachments/{mode}/{project_id}/{conversation_id}` | §8.6 | Upload file attachments to a conversation (multipart) |
| 9 | `getEliteaCoreConversation` | GET | `/conversation/{mode}/{project_id}/{conversation_id}` | §6.2 | Get full conversation detail (participants + first page of messages) |
| 10 | `getEliteaCoreConversations` | GET | `/conversations/{mode}/{project_id}` | §6.1 | List conversations with filter, sort, pagination |
| 11 | `postEliteaCoreConversations` | POST | `/conversations/{mode}/{project_id}` | §6.3 | Create a new conversation |
| 12 | `patchEliteaCoreEntitySettings` | PATCH | `/entity_settings/{mode}/{project_id}/{conversation_id}[/{participant_id}]` | §7.3 | Configure participant settings (LLM override, version pin, variables, chat_history_template) |
| 13 | `getEliteaCoreMessages` | GET | `/messages/{mode}/{project_id}/{conversation_id}` | §8.1 | List message groups in a conversation |
| 14 | `postEliteaCoreMessages` | POST | `/messages/{mode}/{project_id}/{conversation_uuid}` | §8.2 | **Send a message** (uses `conversation_uuid`, not id) and get reply |
| 15 | `deleteEliteaCoreParticipant` | DELETE | `/participant/{mode}/{project_id}/{conversation_id}/{participant_id}` | §7.4 | Remove a participant from a conversation |
| 16 | `postEliteaCoreParticipants` | POST | `/participants/{mode}/{project_id}/{conversation_id}` | §7.2 | Add participants (body is a LIST) |
| 17 | `postEliteaCorePredict` | POST | `/predict/{mode}/{project_id}/{version_id}` | §10.1 | Stateless agent execution with provided inputs |
| 18 | `patchEliteaCoreTool` | PATCH | `/tool/{mode}/{project_id}/{tool_id}` | §3.3, §9.9 | Link/unlink agent ↔ toolkit (sets `selected_tools`) |
| 19 | `getEliteaCoreTools` | GET | `/tools/{mode}/{project_id}` | §9.1 | List project toolkits |
| 20 | `putEliteaCoreVersion` | PUT | `/version/{mode}/{project_id}/{application_id}/{version_id}` | §1.3 | Update an existing agent version (instructions, llm_settings, tools, ...) |
| 21 | `postEliteaCoreVersions` | POST | `/versions/{mode}/{project_id}/{application_id}` | §1.4 | Create a NEW version of an existing agent |

## Tool grouping by capability

### "Browse / introspect"
`getAuthUser`, `getProjectsProject`, `getEliteaCoreApplication`, `getEliteaCoreApplications`, `getEliteaCoreConversation`, `getEliteaCoreConversations`, `getEliteaCoreMessages`, `getEliteaCoreTools`

### "Build agents"
`postEliteaCoreApplications` (create), `postEliteaCoreVersions` (new version), `putEliteaCoreVersion` (update version)

### "Wire toolkits"
`patchEliteaCoreTool` (link/unlink with `selected_tools`), `putEliteaCoreApplicationAttachmentStorage` (attachment toolkit)

### "Run / chat"
`postEliteaCoreConversations`, `postEliteaCoreParticipants`, `patchEliteaCoreEntitySettings`, `postEliteaCoreMessages`, `postEliteaCorePredict`

### "Attachments"
`postEliteaCoreAttachments`, `putEliteaCoreAttachmentStorage`

### "Hygiene"
`deleteEliteaCoreParticipant`

## Common workflows — which tools chain together

### 1. Build + test an agent from scratch

```
postEliteaCoreApplications   → returns id + version_details.id
patchEliteaCoreTool          → link toolkits
postEliteaCoreConversations  → creates a test conversation
postEliteaCoreParticipants   → add the agent
postEliteaCoreMessages       → send a probe (uses conversation_uuid)
getEliteaCoreMessages        → poll for reply
```

### 2. Browse and resume existing conversation

```
getEliteaCoreConversations   → find by query/source
getEliteaCoreConversation    → get full detail incl. participants
postEliteaCoreMessages       → continue chatting
```

### 3. Update agent version in place

```
getEliteaCoreApplication     → fetch current version_details (preserve fields!)
putEliteaCoreVersion         → merge changes back
```

### 4. Stateless single-shot predict

```
getEliteaCoreApplication     → discover version_id
postEliteaCorePredict        → fire predict; get result or task_id
```

## Pulling in additional endpoints

The 21 tools above are the auto-wrapped subset. The full REST API has many more endpoints (publish, fork, regenerate, canvas, folders, etc.) — see `api-reference.md` for everything. To call those from outside, use plain HTTPS (the MCP layer doesn't expose them yet).
