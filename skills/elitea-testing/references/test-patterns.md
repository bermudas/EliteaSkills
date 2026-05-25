# ELITEA Testing — Patterns Reference

Patterns mined from the `elitea-api-testing` pytest suite and from real production debugging. Each pattern has a goal, the minimum REST sequence, and the gotchas.

## 1. Predict — stateless agent run

**Goal:** Fire one prediction against a deployed agent version. No conversation persistence.

**Endpoint:** `POST /api/v2/elitea_core/predict/prompt_lib/{project_id}/{version_id}`

### Sync (block until complete)
```bash
curl -X POST -H "Authorization: Bearer $ELITEA_TOKEN" -H "Content-Type: application/json" \
  -d '{"user_input": "Hello", "chat_history": []}' \
  "https://next.elitea.ai/api/v2/elitea_core/predict/prompt_lib/630/153"
# → {"result": "...", "task_id": "...", "error": null}
```

### Async (fire-and-poll)
```bash
# Fire — returns immediately with task_id
curl -X POST "...?async=yes" -d '{"user_input": "Long task"}'
# → {"task_id": "abc123", "result": null}

# Poll
curl "https://next.elitea.ai/api/v2/elitea_core/application_task/prompt_lib/630/abc123?result=yes"
# → {"status": "SUCCESS", "result": "..."}  | "PENDING" | "FAILURE"
```

### Async with callback (no polling needed)
```json
{
  "user_input": "Generate report",
  "async": "yes",
  "callback_url": "https://my-service.com/webhook",
  "callback_headers": {"Authorization": "Bearer my-token"}
}
```
Platform POSTs result to your `callback_url` when done.

**Gotchas:**
- `chat_history` is REQUIRED to be at least `[]` (empty array). Some clients send `null` and get 400.
- `llm_settings` in the body **overrides** the version's baseline for this run only.
- `variables` in the body **replaces** the version's variables for this run.

## 2. Conversation flow — full multi-turn lifecycle

**Goal:** Reproduce or test a real user scenario where the agent maintains state across messages.

```
1. POST /conversations/...    body: {name, is_private, participants:[]}
   → save {id, uuid}

2. POST /participants/{conv_id}    body: [{entity_name, entity_meta, entity_settings}]
   → save response[0].id as participant_id

3. POST /messages/{conv_UUID}    body: {participant_id, user_input, await_task_timeout}
   → 201 with message_groups OR 202 streaming OR 200 with task_id

4. (Optional) GET /messages/{conv_id}?limit=N    to fetch latest groups
```

### Minimal Python end-to-end

```python
import httpx, os
HEADERS = {"Authorization": f"Bearer {os.environ['ELITEA_TOKEN']}", "Content-Type": "application/json"}
BASE = "https://next.elitea.ai/api/v2/elitea_core"
PROJECT, AGENT, VER = 630, 101, 153

with httpx.Client(headers=HEADERS, timeout=120) as c:
    # 1. Create conversation
    conv = c.post(f"{BASE}/conversations/prompt_lib/{PROJECT}",
                  json={"name": "Smoke test", "is_private": True, "participants": []}).json()
    cid, uuid = conv["id"], conv["uuid"]

    # 2. Add agent participant
    parts = c.post(f"{BASE}/participants/prompt_lib/{PROJECT}/{cid}",
                   json=[{"entity_name": "application",
                          "entity_meta": {"id": AGENT, "project_id": PROJECT},
                          "entity_settings": {"version_id": VER}}]).json()
    pid = parts[0]["id"]

    # 3. Send first message (use UUID, not id!)
    r = c.post(f"{BASE}/messages/prompt_lib/{PROJECT}/{uuid}",
               json={"participant_id": pid, "user_input": "Hello", "await_task_timeout": 60})
    print(r.status_code, r.json())

    # 4. Send a follow-up
    r2 = c.post(f"{BASE}/messages/prompt_lib/{PROJECT}/{uuid}",
                json={"participant_id": pid, "user_input": "Tell me more", "await_task_timeout": 60})
    print(r2.status_code, r2.json())
```

**Gotchas:**
- `POST /messages/...` uses the conversation **UUID** in the URL, not the integer id. Everywhere else uses id.
- Body of `POST /participants/...` is a JSON **list**, even for one participant. Response is also a list — use `response[0]`.
- For long-running predicts, set `await_task_timeout: -1` and pair with `return_task_id: true` to fire-and-forget.

## 3. Send-and-poll — long-running predicts

Sometimes the agent takes minutes to reply (multi-step tool calls, large LLM jobs). Don't block the HTTP request:

```python
# 1. Fire with return_task_id
r = c.post(f"{BASE}/messages/prompt_lib/{PROJECT}/{uuid}",
           json={"participant_id": pid, "user_input": "...",
                 "await_task_timeout": -1, "return_task_id": True}).json()
# → {"task_id": "..."} or {"message_groups": [...]} with last group streaming

# 2. Poll messages list
while True:
    msgs = c.get(f"{BASE}/messages/prompt_lib/{PROJECT}/{cid}", params={"limit": 1, "sort_order": "desc"}).json()
    last = msgs["rows"][0]
    if not last["is_streaming"] and last["message_items"]:
        print("Done:", last["message_items"][0]["item_details"]["content"])
        break
    time.sleep(5)
```

**Gotchas:**
- `return_task_id=True` AND `await_task_timeout > 0` are **mutex** — pick one mode.
- `await_task_timeout=-1` means "no wait, return immediately" — pair with `return_task_id=True`.
- `await_task_timeout=0` is the same as -1 in practice (returns immediately).

