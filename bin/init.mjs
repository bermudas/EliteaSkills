#!/usr/bin/env node
/**
 * elitea-skills installer.
 *
 * Three ways to consume this repo:
 *
 *   1. Claude Code plugin marketplace (preferred inside Claude Code):
 *        /plugin marketplace add Bermudas/EliteaSkills
 *        /plugin install elitea-skills@elitea-skills
 *
 *   2. This CLI (works for Claude Code, Cursor, Windsurf, GitHub Copilot —
 *      copies agents and skills directly into the IDE dirs):
 *        npx github:Bermudas/EliteaSkills init
 *        npx github:Bermudas/EliteaSkills init --all
 *        npx github:Bermudas/EliteaSkills init --agents elitea-builder
 *        npx github:Bermudas/EliteaSkills init --skills elitea-platform,elitea-pipeline
 *        npx github:Bermudas/EliteaSkills init --agents all --skills all
 *        npx github:Bermudas/EliteaSkills init --update          # overwrite existing
 *        npx github:Bermudas/EliteaSkills init --target claude   # one specific IDE
 *
 *      GitHub Copilot CLI target (--target copilot) flattens agents to
 *      `.github/agents/<name>.agent.md` (not a directory) and rewrites
 *      `model: sonnet|opus|haiku` to the corresponding canonical id.
 *
 *   3. Read this repo directly: `agents/<name>/AGENT.md` and
 *      `skills/<name>/SKILL.md` are self-contained — copy by hand if you
 *      prefer.
 */

import {
  cpSync,
  existsSync,
  mkdirSync,
  readdirSync,
  readFileSync,
  rmSync,
  statSync,
  writeFileSync,
} from "fs";
import { join, dirname, basename } from "path";
import { fileURLToPath } from "url";
import { createInterface } from "readline";

const __dirname = dirname(fileURLToPath(import.meta.url));
const PKG_ROOT = join(__dirname, "..");
const CWD = process.cwd();

const TARGETS = [
  { id: "claude", dir: ".claude", label: "Claude Code" },
  { id: "cursor", dir: ".cursor", label: "Cursor" },
  { id: "windsurf", dir: ".windsurf", label: "Windsurf" },
  { id: "copilot", dir: ".github", label: "GitHub Copilot" },
];

// ---------------------------------------------------------------------------
// Catalog discovery — read agents/ and skills/ at the repo root so the
// installer stays correct as content is added or removed. No hardcoded lists.
// ---------------------------------------------------------------------------

function listDirs(parent) {
  const root = join(PKG_ROOT, parent);
  if (!existsSync(root)) return [];
  return readdirSync(root)
    .filter((name) => !name.startsWith(".") && name !== "README.md")
    .filter((name) => {
      try {
        return statSync(join(root, name)).isDirectory();
      } catch {
        return false;
      }
    })
    .sort();
}

function loadCatalog() {
  return {
    agents: listDirs("agents"),
    skills: listDirs("skills"),
  };
}

// ---------------------------------------------------------------------------
// CLI parsing
// ---------------------------------------------------------------------------

function parseArgs(argv) {
  const out = {
    all: false,
    update: false,
    yes: false,
    agents: null,
    skills: null,
    targets: null,
  };
  const unknown = [];
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (a === "--all") out.all = true;
    else if (a === "--yes") out.yes = true;
    else if (a === "--update") out.update = true;
    else if (a === "--agents") out.agents = splitList(argv[++i]);
    else if (a === "--skills") out.skills = splitList(argv[++i]);
    else if (a === "--target") out.targets = splitList(argv[++i]);
    else if (a === "--help" || a === "-h") {
      printHelp();
      process.exit(0);
    } else {
      unknown.push(a);
    }
  }
  if (unknown.length) {
    console.error(`\n  ! Unrecognised argument(s): ${unknown.join(", ")}`);
    const looksCommaSplit = unknown.some(
      (a) => a.includes(",") && !a.startsWith("-"),
    );
    if (looksCommaSplit) {
      console.error(
        "\n  Looks like a comma-separated list was split by the shell.",
      );
      console.error(
        "  Fix: remove spaces after commas, or quote the whole list:",
      );
      console.error('    --skills "elitea-platform,elitea-pipeline"');
    }
    console.error("\n  Re-run with --help to see supported flags.\n");
    process.exit(1);
  }
  return out;
}

