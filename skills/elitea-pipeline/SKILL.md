---
name: elitea-pipeline
description: Author, debug, and deploy ELITEA pipelines (YAML-defined multi-step agent workflows). Knows all 10 modern node types (llm, agent, toolkit, mcp, code, custom, router, decision, state_modifier, printer), state management, and the platform-specific runtime helpers (`elitea_client.auth_token`, `elitea_client.base_url`, `elitea_state.get(...)`). Use this skill whenever the user wants to create, modify, debug, or understand an ELITEA pipeline; whenever they show pipeline YAML; whenever they mention node types, state vars, routers, decisions, transitions, entry points, or pipeline triggers. Examples live under `examples/`; the worked nudge case-study lives in `elitea-testing/references/nudge-case-study.md`.
---

# ELITEA Pipeline — Authoring & Debugging

A pipeline is an `agent_type: pipeline` ELITEA agent whose `instructions` field is YAML describing a node graph. This skill covers the YAML schema, the modern node types, common shapes, and the runtime helpers you have inside `code` nodes.

> **Growing this skill:** if a session uncovers a new node-type quirk, state pattern, or pipeline gotcha, append it to `references/{yaml-schema,patterns,workflows}.md` or add a clean working pipeline to `examples/`. See `elitea-platform/references/growing-this-toolkit.md` for the full routing decision tree and "what NOT to promote" guidance.

## Quick lookup

