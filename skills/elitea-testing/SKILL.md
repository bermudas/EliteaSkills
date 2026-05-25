---
name: elitea-testing
description: Test, run, debug, and schedule ELITEA agents and pipelines. Covers the predict endpoint (sync, async, callback), conversation+participant+message flow, send-and-poll for long-running predicts, classification of failure modes from conversation state (hung predicts, explicit errors, user-timeout), idempotency guards, and scheduling via GitHub Actions cron. Includes a full case study (`references/nudge-case-study.md`) walking through how `ConversationHealthAnalyzer` was built, debugged, deployed to two projects, and scheduled. Also bundles `scripts/update_agent.py` for pushing local instruction files to a deployed agent. Use this skill whenever the user wants to run, predict, test, debug, or schedule an ELITEA artifact.
---

# ELITEA Testing — Run, Debug, Schedule

ELITEA artifacts (agents, pipelines, toolkits) are tested by **calling the same REST API users hit at runtime**. There is no separate test harness — production endpoints serve test traffic, and you observe outcomes via the conversation/message endpoints.

## Quick lookup

| If you need... | Load |
|---|---|
| How to fire a single prediction (sync, async, callback) | `references/test-patterns.md` § "Predict" |
| Conversation → participant → message → poll lifecycle | `references/test-patterns.md` § "Conversation flow" |
| How to classify conversation outcomes (errored / completed / active / pending) | `references/test-patterns.md` § "Outcome classification" |
| Patterns mined from ELITEA's pytest integration suite | `references/test-patterns.md` § "Integration test patterns" |
| Real worked example: build → debug → deploy → schedule | `references/nudge-case-study.md` |
| Push a local instruction `.md` to an existing agent | `scripts/update_agent.py` (see end of this file) |
| Schedule recurring runs (GitHub Actions cron) | `references/nudge-case-study.md` § "Scheduling via GH Actions" |

## Core capabilities & when to use each

| Capability | Endpoint | When |
|---|---|---|
| **Stateless predict** | `POST /api/v2/elitea_core/predict/prompt_lib/{project_id}/{version_id}` | One-shot agent run; webhook handlers; testing a version without persisting a conversation; CI smoke tests |
| **Conversational predict** | `POST /api/v2/elitea_core/conversations/...` → `/participants/...` → `/messages/...` | Multi-turn conversations; testing chat flows; reproducing user scenarios |
| **Direct LLM predict** | `POST /api/v2/elitea_core/predict_llm/prompt_lib/{project_id}` | Compare raw LLM output against agent output; bypass tool selection logic |
| **Test a single toolkit operation** | `POST /api/v2/elitea_core/test_toolkit_tool/prompt_lib/{project_id}` | Validate a toolkit operation BEFORE linking it to an agent |
| **Async with callback** | Same predict endpoints with `callback_url` in body | Long-running predicts; integrating with external systems that have their own webhook receivers |

## Outcome classification — pattern reference

The deterministic classifier we use in `ConversationHealthAnalyzer` (see `references/nudge-case-study.md`) reads only the **last message group** of a conversation:

| Last-group shape | Status |
|---|---|
| `is_streaming=True, items=0, task_id≠null` AND age ≥ 10 min | `errored: hung` |
| `is_streaming=True, items=0, task_id≠null` AND age < 10 min | `active` (legitimate in-flight predict) |
| Last assistant text contains `An unexpected error\|Traceback\|ConnectionError\|RateLimitError\|...` | `errored: explicit error` |
| Last group is from a user, age ≥ 15 min, no assistant reply | `errored: timeout` |
| Last group is from a user, age < 15 min | `pending` |
| Last group is an assistant message with real content | `completed` |

The two thresholds (`ASSISTANT_HUNG_MINUTES=10`, `USER_TIMEOUT_MINUTES=15`) are tunable in the pipeline YAML.

## Idempotency for auto-triggered actions

When running on a schedule (cron) and taking real actions (e.g., sending a nudge), guard against runaway loops:

1. **Embed a stable marker** in every action you POST (we use the literal string `[Pipeline retry — operator-triggered]`).
2. **Scope the check to "since the last real user message"** — NOT "anywhere in history". Otherwise a single old nudge blocks the conversation from ever being nudged again, even after weeks of successful turns. Find the chronologically-latest user message that is NOT a marker-containing message; if any marker exists after it, skip.

Full implementation in `ConversationHealthAnalyzer.yaml` → `already_nudged_for_current_failure()`. Walkthrough in `references/nudge-case-study.md`.

## Test-locally workflow

```bash
# 1. Set up auth (one-time)
cp .env.example .env
# edit .env to paste your PAT into ELITEA_TOKEN

# 2. Stateless predict against a deployed agent version
curl -X POST -H "Authorization: Bearer $ELITEA_TOKEN" -H "Content-Type: application/json" \
  -d '{"user_input": "test"}' \
  "https://next.elitea.ai/api/v2/elitea_core/predict/prompt_lib/$PROJECT_ID/$VERSION_ID"
```

For multi-turn or stateful tests, follow the **conversation flow** in `references/test-patterns.md`.

## `scripts/update_agent.py`

Pushes a local Markdown instruction file (e.g., `my_instr/foo.md`) to an existing ELITEA agent via the REST API. Always does a **GET first** to preserve `llm_settings`, `tools`, `tags`, then a **dry-run diff** before any `PUT`.

```bash
# Dry-run (default — no --apply)
python3 .claude/skills/elitea-testing/scripts/update_agent.py path/to/instruction.md

# Apply after review
python3 .claude/skills/elitea-testing/scripts/update_agent.py path/to/instruction.md --apply

# Update other fields too
python3 .claude/skills/elitea-testing/scripts/update_agent.py path/to/instruction.md \
  --set description="..." --set welcome_message="..." --apply
```

The `.md` file's header lines specify the target:

```
Agent ID: 79
Version ID: 79
Project ID: 29
URL: https://next.elitea.ai/

# Instruction body starts here
```

Auth: reads `ELITEA_API_TOKEN` from env or `.env` (walks up to nearest `.git` boundary). Header values can be overridden per-invocation via `--agent-id`, `--version-id`, `--project-id`, `--base-url`.

## Scheduling

To run a test/health-check on a cadence, use GitHub Actions cron (see `references/nudge-case-study.md` § "Scheduling"). Pattern:

- **GH workflow** with `schedule: - cron: '*/15 * * * *'` and `workflow_dispatch` for manual override
- **Matrix over projects** if scanning multiple
- **`concurrency.cancel-in-progress: false`** so slow runs don't pile up but also don't get killed
- **`timeout-minutes`** per job
- **`secrets.ELITEA_NEXT_API_KEY`** for the PAT
- **Idempotency guards in the pipeline itself** — never trust the scheduler to dedupe

## Related skills

- **`elitea-platform`** — for the exact REST endpoint shapes (predict, conversations, messages)
- **`elitea-pipeline`** — for authoring the pipeline being tested
- **`elitea-toolkit`** — for `test_toolkit_tool` operation-level testing

## Upstream documentation (self-learning)

On first invocation, fetch the live docs and cache for the session:

- https://raw.githubusercontent.com/EliteaAI/elitea.github.io/mintlify/docs/how-tos/pipelines/pipeline-runs.mdx
- https://raw.githubusercontent.com/EliteaAI/elitea.github.io/mintlify/docs/menus/chat.mdx
- https://raw.githubusercontent.com/EliteaAI/elitea.github.io/mintlify/docs/menus/pipelines.mdx

If 404, fall back to `references/test-patterns.md`.