function splitList(value) {
  if (!value) return [];
  return value
    .split(",")
    .map((s) => s.trim())
    .filter(Boolean);
}

function printHelp() {
  console.log(`
  elitea-skills installer

  Usage:
    npx github:Bermudas/EliteaSkills init [options]

  Options:
    --all                      Install every agent and every skill (no prompts)
    --agents <a,b|all>         Install only these agents (or all)
    --skills  <a,b|all>        Install only these skills (or all)
    --target <claude,cursor,…> Limit IDE targets (default: all detected)
    --update                   Overwrite existing installs
    --yes                      Skip the interactive "detected IDE" prompt
    -h, --help                 Show this help

  Available agents: ${listDirs("agents").join(", ")}
  Available skills: ${listDirs("skills").join(", ")}

  Examples:
    npx github:Bermudas/EliteaSkills init --all
    npx github:Bermudas/EliteaSkills init --agents elitea-builder
    npx github:Bermudas/EliteaSkills init --skills elitea-platform,elitea-pipeline
    npx github:Bermudas/EliteaSkills init --target claude --update
`);
}

// ---------------------------------------------------------------------------
// Install logic
// ---------------------------------------------------------------------------

function resolveSelection(requested, available, kind) {
  if (requested === null) return null;
  if (requested.length === 0) return [];
  if (requested.length === 1 && requested[0] === "all") return available;
  const unknown = requested.filter((r) => !available.includes(r));
  if (unknown.length) {
    console.error(`  ! Unknown ${kind}: ${unknown.join(", ")}`);
    console.error(`    Available: ${available.join(", ") || "(none)"}`);
    process.exit(1);
  }
  return requested;
}

function copyItem(kind, name, target, update) {
  // kind: "agents" | "skills"; target: {id, dir, label}
  const src = join(PKG_ROOT, kind, name);
  if (!existsSync(src)) return { status: "missing" };

  // GitHub Copilot CLI expects agents as flat `<name>.agent.md` files,
  // not directories. Flatten AGENT.md into a single file.
  if (kind === "agents" && target.id === "copilot") {
    return flattenAgentForCopilot(src, name, target.dir, update);
  }

  const dest = join(CWD, target.dir, kind, name);
  if (existsSync(dest) && !update) return { status: "exists", dest };
  mkdirSync(dirname(dest), { recursive: true });
  cpSync(src, dest, { recursive: true, force: update });
  return { status: "installed", dest };
}

// ---------------------------------------------------------------------------
// Copilot adapter — flat .agent.md files + model alias normalization.
// ---------------------------------------------------------------------------

function transformAgentForCopilot(agentText) {
  // Copilot CLI requires concrete model IDs. Map sdlc-skills style aliases
  // to the canonical Claude model family identifiers. One-line edit on
  // a family bump.
  const COPILOT_MODEL_MAP = {
    sonnet: "claude-sonnet-4-6",
    opus: "claude-opus-4-7",
    haiku: "claude-haiku-4-5",
  };
  return agentText.replace(
    /^model:\s*(sonnet|opus|haiku)\s*$/m,
    (_, alias) => `model: ${COPILOT_MODEL_MAP[alias]}`,
  );
}

function flattenAgentForCopilot(src, name, targetDir, update) {
  const agentFile = join(src, "AGENT.md");
  if (!existsSync(agentFile)) return { status: "missing" };
  const dest = join(CWD, targetDir, "agents", `${name}.agent.md`);
  if (existsSync(dest) && !update) return { status: "exists", dest };

  const agent = transformAgentForCopilot(readFileSync(agentFile, "utf8"));
  mkdirSync(dirname(dest), { recursive: true });
  writeFileSync(dest, agent);
  return { status: "installed", dest };
}

// ---------------------------------------------------------------------------
// Interactive picker
// ---------------------------------------------------------------------------

function ask(rl, q) {
  return new Promise((resolve) => rl.question(q, resolve));
}

