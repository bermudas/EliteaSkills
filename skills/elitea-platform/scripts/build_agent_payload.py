#!/usr/bin/env python3
"""Build a complete POST /applications create-payload by pulling LIVE toolkit settings.

Why this exists: every tool entry in an agent's `tools[]` needs the toolkit's
full `settings` block (api_version, custom_headers, credential refs,
selected_tools, embedding_model, etc.) — NOT a synthetic stub. Reproducing the
settings by hand is fragile because the toolkit's defaults change over time
and credentials are referenced by `{"elitea_title", "private"}` rather than
the raw id you typed in.

This script GETs `GET /tools/prompt_lib/{project_id}` and copies the relevant
toolkits' settings verbatim into the create payload — minus echo-only fields
the server rejects on input (e.g. `available_tools`).

Usage:
  python3 build_agent_payload.py \
      --project-id 15742 \
      --name "SOG-MYGV BA Assistant" \
      --description "BA assistant for SOG-MYGV" \
      --instructions-file ./ba_instructions.md \
      --model-name eu.anthropic.claude-sonnet-4-6 \
      --model-project-id 1 \
      --toolkit JIraeu \
      --toolkit SOGMYGVConfluence \
      --out /tmp/create_payload.json

Then POST it:
  curl -X POST "$BASE_URL/api/v2/elitea_core/applications/prompt_lib/$PROJECT_ID" \
       -H "Authorization: Bearer $ELITEA_TOKEN" \
       -H "Content-Type: application/json" \
       --data-binary @/tmp/create_payload.json

Hard rules baked in:
  * First version is always named "base" (required by ELITEA)
  * Each tool entry includes `type` + full `settings` (required on create)
  * Doesn't emit `author_id` on tools (that field is required on PUT, not POST)
  * Strips `settings.available_tools` (server-echo, rejected on input)

If a named --toolkit isn't found in the project, the script prints the
available toolkit_names and exits non-zero so you can correct the name. Match
is on the sanitized `toolkit_name` (what you see in API responses), NOT the
human display `name`.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

DEFAULT_BASE_URL = "https://next.elitea.ai"
TOKEN_ENV_NAMES = ("ELITEA_TOKEN", "ELITEA_API_TOKEN", "ELITEA_NEXT_API_KEY")


def load_token() -> str:
    for name in TOKEN_ENV_NAMES:
        v = os.environ.get(name)
        if v:
            return v
    here = Path.cwd().resolve()
    for parent in [here, *here.parents]:
        env_file = parent / ".env"
        if env_file.is_file():
            for line in env_file.read_text().splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, _, v = line.partition("=")
                if k.strip() in TOKEN_ENV_NAMES:
                    return v.strip().strip('"').strip("'")
        if (parent / ".git").exists():
            break
    sys.exit(f"error: no PAT found in env ({', '.join(TOKEN_ENV_NAMES)}) or nearest .env")


def http_get(url: str, token: str) -> dict:
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    try:
        with urllib.request.urlopen(req) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        sys.exit(f"HTTP {e.code} GET {url}\n{e.read().decode(errors='replace')[:500]}")
    except urllib.error.URLError as e:
        sys.exit(f"network error {url}: {e.reason}")


def make_tool_entry(t: dict, only_tools: list[str] | None) -> dict:
    settings = {k: v for k, v in t["settings"].items() if k != "available_tools"}
    if only_tools is not None:
        settings = dict(settings)
        settings["selected_tools"] = [s for s in settings.get("selected_tools", []) if s in only_tools]
    return {
        "type": t["type"],
        "toolkit_id": t["id"],
        "toolkit_name": t["toolkit_name"],
        "name": t["name"],
        "description": t.get("description"),
        "settings": settings,
        "selected_tools": settings.get("selected_tools", []),
    }


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--project-id", type=int, required=True)
    p.add_argument("--base-url", default=DEFAULT_BASE_URL)
    p.add_argument("--name", required=True)
    p.add_argument("--description", default="")
    p.add_argument("--instructions", help="instructions text (inline)")
    p.add_argument("--instructions-file", type=Path, help="read instructions from a file")
    p.add_argument("--model-name", required=True,
                   help="EXACT identifier from list_models.py output, e.g. eu.anthropic.claude-sonnet-4-6")
    p.add_argument("--model-project-id", type=int, default=1,
                   help="project hosting the model config (usually 1 — promptlib_public)")
    p.add_argument("--temperature", type=float, default=0.4)
    p.add_argument("--max-tokens", type=int, default=4096)
    p.add_argument("--reasoning-effort", default="medium", choices=("low", "medium", "high"))
    p.add_argument("--agent-type", default="openai", choices=("openai", "pipeline", "react"))
    p.add_argument("--step-limit", type=int, default=25)
    p.add_argument("--welcome-message", default="")
    p.add_argument("--toolkit", action="append", default=[],
                   help="toolkit_name (NOT display name) to attach; repeatable. Match is exact and case-sensitive.")
    p.add_argument("--only-tool", action="append", default=[],
                   help="restrict selected_tools across ALL attached toolkits to this set; repeatable")
    p.add_argument("--starter", action="append", default=[], help="conversation starter; repeatable")
    p.add_argument("--out", type=Path, default=Path("/tmp/create_agent_payload.json"))
    args = p.parse_args()

    if not args.instructions and not args.instructions_file:
        sys.exit("error: provide --instructions or --instructions-file")
    instructions = args.instructions or args.instructions_file.read_text()

    token = load_token()
    base = args.base_url.rstrip("/")
    tools_resp = http_get(f"{base}/api/v2/elitea_core/tools/prompt_lib/{args.project_id}", token)
    by_name = {t["toolkit_name"]: t for t in tools_resp.get("rows", [])}

    tools: list[dict] = []
    missing: list[str] = []
    for tk in args.toolkit:
        t = by_name.get(tk)
        if t is None:
            missing.append(tk)
            continue
        tools.append(make_tool_entry(t, args.only_tool or None))
    if missing:
        available = ", ".join(sorted(by_name)) or "(none)"
        sys.exit(f"toolkits not found: {missing}\navailable in project: {available}")

    payload = {
        "name": args.name,
        "description": args.description,
        "type": "interface",
        "versions": [
            {
                "name": "base",
                "agent_type": args.agent_type,
                "tags": [],
                "instructions": instructions,
                "llm_settings": {
                    "max_tokens": args.max_tokens,
                    "temperature": args.temperature,
                    "reasoning_effort": args.reasoning_effort,
                    "model_name": args.model_name,
                    "model_project_id": args.model_project_id,
                },
                "variables": [],
                "tools": tools,
                "conversation_starters": args.starter,
                "welcome_message": args.welcome_message,
                "meta": {"step_limit": args.step_limit},
            }
        ],
    }

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, indent=2))
    print(f"wrote {args.out}")
    print(f"  toolkits attached: {[t['toolkit_name'] for t in tools]}")
    print(f"  model_name:        {args.model_name} (project {args.model_project_id})")
    print(f"\nDeploy with:")
    print(f'  curl -X POST "{base}/api/v2/elitea_core/applications/prompt_lib/{args.project_id}" \\')
    print(f'       -H "Authorization: Bearer $ELITEA_TOKEN" -H "Content-Type: application/json" \\')
    print(f"       --data-binary @{args.out}")


if __name__ == "__main__":
    main()
