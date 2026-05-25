#!/usr/bin/env python3
"""List the LLM models available to an ELITEA project.

Prints the EXACT `model_name` identifier (and `model_project_id`) you must use
in `llm_settings`. The api-reference dummy examples ("claude-sonnet-4-5", etc.)
are NOT real identifiers — wrong names silently fall back to the project
default. Always query this endpoint first.

Usage:
  python3 list_models.py --project-id 15742
  python3 list_models.py --project-id 15742 --base-url https://next.elitea.ai
  python3 list_models.py --project-id 15742 --include-shared no
  python3 list_models.py --project-id 15742 --json   # raw JSON output

Auth:
  Reads ELITEA_TOKEN (or ELITEA_API_TOKEN, ELITEA_NEXT_API_KEY) from the
  environment or the nearest .env file walking up from CWD to the first .git
  boundary.
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
    sys.exit(
        f"error: no PAT found in env ({', '.join(TOKEN_ENV_NAMES)}) or nearest .env"
    )


def fetch_models(base_url: str, project_id: int, token: str, include_shared: bool) -> dict:
    qs = "?include_shared=true" if include_shared else ""
    url = f"{base_url.rstrip('/')}/api/v1/configurations/models/{project_id}{qs}"
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    try:
        with urllib.request.urlopen(req) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="replace")[:500]
        sys.exit(f"HTTP {e.code} {url}\n{body}")
    except urllib.error.URLError as e:
        sys.exit(f"network error {url}: {e.reason}")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--project-id", type=int, required=True, help="ELITEA project id")
    p.add_argument("--base-url", default=DEFAULT_BASE_URL,
                   help=f"ELITEA base URL (default {DEFAULT_BASE_URL})")
    p.add_argument("--include-shared", choices=("yes", "no"), default="yes",
                   help="include models shared from promptlib_public (default yes)")
    p.add_argument("--json", action="store_true", help="dump raw JSON instead of a table")
    args = p.parse_args()

    token = load_token()
    data = fetch_models(args.base_url, args.project_id, token, args.include_shared == "yes")

    if args.json:
        json.dump(data, sys.stdout, indent=2)
        print()
        return

    items = data.get("items", [])
    if not items:
        print(f"(no models in project {args.project_id} — check that the project owns or shares a model config)")
        return

    print(f"{len(items)} model(s) available for project {args.project_id}:\n")
    for m in items:
        ctx = m.get("context_window")
        maxo = m.get("max_output_tokens")
        flags = []
        if m.get("shared"):
            flags.append("shared")
        if m.get("default"):
            flags.append("default")
        if m.get("supports_reasoning"):
            flags.append("reasoning")
        if m.get("supports_vision"):
            flags.append("vision")
        flag_str = f" [{', '.join(flags)}]" if flags else ""
        print(f"  name:        {m['name']!r}")
        print(f"    display:   {m.get('display_name')}")
        print(f"    project:   {m.get('project_id')}{flag_str}")
        print(f"    ctx/out:   {ctx} / {maxo}")
        print()
    print("Use `name` verbatim as llm_settings.model_name; use the matching project as llm_settings.model_project_id.")


if __name__ == "__main__":
    main()