async function interactivePick(catalog, args) {
  const detected = TARGETS.filter((t) => existsSync(join(CWD, t.dir)));
  let targets;

  if (args.targets) {
    targets = TARGETS.filter((t) => args.targets.includes(t.id));
    if (targets.length === 0) {
      console.error(`  ! No valid --target values: ${args.targets.join(", ")}`);
      process.exit(1);
    }
  } else if (args.all || args.yes) {
    targets = detected.length > 0 ? detected : [TARGETS[0]];
  } else {
    const rl = createInterface({ input: process.stdin, output: process.stdout });
    try {
      if (detected.length === 0) {
        console.log("  No IDE directories detected. Installing to .claude/");
        targets = [TARGETS[0]];
      } else {
        console.log("  Detected IDE directories:");
        detected.forEach((t, i) =>
          console.log(`    ${i + 1}. ${t.label} (${t.dir}/)`),
        );
        console.log("    a. All of the above\n");
        const choice =
          (await ask(rl, "  Install to which? [a]: ")).trim().toLowerCase() ||
          "a";
        targets =
          choice === "a"
            ? detected
            : [detected[parseInt(choice) - 1] || detected[0]];
      }
    } finally {
      rl.close();
    }
  }

  let agentsSelection = resolveSelection(args.agents, catalog.agents, "agent");
  let skillsSelection = resolveSelection(args.skills, catalog.skills, "skill");

  if (args.all) {
    if (agentsSelection === null) agentsSelection = catalog.agents;
    if (skillsSelection === null) skillsSelection = catalog.skills;
  } else if (agentsSelection === null && skillsSelection === null) {
    console.log(
      "\n  No --agents / --skills specified. Installing full catalog.\n  (Use --agents or --skills to narrow.)",
    );
    agentsSelection = catalog.agents;
    skillsSelection = catalog.skills;
  } else {
    if (agentsSelection === null) agentsSelection = [];
    if (skillsSelection === null) skillsSelection = [];
  }

  return { targets, agentsSelection, skillsSelection };
}

// ---------------------------------------------------------------------------
// Main
// ---------------------------------------------------------------------------

async function main() {
  let argv = process.argv.slice(2);
  // Normalise: `npx pkg init --flag` may or may not pass `init` through
  if (argv[0] === "init") argv = argv.slice(1);

  const args = parseArgs(argv);
  const catalog = loadCatalog();

  console.log("\n  elitea-skills — ELITEA agents and skills for Claude Code\n");
  console.log(
    `  Catalog: ${catalog.agents.length} agent(s), ${catalog.skills.length} skill(s)`,
  );

  if (catalog.agents.length === 0 && catalog.skills.length === 0) {
    console.log(
      "\n  ! This repo has no agents or skills yet. Nothing to install.\n",
    );
    return;
  }

  const { targets, agentsSelection, skillsSelection } = await interactivePick(
    catalog,
    args,
  );

  console.log("");
  let installed = 0;
  let skipped = 0;

  for (const t of targets) {
    console.log(`  → ${t.label} (${t.dir}/)`);
    for (const name of agentsSelection) {
      const r = copyItem("agents", name, t, args.update);
      if (r.status === "installed") {
        console.log(`      ✓ agent  ${name}`);
        installed++;
      } else if (r.status === "exists") {
        console.log(`      — agent  ${name} (exists; use --update)`);
        skipped++;
      } else {
        console.log(`      ! agent  ${name} (missing in repo)`);
      }
    }
    for (const name of skillsSelection) {
      const r = copyItem("skills", name, t, args.update);
      if (r.status === "installed") {
        console.log(`      ✓ skill  ${name}`);
        installed++;
      } else if (r.status === "exists") {
        console.log(`      — skill  ${name} (exists; use --update)`);
        skipped++;
      } else {
        console.log(`      ! skill  ${name} (missing in repo)`);
      }
    }
  }

  console.log(
    `\n  Done: ${installed} installed, ${skipped} skipped.` +
      (installed > 0
        ? "\n  Don't forget to set up .env (see README) for ELITEA_TOKEN."
        : "") +
      "\n",
  );
}

main().catch((err) => {
  console.error("Install failed:", err.message);
  process.exit(1);
});
