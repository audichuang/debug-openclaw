# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Repository Is

This is a **Claude Code skill** for debugging and operating the OpenClaw AI gateway. It is loaded by OpenClaw at runtime and injected into the agent's system prompt. There are no build steps, tests, or compilation — changes to `.md` files take effect immediately after OpenClaw reloads the skill.

## Skill Structure

```
SKILL.md                    ← Entry point: frontmatter + investigation guide
references/
  architecture.md           ← OpenClaw source code map and system design
  cli-reference.md          ← All CLI commands, systemd management, update/rollback
  common-tasks.md           ← Step-by-step operational guides
  debug-checklist.md        ← Symptom-based diagnostic checklists
  config-formats.md         ← openclaw.json, models.json, sessions.json formats
```

`SKILL.md` is always loaded. The `references/` files are linked from `SKILL.md` and read on demand — they are NOT automatically in context, so `SKILL.md` must clearly direct Claude to read them.

## Skill Frontmatter Rules

The YAML frontmatter at the top of `SKILL.md` controls how OpenClaw loads and triggers this skill:

- Must be delimited by `---` lines
- `name`: lowercase, digits, hyphens only, ≤64 chars
- `description`: ≤1024 chars — this is the **trigger mechanism** (OpenClaw reads all skill descriptions and decides which to invoke based on user intent)
- File size must be ≤256KB

Validate that the frontmatter is well-formed after any edits to the top of `SKILL.md`.

## How OpenClaw Uses Skills

1. OpenClaw scans skill directories (`.agents/skills/`, `~/.openclaw/skills/`, etc.) for `SKILL.md` files
2. Frontmatter `name` + `description` are injected into the agent system prompt
3. When the agent decides a skill is relevant, it reads the full `SKILL.md` body
4. The skill instructs the agent to read specific `references/` files based on the problem type
5. Skills are deduplicated by name — workspace skills override managed/bundled ones

## Editing Guidelines

- **`SKILL.md`**: The "where to look" guide. Should tell Claude which files to read, not reproduce their content. Keep it as a routing layer.
- **`references/` files**: Contain the actual detailed information. These can be longer and more detailed since they're only loaded when needed.
- When adding a new reference file, add a link to it in the "Additional References" section of `SKILL.md`.
- The main diagnostic flow in `SKILL.md` must remain under 200 lines to avoid truncation in OpenClaw's skill prompt (the body is loaded in full, but keeping it focused helps).

## Key OpenClaw Concepts (for editing reference content accurately)

- **Gateway**: HTTP + WebSocket server on port 18789, manages all agent sessions
- **Lane**: Serial execution queue per session — one slow run blocks all channels for that agent
- **Session key format**: `agent:<agentId>:<channel>:<type>:<id>` (e.g., `agent:main:discord:channel:123`)
- **Config file**: `~/.openclaw/openclaw.json` (JSON5 format — supports comments and trailing commas)
- **Log file**: `/tmp/openclaw/openclaw-YYYY-MM-DD.log` (faster than journalctl for large logs)
- **Doctor**: `openclaw doctor` runs 19 health checks; `--repair` auto-fixes; can overwrite the systemd `.service` file
- **Hot-reloadable config**: `agents.defaults.model` and subagent model; channel tokens and port changes require restart
