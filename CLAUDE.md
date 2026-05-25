# CLAUDE.md — How to work in this repo

This file tells Claude Code how this repository is organized so it can quickly route any ELITEA-related request to the right agent + skill.

## Repository purpose

A **distributable** Claude-Code-native toolkit for the **ELITEA platform** (https://next.elitea.ai). It contains:
- 2 specialized agents under `agents/<name>/AGENT.md`
- 4 progressive-disclosure skills under `skills/<name>/`
- Plugin manifests (`.claude-plugin/`, `.cursor-plugin/`) for marketplace install
- `npx`-friendly installer (`bin/init.mjs`) for direct file-copy install

There is **no production application** in this repo. The "work" is:
1. Building the agents/skills HERE (developer maintenance)
2. Helping consumers who installed it apply ELITEA artifacts they're working on

When this repo is **installed into a consumer project**, its contents land at:
- `.claude/agents/elitea-{builder,integrator}/AGENT.md`
- `.claude/skills/elitea-{platform,pipeline,toolkit,testing}/`

Skill cross-references inside the agents and other skills use **paths without a leading `.claude/`** (e.g., `elitea-platform/references/api-reference.md`). Claude Code resolves them relative to its discovery root — works both in this source repo and in consumer projects after install.

## Routing requests (in a consumer project)

| User says / wants | Route to |
|---|---|
| "Create / build / make / scaffold / deploy / write an ELITEA agent / pipeline / toolkit / credential / version" | `elitea-builder` agent |
| "Show me / explain / debug / fix / refactor my ELITEA YAML / agent / toolkit" | `elitea-builder` agent (it'll load skills to ground the response) |
| "Test / run / predict / smoke-test / call / hit / fire / trigger my deployed agent / pipeline" | `elitea-integrator` agent |
| "Schedule / cron / GH Action / Power Automate / webhook for ELITEA" | `elitea-integrator` agent |
| "Send a message to ELITEA from Python / curl / JS / Power Automate" | `elitea-integrator` agent |
| "Debug why this conversation is stuck / errored / not replying" | `elitea-integrator` agent |
| "Push this local instruction `.md` to agent N" | `elitea-integrator` (uses `elitea-testing/scripts/update_agent.py`) |
| Pure factual lookup ("what's the endpoint for X", "what's the input schema for getEliteaCoreMessages") | Load `elitea-platform` skill directly; no agent needed |
| Pure YAML question ("can a router node be entry_point?") | Load `elitea-pipeline/references/yaml-schema.md` |

## Skill loading order

When in doubt, load `elitea-platform` first. It's the foundation. Every other skill assumes you know the conventions in `elitea-platform/references/conventions.md`.

Load the other skills lazily on the FIRST mention of:

| Mention triggers loading… |
|---|
| Pipeline YAML, node types, `state`, `entry_point`, `transition`, `router`, `decision`, code nodes, `elitea_client.auth_token` → **`elitea-pipeline`** |
| OpenAPI, toolkit, MCP server, datasource, `selected_tools`, `elitea_title`, `private: true|false`, credentials → **`elitea-toolkit`** |
| Predict, conversation, message, participant, schedule, cron, GH Actions, test, debug, polling, async, callback → **`elitea-testing`** |

## .env handling (in a consumer project)

Consumers create `.env` from `.env.example`:

```
ELITEA_TOKEN=<the user's PAT>
```

Token-name aliases (all the same value):
- `ELITEA_TOKEN` — canonical
- `ELITEA_API_TOKEN` — read by `update_agent.py` (falls back to `ELITEA_TOKEN`)
- `ELITEA_NEXT_API_KEY` — GitHub Actions secret naming used by existing workflows

**Hard rule:** never invent or guess a PAT. If the consumer hasn't set up `.env`, walk them through `cp .env.example .env` first.

**Inside an ELITEA pipeline runtime:** do NOT read `.env`. Use `elitea_client.auth_token` and `elitea_client.base_url`. The runtime injects them.

## Key facts (don't re-derive)

- **Base URLs:** production `https://nexus.elitea.ai/`, pre-prod `https://next.elitea.ai/`
- **API versions:** v2 canonical (`/api/v2/elitea_core/...`); v1 still hosts configurations, artifacts, secrets
- **Most paths embed `prompt_lib/{project_id}`** as the mode + project segment
- **First agent version MUST be `"base"`**; subsequent versions MUST NOT be `"base"`
- **`POST /messages/...` uses `conversation_uuid` (string)**, every other conversation endpoint uses integer `id`
- **`POST /participants/...` body is a JSON LIST** even for one participant
- **Toolkit settings reference credentials by `{"elitea_title", "private"}`**, never raw id
- **Secret-typed fields come back as `"{{secret.NAME}}"`** placeholders
- **`POST /api/v1/configurations/...` returns 200**, not 201
- **Don't send `Content-Type: application/json` on GET requests** — proxies reject it with 400

Full list of conventions: `elitea-platform/references/conventions.md`.

## Worked example to reference

When a user asks "how do I build and operate an ELITEA pipeline end-to-end", point them to `elitea-testing/references/nudge-case-study.md`. It walks through the entire `ConversationHealthAnalyzer` build, the bugs hit, and the fixes.

## Example artifacts (canonical templates inside skills)

| Need a template for… | Look at |
|---|---|
| A pipeline that fetches and classifies conversations | `elitea-pipeline/examples/ConversationHealthAnalyzer.yaml` |
| A pipeline with router + multiple code-node branches | `elitea-pipeline/examples/FetchUIContext.yaml` |
| A trivial code-node pipeline | `elitea-pipeline/examples/wait2mins.yaml` |
| An MCP node | `elitea-pipeline/examples/getuserdetails.yaml` |
| Wrapping ELITEA's own API as a toolkit | `elitea-toolkit/examples/elitea-api.yaml` |
| Wrapping GitHub REST as a toolkit | `elitea-toolkit/examples/githubissues.json` |
| Wrapping a GraphQL endpoint | `elitea-toolkit/examples/githuboardmoovement.json` |

## When the user shares pipeline YAML

1. Validate parseability: `python3 -c "import yaml; yaml.safe_load(open('file.yaml'))"`
2. Run the checklist from `elitea-pipeline/references/workflows.md`:
   - `entry_point` references an existing node ID
   - All node IDs unique
   - All transitions reach `END` eventually
   - Router/Decision have `default_output`
   - If custom `state` block exists, `messages: list` is included
3. Flag legacy node types (`tool`, `function`, `loop`, `loop_from_tool`) and offer modern equivalents

## When the user wants to deploy something

Always follow this order:
1. Author the artifact locally
2. Validate (YAML parse + checklist)
3. Show the user what you're about to deploy
4. Deploy via REST (`POST /applications/...` or `POST /tools/...` etc.) — use exact payloads from `api-reference.md`
5. Verify (`GET` the artifact back; confirm IDs)
6. Smoke-test via `elitea-testing` skill before declaring done

Don't deploy without showing the user the final payload. Don't claim success without a verification GET.

## Source-repo development (this repo only)

If you're working on THIS repo (developing the skills/agents, not consuming them):

- Source layout is `agents/<name>/AGENT.md` and `skills/<name>/` — NOT under `.claude/`. Claude Code in this repo will NOT auto-discover them (it expects `.claude/`).
- To use the skills in this repo's own Claude Code session, run the installer once: `node bin/init.mjs --all --target claude --yes` — that copies the source content into `.claude/`. Remove `.claude/` before commits (it's gitignored).
- After editing a skill/agent, bump versions in `.claude-plugin/plugin.json`, `.claude-plugin/marketplace.json`, `.cursor-plugin/plugin.json`, and `package.json`.
