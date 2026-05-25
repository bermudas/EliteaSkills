#!/usr/bin/env python3
"""GET an agent version, mutate a small set of fields, PUT it back — safely.

The PUT endpoint replaces the version body wholesale. If you forget any
existing field (especially tools), it disappears. This script does the
GET-mutate-PUT dance so you can change one thing without losing the rest.

Quirks handled:
  * `tools[].author_id` is REQUIRED on PUT (not on POST). We preserve it from
    the GET response.
  * `tools[].settings.available_tools` is a server-only echo; we strip it.
  * The api-reference's "flat update payload" lives at
    `PUT /api/v2/elitea_core/version/prompt_lib/{project_id}/{app_id}/{ver_id}`
    (note: `version`, singular). Don't confuse with the agent-entity PUT
    (`/application/...`) which uses a nested `version` object.

Usage:
  # change just the LLM
  python3 update_version_field.py --project-id 15742 --app-id 1 --version-id 1 \\
      --set llm_settings.model_name=eu.anthropic.claude-sonnet-4-6 \\
      --set llm_settings.temperature=0.3 --apply

  # tweak instructions from a file
  python3 update_version_field.py --project-id 15742 --app-id 1 --version-id 1 \\
      --set-file instructions=./new_instructions.md --apply

  # dry-run (default) prints the diff and exits without PUTting
  python3 update_version_field.py --project-id 15742 --app-id 1 --version-id 1 \\
      --set welcome_message="Hi there!"

Supported `--set key=value` paths:
  name, instructions, welcome_message, agent_type, conversation_starters,
  tags, variables, meta.step_limit,
  llm_settings.{model_name,model_project_id,temperature,max_tokens,reasoning_effort}

For nested paths use dotted form (`llm_settings.model_name`). Values are
parsed as JSON if they look JSON-y (numbers, true/false, null, [..], {..}),
otherwise as strings.

Auth:
  ELITEA_TOKEN / ELITEA_API_TOKEN / ELITEA_NEXT_API_KEY (env or .env walk).
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


def http(method: str, url: str, token: str, body: dict | None = None) -> tuple[int, dict]:
    headers = {"Authorization": f"Bearer {token}"}
    data = None
    if body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req) as r:
            return r.status, json.load(r)
    except urllib.error.HTTPError as e:
        return e.code, {"_error_body": e.read().decode(errors="replace")[:2000]}
    except urllib.error.URLError as e:
        sys.exit(f"network error {url}: {e.reason}")


def parse_value(raw: str):
    """Return JSON-parsed value if it looks JSON-y, else the raw string."""
    s = raw.strip()
    if not s:
        return s
    try:
        if s[0] in "[{\"" or s in ("true", "false", "null") or s.lstrip("-").replace(".", "", 1).isdigit():
            return json.loads(s)
    except json.JSONDecodeError:
        pass
    return raw


def set_path(obj: dict, dotted: str, value):
    parts = dotted.split(".")
    cur = obj
    for p in parts[:-1]:
        if p not in cur or not isinstance(cur[p], dict):
            cur[p] = {}
        cur = cur[p]
    cur[parts[-1]] = value


def strip_tool(t: dict) -> dict:
    settings = {k: v for k, v in t.get("settings", {}).items() if k != "available_tools"}
    return {
        "type": t["type"],
        "toolkit_id": t.get("id"),
        "toolkit_name": t["toolkit_name"],
        "name": t["name"],
        "description": t.get("description"),
        "author_id": t.get("author_id"),
        "settings": settings,
        "selected_tools": settings.get("selected_tools", []),
    }


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--project-id", type=int, required=True)
    p.add_argument("--app-id", type=int, required=True)
    p.add_argument("--version-id", type=int, required=True)
    p.add_argument("--version-name", default="base",
                   help="name of the version to GET (default 'base')")
    p.add_argument("--base-url", default=DEFAULT_BASE_URL)
    p.add_argument("--set", action="append", default=[], metavar="KEY=VALUE",
                   help="dotted path = value; repeatable. Values parsed as JSON if they look it.")
    p.add_argument("--set-file", action="append", default=[], metavar="KEY=PATH",
                   help="read VALUE from a file; repeatable")
    p.add_argument("--apply", action="store_true",
                   help="actually PUT (default is dry-run preview)")
    args = p.parse_args()

    if not args.set and not args.set_file:
        sys.exit("error: no --set or --set-file provided; nothing to update")

    token = load_token()
    base = args.base_url.rstrip("/")
    get_url = f"{base}/api/v2/elitea_core/application/prompt_lib/{args.project_id}/{args.app_id}/{args.version_name}"
    status, full = http("GET", get_url, token)
    if status != 200:
        sys.exit(f"GET {get_url} → {status}\n{full.get('_error_body','')}")

    v = full.get("version_details") or {}
    if not v:
        sys.exit("GET response missing version_details — check version_name")

    payload = {
        "projectId": args.project_id,
        "applicationId": args.app_id,
        "versionId": args.version_id,
        "name": v.get("name"),
        "tags": v.get("tags", []),
        "instructions": v.get("instructions", ""),
        "variables": v.get("variables", []),
        "tools": [strip_tool(t) for t in v.get("tools", [])],
        "llm_settings": v.get("llm_settings", {}),
        "conversation_starters": v.get("conversation_starters", []),
        "agent_type": v.get("agent_type", "openai"),
        "welcome_message": v.get("welcome_message", ""),
        "meta": v.get("meta", {"step_limit": 25}),
    }

    before = json.dumps(payload, sort_keys=True)

    for kv in args.set:
        if "=" not in kv:
            sys.exit(f"--set expects KEY=VALUE, got {kv!r}")
        key, _, raw = kv.partition("=")
        set_path(payload, key.strip(), parse_value(raw))
    for kv in args.set_file:
        if "=" not in kv:
            sys.exit(f"--set-file expects KEY=PATH, got {kv!r}")
        key, _, path = kv.partition("=")
        set_path(payload, key.strip(), Path(path).read_text())

    after = json.dumps(payload, sort_keys=True)
    if before == after:
        print("no changes — nothing to do")
        return

    # tiny diff summary
    print("Changes:")
    for kv in args.set:
        key = kv.split("=", 1)[0].strip()
        print(f"  {key} = {parse_value(kv.split('=', 1)[1])!r}")
    for kv in args.set_file:
        key, _, path = kv.partition("=")
        print(f"  {key.strip()} ← contents of {path}")
    if not args.apply:
        print("\n(dry-run — re-run with --apply to PUT)")
        return

    put_url = f"{base}/api/v2/elitea_core/version/prompt_lib/{args.project_id}/{args.app_id}/{args.version_id}"
    status, resp = http("PUT", put_url, token, payload)
    if status not in (200, 201):
        print(f"PUT {put_url} → {status}", file=sys.stderr)
        print(resp.get("_error_body", json.dumps(resp))[:2000], file=sys.stderr)
        sys.exit(1)
    print(f"\nPUT → {status} OK")
    ll = (resp.get("llm_settings") or
          resp.get("version_details", {}).get("llm_settings") or {})
    if ll:
        print(f"  llm_settings now: {json.dumps(ll)}")


if __name__ == "__main__":
    main()
