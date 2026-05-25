# EliteaSkills

A Claude-Code-native toolkit for the **[ELITEA platform](https://next.elitea.ai)** — 2 role-based agents and 4 progressive-disclosure skills covering the full ELITEA lifecycle: authoring pipeline YAML, wrapping APIs as toolkits, deploying agents, smoke-testing them, and scheduling recurring jobs.

Distributed as a Claude Code plugin (and via an `npx` installer for Cursor / Windsurf / GitHub Copilot).

## What's in the box

```
agents/
├── elitea-builder/                 # builds ELITEA artifacts
└── elitea-integrator/              # connects external systems to ELITEA

skills/
├── elitea-platform/                # foundation: REST API, auth, IDs, MCP catalog
├── elitea-pipeline/                # pipeline YAML — schema, patterns, examples
├── elitea-toolkit/                 # toolkit types + real OpenAPI specs
└── elitea-testing/                 # predict, debug, schedule + nudge case study
```

## Install — three ways

### 1. Claude Code plugin marketplace (recommended inside Claude Code)

```
/plugin marketplace add Bermudas/EliteaSkills
/plugin install elitea-skills@elitea-skills
```

Installs the full bundle (both agents + all four skills) in one shot. To install just a piece:

```
/plugin install elitea-builder@elitea-skills
/plugin install elitea-platform@elitea-skills
```

### 2. `npx` installer (works for Claude Code, Cursor, Windsurf, GitHub Copilot)

```bash
# everything
npx github:Bermudas/EliteaSkills init --all

# pick & choose
npx github:Bermudas/EliteaSkills init --agents elitea-builder
npx github:Bermudas/EliteaSkills init --skills elitea-platform,elitea-pipeline

# specific IDE only
npx github:Bermudas/EliteaSkills init --target claude --update
```

The installer copies `agents/` and `skills/` into the right IDE-specific dirs:
- Claude Code → `.claude/agents/` and `.claude/skills/`
- Cursor → `.cursor/agents/` and `.cursor/skills/`
- Windsurf → `.windsurf/agents/` and `.windsurf/skills/`
- GitHub Copilot → `.github/agents/<name>.agent.md` (flat layout with model alias normalized)

### 3. Copy by hand

This repo is self-contained — `agents/<name>/AGENT.md` and `skills/<name>/SKILL.md` are ready to drop into your IDE's discovery directory.

## After install — set up auth

Every consumer project needs an ELITEA Personal Access Token:

1. Open https://next.elitea.ai → **Profile** → **API Tokens** → generate one
2. In your project, create `.env`:
   ```bash
   cp .env.example .env
   $EDITOR .env
   # paste the token after ELITEA_TOKEN=
   ```

The token name is `ELITEA_TOKEN` in this repo. Older code or third-party docs may use other names — they all mean the same PAT:

| Where | Env var name |
|---|---|
| **Project `.env`** | `ELITEA_TOKEN` ← canonical |
| `skills/elitea-testing/scripts/update_agent.py` | `ELITEA_API_TOKEN` (falls back to `ELITEA_TOKEN`) |
| GitHub Actions secrets | `ELITEA_NEXT_API_KEY` (matches existing workflow conventions) |
| Inside an ELITEA pipeline (runtime) | DO NOT read `.env` — use `elitea_client.auth_token` |

## What each agent does

### `elitea-builder` 🛠️
For **building artifacts ON the ELITEA platform**: agents, pipelines, toolkits, credentials, links.

Triggers on: *"create an elitea agent"*, *"build a pipeline"*, *"wrap an API as a toolkit"*, *"deploy this YAML"*, *"link toolkit X to agent Y"*, *"create a credential"*.

### `elitea-integrator` 🔌
For **calling ELITEA from somewhere else** — external Python/JS scripts, GitHub Actions, Power Automate, Teams bots, JIRA webhooks, scheduled jobs.

Triggers on: *"integrate with elitea from"*, *"schedule a recurring run"*, *"test my deployed agent"*, *"debug why this conversation is stuck"*.

## What each skill contains

| Skill | When it gets loaded | Key files |
|---|---|---|
| **`elitea-platform`** | Any ELITEA work that needs REST endpoint details, auth, ID rules, MCP tool catalog. **Load first when in doubt.** | `references/api-reference.md`, `references/conventions.md`, `references/mcp-tools.md` |
| **`elitea-pipeline`** | Authoring/debugging pipeline YAML. | `references/yaml-schema.md`, `references/patterns.md`, `references/workflows.md`, `examples/*.yaml` |
| **`elitea-toolkit`** | Wrapping APIs, MCP servers, datasources, custom python as ELITEA toolkits. | `references/toolkit-types.md`, `references/openapi-toolkits.md`, `examples/*.{json,yaml}` |
| **`elitea-testing`** | Running, predicting, debugging, scheduling. | `references/test-patterns.md`, `references/nudge-case-study.md`, `scripts/update_agent.py` |

## Worked example — the nudge pipeline

For a complete end-to-end story (build → deploy → debug → schedule), read `skills/elitea-testing/references/nudge-case-study.md`. It walks through how `ConversationHealthAnalyzer` was built: deterministic classifier instead of LLM, the false-positive "hung" bug discovered on the first apply run, the idempotency design, deployment to two projects, and the GitHub Actions cron that runs it every 15 minutes.

The actual artifact files in this repo:
- Pipeline YAML: `skills/elitea-pipeline/examples/ConversationHealthAnalyzer.yaml`
- GH Actions workflow template referenced from the case study

## Local usage workflow

After installing into a project, common operations:

### Push a local instruction `.md` to a deployed agent
```bash
python3 .claude/skills/elitea-testing/scripts/update_agent.py path/to/instruction.md           # dry-run
python3 .claude/skills/elitea-testing/scripts/update_agent.py path/to/instruction.md --apply   # apply
```

### Smoke-test a deployed agent version
```bash
source .env
curl -X POST -H "Authorization: Bearer $ELITEA_TOKEN" -H "Content-Type: application/json" \
  -d '{"user_input":"hello"}' \
  "https://next.elitea.ai/api/v2/elitea_core/predict/prompt_lib/$PROJECT_ID/$VERSION_ID"
```

Full test-pattern recipes (conversation flow, send-and-poll, async, debugging checklist) live in `skills/elitea-testing/references/test-patterns.md`.

## Repository layout (developing this package)

```
EliteaSkills/
├── agents/
│   ├── elitea-builder/AGENT.md
│   └── elitea-integrator/AGENT.md
├── skills/
│   ├── elitea-platform/
│   ├── elitea-pipeline/
│   ├── elitea-toolkit/
│   └── elitea-testing/
├── .claude-plugin/
│   ├── plugin.json                 # top-level Claude Code plugin manifest
│   └── marketplace.json            # per-agent + per-skill installables
├── .cursor-plugin/plugin.json      # Cursor manifest
├── bin/init.mjs                    # npx installer
├── package.json                    # npm metadata + bin alias
├── README.md                       # this file
├── CLAUDE.md                       # routing hints for Claude Code
├── .env.example
└── .gitignore
```

## Environment

ELITEA runs at **`https://next.elitea.ai/`** — this is the only environment. The legacy `nexus.elitea.ai` host has been retired; if you find references to it in old code or docs, update them to `next.elitea.ai`.

## Contributing

If you build a new pipeline or toolkit worth keeping:

1. Drop the YAML/JSON into `skills/elitea-pipeline/examples/` or `skills/elitea-toolkit/examples/`.
2. Add a one-line entry in that skill's `SKILL.md` example catalog.
3. If it embodies a non-obvious pattern (idempotency, async polling, error recovery), document it in the relevant `references/*.md`.
4. Bump `version` in `.claude-plugin/plugin.json`, `.claude-plugin/marketplace.json`, `.cursor-plugin/plugin.json`, and `package.json`.

## License

MIT — see `LICENSE`.

## Credits

Packaging pattern (plugin manifests, multi-target `init.mjs` installer, sdlc-skills style agent frontmatter) inspired by [arozumenko/sdlc-skills](https://github.com/arozumenko/sdlc-skills).