## 4. Outcome classification

Reading conversation state to decide if a turn worked, hung, or errored.

```python
def classify_last_group(detail, user_pids, hung_minutes=10, user_timeout_minutes=15):
    """Inspect a conversation's last message group and return one of:
       errored / active / pending / completed / empty.
    """
    from datetime import datetime, timezone
    groups = sorted(detail.get('message_groups') or [],
                    key=lambda g: g.get('created_at') or '')
    if not groups:
        return 'empty'
    last = groups[-1]
    is_user = last['author_participant_id'] in user_pids
    streaming = last.get('is_streaming', False)
    items = last.get('message_items') or []

    # Pattern A: assistant streaming with no items
    if not is_user and streaming and not items and last.get('task_id'):
        age = (datetime.now(timezone.utc) -
               datetime.fromisoformat(last['created_at'].replace('Z',''))).total_seconds() / 60
        return 'errored' if age >= hung_minutes else 'active'

    # Pattern B: explicit error string in assistant reply
    if not is_user and items:
        text = ''.join(it['item_details'].get('content','') for it in items
                       if it.get('item_type') == 'text_message')
        if any(s in text for s in ['An unexpected error', 'Traceback', 'ConnectionError', 'RateLimitError']):
            return 'errored'

    # Pattern C: last group is user — pending or timed out
    if is_user:
        age = (datetime.now(timezone.utc) -
               datetime.fromisoformat(last['created_at'].replace('Z',''))).total_seconds() / 60
        return 'errored' if age >= user_timeout_minutes else 'pending'

    return 'completed'
```

Full version with all edge cases is in `eliteapipelines/ConversationHealthAnalyzer.yaml` (now under `elitea-pipeline/examples/`).

## 5. Direct tool invocation testing

Before linking a toolkit to an agent, smoke-test one operation:

```bash
curl -X POST -H "Authorization: Bearer $ELITEA_TOKEN" -H "Content-Type: application/json" \
  -d '{
    "project_id": 630,
    "toolkit_config": {... full settings dict ...},
    "tool_name": "list_branches_in_repo",
    "tool_params": {"repository": "octocat/Hello-World"},
    "llm_model": "gpt-5"
  }' \
  "https://next.elitea.ai/api/v2/elitea_core/test_toolkit_tool/prompt_lib/630?await_response=true&timeout=60"
```

Returns `{result: ...}` on success or `{error: ...}` on failure.

## 6. Integration test patterns (from `elitea-api-testing`)

The pytest suite uses these helpers:

### `post_conversation(project_id, name, participants=[])`
Just `POST /conversations/...`. Returns `{id, uuid}`.

### `post_participant(project_id, conv_id, list_of_participants)`
Wraps the list-body requirement. Always returns `response[0]`.

### `post_message(project_id, conv_uuid, payload)`
Always sets `await_task_timeout=30` if caller didn't.

### `update_entity_settings(project_id, conv_id, participant_id, body)`
Full-replace PUT — caller responsible for including all fields they want to keep.

### `wait_for_configuration_status_ok(config_id, max_tries=5, delay=3)`
Polls `GET /configuration/{id}` until `status_ok: true`. AI/embedding configs sometimes need a few seconds.

### Common fixtures

| Fixture | Value |
|---|---|
| `TEST_GITHUB_REPOSITORY` | `octocat/Hello-World` |
| `TEST_EMBEDDING_MODEL_NAME` | `text-embedding-ada-002` |
| `TEST_CHAT_MODEL_NAME` | `gpt-5` |
| `TEST_AZURE_OPENAI_API_VERSION` | `2024-02-01` |
| `bucket.expiration_value` | 30 days (workaround for a backend bug with non-null `data_retention_limit`) |
| `await_task_timeout` default in `post_message` | 30 seconds |

## 7. Common gotchas (cheat sheet)

| Gotcha | Detail |
|---|---|
| `Content-Type: application/json` on GET | Drop it. Use `Accept: application/json`. Some proxies 400 with it. |
| Empty `chat_history` | Send `[]`, not `null`. |
| Wrong `participant_id` | Use the integer `id` from `POST /participants/...` response, NOT the agent's `application_id`. |
| URL with `id` instead of `uuid` for `POST /messages/` | Get 400 `"...does not exist..."`. |
| Bare `await_task_timeout` < -1 | 400 validation error. |
| `meta.step_limit` not set | Defaults to 25; bump for long agentic chains. |
| First version name not `"base"` | Create fails with 400. |
| Subsequent version named `"base"` | Create fails with 400. |
| Sending `Content-Type` on GET via Pyodide httpx in a pipeline | Got us a 400. Don't. |
| `entity_settings.llm_settings` override on non-published agent | Gets stripped; if it doesn't match version baseline → 400. |

## 8. End-to-end debugging checklist

When a pipeline / agent isn't behaving:

1. **Check the calling user has access to the project** — `getAuthUser` then `getProjectsProject` should include the target.
2. **Confirm the version_id is current** — `getEliteaCoreApplication` and verify `version_details.id`.
3. **Look at the last few message groups** — `GET /messages/?limit=5&sort_order=desc`. Check `is_streaming`, `task_id`, `meta.tool_calls[*].finish_reason`.
4. **For pipelines, look at the structured `result` block in predict** — `chat_history[-1].content` often contains a wrapped JSON with diagnostics.
5. **Test the failing operation in isolation** via `test_toolkit_tool` if it's a tool issue.
6. **Compare model output to baseline** via `/predict_llm/` (no agent, just LLM).
