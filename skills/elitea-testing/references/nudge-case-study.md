# Case Study — Conversation Health Analyzer

End-to-end walkthrough of building, testing, and operationalizing the `ConversationHealthAnalyzer` pipeline. The numbers below (project IDs, agent IDs, conv IDs) come from a real deploy across two ELITEA projects, scheduled via GitHub Actions every 15 minutes. Treat them as illustrative — your IDs will differ.

> **Why this exists:** demonstrate the full BUILD → DEPLOY → TEST → SCHEDULE loop using a real, non-toy problem (auto-recovery of stuck Teams conversations). Every choice in the pipeline YAML and workflow file traces back to a concrete bug or trade-off discovered during construction.

The full source files:
- Pipeline YAML: `elitea-pipeline/examples/ConversationHealthAnalyzer.yaml`
- GH Actions workflow: `<your-ops-repo>/.github/workflows/nudge-failed-conversations.yaml` (kept in a separate ops repo so the workflow secret is scoped there)

---

## 1. The problem

**A project (let's call it `<source_project>`, id 630 in the original deploy)** runs a `Teams:*` support bot — users DM it via Microsoft Teams, the bot replies via `ReplyTeamsMessage`. Two failure modes were observed in real traffic:

1. **Hung predicts** — assistant message group stuck with `is_streaming=True`, `items=0`, never completes. The user is waiting in Teams forever.
2. **Explicit errors** — the agent's last reply is literally `"An unexpected error occurred while processing your request"`. The user sees a non-answer.

**Goal:** detect these on a cadence, send the agent a re-try nudge that says "apologize and re-answer the original question via Teams", and not spam-nudge stuck conversations.

## 2. Build — pipeline architecture

Three nodes, no LLM cost on the main path:

```
[FetchAndClassify] (code)
   ↓
[Display] (printer) → END
```

Yes, just two nodes. The earlier design had an LLM `Insights` node — we dropped it after the deterministic classifier matched all known ground-truth cases.

### `FetchAndClassify` — what it actually does

Three sequential passes, each tuned for cost:

| Pass | API | Why |
|---|---|---|
| **1** | `GET /conversations/.../{project_id}` (paginated) | Cheap list. Filter by `updated_at` so we catch recently-active old convs. `meta.context_analytics` comes in this response — `context_pressure` is free. |
| **2** | `GET /messages/.../{conv_id}?limit=2&sort_order=desc` (per conv, parallel × 30) | Lightweight. ~500KB vs 1.5MB for full `/conversation/...`. Has full `meta.tool_calls` on the last 2 groups. Enough to classify status. |
| **3** | `GET /conversation/.../{conv_id}` (per non-completed conv, parallel × 30) | Heavyweight, but only for the ~5% that are errored/pending. Gets participants + full history (needed for agent_id and the idempotency check). |

Net result: 30-day scan over 300 conversations runs in ~100s with the deterministic classifier producing a ranked table.

### Auth from inside the pipeline

The pipeline runs on the platform; auth comes for free:

```python
headers = {
    'Authorization': f'Bearer {elitea_client.auth_token}',
    'Accept': 'application/json',
}
base_url = elitea_client.base_url.rstrip('/')
```

We DO NOT read `.env` from inside the pipeline. `elitea_client.auth_token` is the calling user's PAT, injected by the runtime.

### Classifier rules

Last-group inspection, in order:

```python
# Pattern A: streaming-but-empty assistant group
if assistant_streaming and items==0 and task_id:
    age = now - last.created_at
    return 'errored: hung' if age >= ASSISTANT_HUNG_MINUTES else 'active'

# Pattern B: explicit error string in last assistant text
if assistant and ERROR_RE.search(last_text):
    return 'errored: explicit error'

# Pattern C: last group is user
if user_last:
    age = now - last.created_at
    return 'errored: timeout' if age >= USER_TIMEOUT_MINUTES else 'pending'

# Otherwise
return 'completed'
```

Two tunable thresholds (`ASSISTANT_HUNG_MINUTES=10`, `USER_TIMEOUT_MINUTES=15`).

### The bug we hit on first run: false-positive "hung"

First version of the classifier omitted the age check. We nudged User E's conversation **while it was actively answering** — the predict had been streaming for 81 seconds and was on tool-call 13 of an upcoming successful reply.

**Fix:** require `age >= ASSISTANT_HUNG_MINUTES` before classifying as hung. A streaming group < 10 min old is `active`, not `errored`.

### Idempotency — the marker pattern

Every nudge body starts with the literal string `[Pipeline retry — operator-triggered]`. On subsequent runs, the classifier checks if the marker exists **after the most recent real user message** (not anywhere in history):

```python
def already_nudged_for_current_failure(detail):
    groups = sort_chronological(detail.message_groups)
    last_real_user_idx = last index of group authored by user-pid that's NOT a nudge
    if last_real_user_idx < 0:
        return any nudge marker anywhere   # fallback
    return any nudge marker in groups[last_real_user_idx + 1:]
```

**Why scoped to "after last real user message":** a conv nudged 3 weeks ago, then 50 successful turns, then a fresh failure today — must be eligible for a new nudge. A global-history check would block it forever.

Verified with four unit-test scenarios (see `references/test-patterns.md` § 4 for the classifier; idempotency test is at the end of the pipeline YAML's code node).

### The nudge body

Operator-friendly, structured, with all the routing info the agent needs:

```
[Pipeline retry — operator-triggered]

Your previous reply in this conversation failed: `<reason>`.

**Please do the following, in order:**
1. Use `ReplyTeamsMessage` (with the Teams routing instructions below) to send a brief apology...
2. Then process the user's most recent question (below)...

---

**User's latest question (the one you must answer):**
<cleaned text>

**Teams routing (use these instructions for `ReplyTeamsMessage`):**
<ReplyInstructions>...verbatim from the original user message...</ReplyInstructions>

**Recent conversation history (for context, useful after compaction):**
- `2026-05-22 12:23:05` **User A**: ...
- ...
```

Key choices:
- **Preserve `<ReplyInstructions>` verbatim.** This block contains the Teams conversation ID (`19:abc@unq.gbl.spaces`) the agent needs for `ReplyTeamsMessage`. Stripping it forces the agent to hunt history (which sometimes works, sometimes doesn't).
- **Parse `<ChatHistory>` into clean per-line bullets** instead of dumping the raw `\n`-escaped blob. Each line: `timestamp · who · text` (max 400 chars).
- **Cap history to last 12 lines** so nudges don't grow unbounded on long convs.
- **Marker is the first line of the body** — easy to grep for idempotency.

## 3. Deploy — two projects

Both projects (`<source_project>` and `<companion_project>`) get their own copy of the same pipeline:

```
<source_project>     → agent_id=<A1> / version_id=<V1>
<companion_project>  → agent_id=<A2> / version_id=<V2>
```

The pipeline YAML accepts `project=NNN` in `user_input` so one canonical YAML works for any project. Each deployment passes `project=<its-own-id>` from the workflow so it scans the correct project.

Deployment command (per project):

```bash
curl -X POST -H "Authorization: Bearer $ELITEA_TOKEN" -H "Content-Type: application/json" \
  -d @create_payload.json \
  "https://next.elitea.ai/api/v2/elitea_core/applications/prompt_lib/$PROJECT_ID"
```

The `create_payload.json` body shape is `{name, description, type, versions: [{name:"base", agent_type:"pipeline", instructions:<YAML>, llm_settings, ...}]}` — see `elitea-platform/references/api-reference.md` § 1.1 for the full schema.

For updates: `PUT /api/v2/elitea_core/version/.../{ver_id}` (preserve fields by GET-first; see `scripts/update_agent.py`).

## 4. Test — validating each piece

### Stage 1: validate against three known cases

Three real conversations from the source project with known status:
- conv #conv-good (User F) — **completed** (good)
- conv #conv-hung (User C) — **errored: hung**
- conv #conv-err  (User B) — **errored: explicit error**

After deploy, ran the pipeline in dry-run mode over a 30-day window and grepped each conv's classification in the output. All three matched expectations.

### Stage 2: validate idempotency with synthetic scenarios

Built 4 fake `detail` dicts in Python (no API call needed) and ran the `already_nudged_for_current_failure` function:

| Scenario | Expected | Got |
|---|---|---|
| Fresh failure, no prior nudge | NUDGE | ✓ NUDGE |
| Just nudged, same question still failing | SKIP | ✓ SKIP |
| Old nudge weeks ago → recovered → new question fails today | NUDGE | ✓ NUDGE |
| Never nudged, fresh error | NUDGE | ✓ NUDGE |

### Stage 3: apply on the first real nudge — User A

Ran `7 days apply` mode → 1 errored conv → nudge sent → 90s later the agent had completed the retry, apologized in Teams, and answered the original `.create(...)` question. Verified by inspecting the nudge group (posted as the operator) and the immediately-following assistant recovery group.

### Stage 4: apply on a batch of 4

Ran `30 days apply` → 4 errored convs (User A, User C, User B, User D + bonus User E false-positive that exposed the hung-threshold bug). Three completed within minutes; one (User C) was the historically-flakiest conv and slowly recovered.

### Stage 5: false-positive discovery → fix

User E's conv was streaming for 81s when scanned and was classified as "hung". Added `ASSISTANT_HUNG_MINUTES=10` threshold; verified subsequent dry-runs no longer flag active-but-young predicts.

## 5. Schedule — GitHub Actions every 15 min

> **2.0.3+ alternative — native pipeline cron.** As of ELITEA 2.0.3 the pipeline itself can declare a `scheduled` trigger at its entry-point node, and ELITEA fires it directly with no external scheduler. For the `ConversationHealthAnalyzer` pipeline specifically (no Printer, no HITL, no interrupts), this is the cleaner choice — fewer moving parts, no GH-Actions billing risk, no PAT-secret rotation.
>
> Keep the GH-Actions path described in this section when:
> - The pipeline contains any interactive node (Printer / HITL / interrupt) — cron + interactive is forbidden, you MUST stick with `chat` trigger and external scheduler
> - You need pre/post logic outside the pipeline (e.g. fan-out to multiple projects via a matrix, persistence of artifacts to GH, alerting via PRs/issues)
> - The native cron path hasn't been verified end-to-end for your scenario yet — keep the GH-Actions cron as the durable fallback and switch over once both have been observed to behave the same way over a week
>
> See `elitea-pipeline/references/workflows.md` § "Pipeline entry-point triggers" for the trigger types and constraints.

### Classic GH-Actions cron (the pattern that's been running all year)

`<your-ops-repo>/.github/workflows/nudge-failed-conversations.yaml`:

```yaml
on:
  schedule:
    # Offset off the top-of-hour to avoid GitHub's scheduled-workflow stampede
    # (which silently drops :00/:15/:30/:45 ticks under load).
    - cron: '7,22,37,52 * * * *'
  workflow_dispatch:
    inputs:
      days: { default: '1', type: string }
      dry_run: { default: false, type: boolean }

concurrency:
  group: nudge-failed-conversations
  cancel-in-progress: false       # slow runs don't pile up but aren't killed

jobs:
  scan-and-nudge:
    timeout-minutes: 8
    strategy:
      fail-fast: false             # companion project keeps running even if source fails
      matrix:
        include:
          - { project_id: <source_id>,    agent_id: <A1>, version_id: <V1> }
          - { project_id: <companion_id>, agent_id: <A2>, version_id: <V2> }
    steps:
      - name: Invoke pipeline
        env:
          ELITEA_TOKEN: ${{ secrets.ELITEA_NEXT_API_KEY }}
        run: |
          curl -X POST "https://next.elitea.ai/api/v2/elitea_core/predict/prompt_lib/${PROJECT_ID}/${VERSION_ID}" \
            -H "Authorization: Bearer ${ELITEA_TOKEN}" \
            -H "Content-Type: application/json" \
            -d '{"user_input":"1 day apply project='${PROJECT_ID}'","chat_history":[]}'
```

Operational notes:

- **Cron offset (`7,22,37,52`)** — GitHub silently drops scheduled workflow ticks at the top of the hour under load. Offsetting reduces the miss rate.
- **`cancel-in-progress: false`** — a slow scan should finish, not be replaced mid-run.
- **`fail-fast: false`** — one project's outage doesn't block the other.
- **`timeout-minutes: 8`** — covers the worst 30-day scan we've seen (4 min), with margin.
- **Idempotency lives in the pipeline, NOT the scheduler.** Trust the pipeline's marker check; the scheduler is dumb on purpose.
- **GH secret name is `ELITEA_NEXT_API_KEY`** (matches the other workflows in that repo); this is the same PAT you'd put in local `.env` as `ELITEA_TOKEN`.

## 6. Operational outcomes

Over the first 30 days post-deploy:
- 18 errored Teams convs in window → 16 unique (2 dedup'd)
- 4 successfully nudged + recovered on the first batch (User A, User B, User D, User E)
- 0 runaway loops (idempotency held)
- 1 bug found and fixed (hung-vs-active threshold)
- 11 of 18 errored convs were all from the same `2026-04-30T08:38:50` minute — clearly a single platform incident, not 11 separate bugs. The dashboard flagged this as a cluster.

## 7. Lessons learned

1. **Move classification into code, not LLM.** Original design used an LLM to write the summary. With 300 conversations the LLM input was 930K tokens — too much. Deterministic classifier + minimal LLM call (just for the executive summary, then dropped entirely) is faster, cheaper, and reproducible.
2. **Validate against known cases BEFORE going live.** The three-cases-from-real-history check caught classifier bugs that a unit-test suite of synthetic data would have missed.
3. **Make idempotency local to the conversation.** Don't trust the scheduler; make the action self-protecting.
4. **Preserve provider-specific routing data verbatim.** `<ReplyInstructions>` looked like noise but contained the Teams routing the agent needed. Don't strip what you don't fully understand.
5. **Active ≠ hung.** Time-since-streaming-started is a critical signal. Always require an age threshold for "stuck" classifications.
6. **One canonical pipeline + parameterized inputs > N copies.** The `project=NNN` parser meant we ship one YAML to git and deploy it identically to multiple ELITEA projects.
7. **`finish_reason: stop` ≠ delivered.** ReplyTeamsMessage wraps a Power Automate workflow that POSTs to Microsoft Graph. The tool returns `finish_reason: stop` whenever Power Automate replies — even when Graph rejected the message (e.g. body uses HTML tags Teams forbids: `<h1>-<h6>`, complex code blocks, `<table>`). Truth lives in `tool_output`: `"ok":true / "Teams reply was sent"` (delivered) vs `Tool execution error! ... Power Automate workflow ... error` (not delivered). The CHA pipeline now inspects `tool_output` and classifies multi-call delivery with a **last-call rule**: if the LAST ReplyTeamsMessage call succeeded, the user has the agent's final intent → `delivered_last_ok` (completed). If the LAST failed → `last_failed` (re-nudge). Earlier failures in the middle don't matter if the final retry landed.
8. **The list endpoint's `updated_at` lies.** When the underlying predict crashes pre-task-id (e.g. ELITEA 0.416's `validate_and_resolve_llm_settings` regression), the conversation gets a new hung message group but its list-level `updated_at` doesn't advance. A 1-day window then silently misses the conv. Fix: Pass 1 always uses a wider buffer (`max(DAYS_BACK, 7)` days), then Pass 2 re-filters convs by their **actual last message-group timestamp**. The report tells you how many got dropped: `dropped=N convs whose actual last message was older than effective cutoff`.
9. **Corrupted-response detection.** When the agent's predict path hits an auth/redirect failure, the response sometimes contains the ELITEA UI's HTML landing page (`Error: <!DOCTYPE html>...alita_ui_config...sourceMappingURL=...`) instead of an assistant reply. Without a specific detector this slips through as `completed` because it has text content and no streaming flag. Add a regex matching `Error:\s*<!DOCTYPE | alita_ui_config | sourceMappingURL=` to the classifier.
10. **Nudges look like user messages.** When the cron POSTs a nudge to `/messages/`, ELITEA records it with the operator's user-participant id (not 6, not 19 — usually a separate pid like 77). Any helper that finds "the latest user message" must filter out nudge groups (`_is_nudge_group(g)`) or it will return the previous nudge's marker text as the "latest user question" — and the next nudge will ask the agent to "answer" our own prior nudge. Both `extract_last_user_message` and `already_nudged_for_current_failure` need this filter.
11. **ChatHistory blocks are multi-line.** The Teams integration embeds a `<ChatHistory>...</ChatHistory>` block in each user message. Each turn starts with a header line `TS | speaker | first-line-of-text` and may continue across many physical lines until the next header. Parsing line-by-line with `re.match(header_pattern, line)` only captures HEADER lines and drops the continuation. The agent then sees nudge context that's just "first line of each turn" — long agent replies with tables/code snippets get truncated to a one-liner. Accumulate continuation lines into the current turn's text until the next header.
12. **Pattern E (generic catch-all for Teams convs).** Beyond specific known failure modes (hung, explicit error, corrupted), the most useful single rule is: *for any Teams conv, the LAST assistant turn MUST have a successful ReplyTeamsMessage delivery, or the user got nothing*. Subsumes ghost-teams-reply (text claims delivered but no tool call), scratchpad-only (reasoning never followed by send), forgot-the-tool, tool-failed. Apply a 15-minute grace period before flagging — fresh responses may still be settling meta.tool_calls writes.
13. **MAX_NUDGE_ATTEMPTS cap.** When a nudge's response is itself broken (the agent hung again, or returned corrupted HTML), `_nudge_response_is_real` correctly says "not delivered" and we re-nudge. Without a cap this loops forever during prolonged platform outages. Cap at 3 attempts per failure window — beyond that, flag for human review.

## 8. Where to look next

- **Per-turn outcome tracking** (not just last-turn) — useful for "agent quality" dashboards. Currently the classifier looks at the last group only; a richer pipeline could track success rate per user-AI turn across the conversation lifetime.
- **Cross-conversation alerting** — when N errored convs share the same `updated_at` minute, surface as an incident rather than N individual nudges. We saw this pattern at `2026-04-30T08:38:50` but only by eye.
- **Nudge retry tracking** — currently one nudge per failure; if the nudge itself fails, the conv is parked in "skipped, needs human attention". Could add a second-attempt heuristic with backoff.