| If you need... | Load |
|---|---|
| YAML top-level structure (entry_point/state/nodes), data types, naming rules | `references/yaml-schema.md` § 1 |
| Detailed schema for every modern node type | `references/yaml-schema.md` § 2 |
| Connection rules (`transition` / `routes` / `nodes` / `END`) | `references/yaml-schema.md` § 3 |
| Legacy node types (only for reading old pipelines — don't write these) | `references/yaml-schema.md` § Legacy |
| When to pick which pipeline shape (linear / loop / branching / converging) | `references/patterns.md` |
| Validation checklist & common debugging steps | `references/workflows.md` |
| How `alita_client` / `elitea_client` helpers work in code nodes | `references/workflows.md` § "Code Node Special Capabilities" |
| Real, working pipeline YAML files to learn from | `examples/*.yaml` (see catalog below) |

## Example catalog (`examples/`)

| File | What it shows |
|---|---|
| `ConversationHealthAnalyzer.yaml` | **The flagship example.** Full pipeline that fetches conversations, classifies status (errored/completed/active/pending), nudges failed ones, with idempotency guards and `apply`/dry-run modes. Demonstrates: async httpx calls, `elitea_client.auth_token`, `elitea_state.get`, structured output, parallelism via `asyncio.gather`, deterministic classification (no LLM call needed). Walked through end-to-end in `elitea-testing/references/nudge-case-study.md`. |
| `FetchUIContext.yaml` | Router-based dispatch: parses entity_type and routes to one of four `code` nodes that fetch different entity details via the REST API. Best example of `router` + `code` + auth via `elitea_client.auth_token`. Also demonstrates the **secret redaction** pattern (mask any field whose key matches a sensitive-name list). |
| `GetAvailableToolkits.yaml` | Minimal: single `toolkit` node returning the toolkit list. Read first if you're new to pipeline YAML. |
| `GetToolDescription.yaml` | Single toolkit-call pattern with `input_mapping`. |
| `GetAvailableProjectTools.yaml` | Aggregator: combines toolkit metadata with per-toolkit available tools. Good `code`-node example. |
| `getuserdetails.yaml` | Tiny `mcp` node example. |
| `wait2mins.yaml` | Trivial `code` node that just sleeps — useful for testing interrupts/timeouts. |

## Core rules (always in effect)

- **Modern node types only** in new pipelines: `llm`, `agent`, `toolkit`, `mcp`, `code`, `custom`, `router`, `decision`, `state_modifier`, `printer`. Legacy types appear in `yaml-schema.md` for reading existing pipelines only.
- **If you define a custom `state` block, it MUST include `messages: list`.** Otherwise omit `state` entirely to use defaults (`input: str`, `messages: list`).
- **Every execution path must reach `END`.** Router and Decision nodes must declare `default_output`.
- **Router and Decision nodes cannot be `entry_point`.** Decision nodes cannot chain directly to another Decision.
- **Produce complete, valid YAML** when generating — never partial snippets. Validate with `python3 -c "import yaml; yaml.safe_load(open('file.yaml'))"`.
- **Never hardcode secrets.** Use `alita_client.unsecret('NAME')` if reading project-stored secrets; use `elitea_client.auth_token` for self-API calls.
- **Inside code nodes use `elitea_state.get('var', default)` and `elitea_client.{auth_token,base_url}`** — these are the runtime-injected helpers. `alita_client` is an alias for some operations (artifacts, apps). When in doubt, prefer `elitea_*`.
- **HTTP from inside code nodes:** use `httpx.AsyncClient(timeout=60, follow_redirects=True)`; do NOT add `Content-Type: application/json` on GET requests (some proxies reject this; use `Accept: application/json` for GETs).

## Workflow when authoring a new pipeline

1. Clarify inputs / outputs / external integrations needed
2. If broad design: load `references/patterns.md` to pick the shape
3. Load `references/yaml-schema.md` for the node-type definitions you'll use
4. Sketch the node IDs and transitions on paper; draft the state block
5. Generate complete YAML
6. Validate against the checklist in `references/workflows.md`
7. Deploy via `POST /api/v2/elitea_core/applications/prompt_lib/{project_id}` with `agent_type: "pipeline"` and the YAML as `instructions` (see `elitea-platform/references/api-reference.md` § 2.1 for the full payload)
8. Test via `POST /api/v2/elitea_core/predict/prompt_lib/{project_id}/{version_id}` — see `elitea-testing` skill

## How to deploy / update an existing pipeline

After editing YAML locally:

```bash
# update version (assumes you know the application_id + version_id)
curl -X PUT -H "Authorization: Bearer $ELITEA_TOKEN" -H "Content-Type: application/json" \
  -d @- "https://next.elitea.ai/api/v2/elitea_core/version/prompt_lib/$PROJECT_ID/$APP_ID/$VER_ID" <<EOF
{
  "id": $VER_ID, "application_id": $APP_ID, "name": "base",
  "agent_type": "pipeline",
  "instructions": $(jq -Rs . < pipeline.yaml),
  ...other fields preserved from the GET response...
}
EOF
```

The full payload shape and "always-GET-first-then-merge" pattern is in `elitea-testing/scripts/update_agent.py`.

## Upstream documentation (self-learning)

On first invocation in a session, fetch the latest authoritative pipeline docs from upstream and cache for the rest of the session. The bundled `references/` files are a snapshot; these are the live source:

- https://raw.githubusercontent.com/EliteaAI/elitea.github.io/mintlify/docs/how-tos/pipelines/overview.mdx
- https://raw.githubusercontent.com/EliteaAI/elitea.github.io/mintlify/docs/how-tos/pipelines/yaml.mdx
- https://raw.githubusercontent.com/EliteaAI/elitea.github.io/mintlify/docs/how-tos/pipelines/states.mdx
- https://raw.githubusercontent.com/EliteaAI/elitea.github.io/mintlify/docs/how-tos/pipelines/nodes-connectors.mdx
- https://raw.githubusercontent.com/EliteaAI/elitea.github.io/mintlify/docs/how-tos/pipelines/nodes/interaction-nodes.mdx
- https://raw.githubusercontent.com/EliteaAI/elitea.github.io/mintlify/docs/how-tos/pipelines/nodes/execution-nodes.mdx
- https://raw.githubusercontent.com/EliteaAI/elitea.github.io/mintlify/docs/how-tos/pipelines/nodes/control-flow-nodes.mdx
- https://raw.githubusercontent.com/EliteaAI/elitea.github.io/mintlify/docs/how-tos/pipelines/nodes/utility-nodes.mdx
- https://raw.githubusercontent.com/EliteaAI/elitea.github.io/mintlify/docs/how-tos/pipelines/pipeline-runs.mdx
- https://raw.githubusercontent.com/EliteaAI/elitea.github.io/mintlify/docs/how-tos/pipelines/ai-assistant-in-nodes.mdx
- https://raw.githubusercontent.com/EliteaAI/elitea.github.io/mintlify/docs/how-tos/pipelines/entry-point.mdx
- https://raw.githubusercontent.com/EliteaAI/elitea.github.io/mintlify/docs/how-tos/pipelines/flow-editor.mdx
- https://raw.githubusercontent.com/EliteaAI/elitea.github.io/mintlify/docs/how-tos/pipelines/appendix-comparison-tables.mdx

If 404, the docs moved — fall back to `references/yaml-schema.md` and flag the breakage.

## Related skills

- **`elitea-platform`** — for any REST endpoint detail, MCP tool reference, ID rules
- **`elitea-toolkit`** — when your pipeline binds a toolkit (`toolkit` or `mcp` node), or needs a new toolkit created
- **`elitea-testing`** — for predict/run/debug; the nudge case study walks through a real build→deploy→test cycle
