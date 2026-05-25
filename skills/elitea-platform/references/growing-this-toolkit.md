# Growing this toolkit — how each session feeds knowledge back

This file is the contract every ELITEA skill and agent links to. The point: knowledge gained *during* a real task should land *in* the skill, not just in chat history or one-off `/tmp` scratch files. Sessions are cheap; rediscovering the same gotcha six months from now is expensive.

If you finish a non-trivial task and notice you learned something the skills didn't know, **before you close out the session**, route that knowledge to the right home using the map below. Don't ask the user every time — if it would have saved you 10+ minutes this session, it qualifies; capture it and mention what you added.

## Decision tree — where does this learning belong?

```
What did you learn?
├── A reusable script you wrote in /tmp
│   → Generalize and drop in skills/<area>/scripts/<name>.py
│     (See "Generalizing a session script" below.)
│
├── A gotcha / API quirk / silent-fallback behavior
│   → Append to skills/elitea-platform/references/conventions.md
│     (numbered section, or §10 one-liner if it's terse)
│
├── A response-shape detail (new field, status code, payload requirement)
│   → Edit skills/elitea-platform/references/api-reference.md
│     in the relevant § (find via the top-of-file TOC)
│
├── A new node type / state pattern / pipeline trick
│   → skills/elitea-pipeline/references/{yaml-schema,patterns,workflows}.md
│     Add a working pipeline to examples/ if you debugged a real one
│
├── A new toolkit shape (OpenAPI extension, MCP option, datasource quirk)
│   → skills/elitea-toolkit/references/{toolkit-types,openapi-toolkits}.md
│     Add the spec to examples/ if it's a clean reusable template
│
├── A failure-mode pattern, retry rule, smoke-test trick
│   → skills/elitea-testing/references/test-patterns.md
│     (deep multi-step case studies go in references/, named after the artifact)
│
├── A process insight about HOW the agent should work
│   → agents/<agent>/AGENT.md — extend "How you work", "Hard rules", or
│     "Where to find more"
│
├── A project-specific fact (this client's ID, this Jira key, this credential)
│   → DO NOT put in this repo — it ships to other consumers. Save to
│     memory/ (the user's local memory store) instead.
│
└── A new upstream doc URL worth caching at session start
    → Add to the "Upstream documentation (self-learning)" block in the
      relevant skill's SKILL.md
```

## Generalizing a session script

If you wrote a script in `/tmp/foo.py` that solved this session's problem and you want to promote it:

1. **Strip session-specific values.** No hardcoded project ids, agent ids, version ids, toolkit names, or PATs. Replace with `argparse` flags or env vars.
2. **Add `--help` text** that explains both *what* it does and *why* it exists — what gotcha forced you to write it. Future-you will read the docstring before the code.
3. **Make the auth path consistent.** Read `ELITEA_TOKEN` from env or walk up to the nearest `.env`. Pattern is in any of the existing `scripts/*.py` — copy it.
4. **Default to dry-run for write operations.** A `--apply` flag protects against accidents.
5. **Make it work standalone.** Don't depend on other scripts in the same dir unless you put it in a real Python package. A single-file script users can run with `python3 path/to/it.py` is the goal.
6. **Reference it from the relevant SKILL.md / AGENT.md.** Otherwise it won't get loaded.

Existing examples worth modeling on:
- `skills/elitea-testing/scripts/update_agent.py` — dry-run by default, walks for `.env`, header-block parsing
- `skills/elitea-platform/scripts/update_version_field.py` — GET-mutate-PUT pattern with JSON-or-string value parsing
- `skills/elitea-platform/scripts/build_agent_payload.py` — composes a complex payload from live state

## What NOT to promote

Resist the urge to add everything. The skill stays useful only if it stays focused.

- **Don't capture project-specific facts.** "Project 15742 has these credentials" goes to user memory, not the repo.
- **Don't add scripts that solve a one-off cleanup.** If you'll never run it again, leave it in `/tmp/`.
- **Don't paste a giant prompt.** If you wrote a great instruction block, decide where it belongs (an `examples/`-level template? an agent's own behavior in AGENT.md?) and either polish it or leave it out.
- **Don't add another reference file when an existing one would do.** Search the existing `references/*.md` first; usually there's a section that already covers the topic.

## What to do when you add something

End your turn with a one-liner pointing the user at what you added, e.g.:

> Captured this session's learnings: added `skills/elitea-platform/scripts/foo.py` and a new §11 in conventions.md.

If the user merges the change later, the next session will pick it up automatically. If they don't, no harm done — your help in *this* session is unaffected.

## After editing skills/agents

Per the repo's `CLAUDE.md` § "Source-repo development": bump the version in `.claude-plugin/plugin.json`, `.claude-plugin/marketplace.json`, `.cursor-plugin/plugin.json`, and `package.json`. Run `node bin/init.mjs --all --target claude --yes` once so the source content lands under `.claude/` in this session (the source layout under `agents/` and `skills/` is not auto-discovered; only `.claude/` is).
