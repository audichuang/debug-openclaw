# OpenClaw Debug Checklist

When investigating a specific symptom, go to the matching section. Each section tells you what files to read and what to look for.

## Table of Contents

* [Gateway Won't Start](#gateway-wont-start)
* [Session Not Responding](#session-not-responding)
* [Session Transcript Corrupted](#session-transcript-corrupted)
* [Skill Not Loading or Not Triggering](#skill-not-loading-or-not-triggering)
* [Model or Auth Failures](#model-or-auth-failures)
* [Browser Automation Broken](#browser-automation-broken)
* [Channel Disconnected](#channel-disconnected)
* [Config Not Taking Effect](#config-not-taking-effect)
* [Event Queue Blocking / Lane Congestion](#event-queue-blocking--lane-congestion)
* [Subagent Blocking Main Lane](#subagent-blocking-main-lane)
* [Model Fallback Not Working](#model-fallback-not-working)
* [Doctor Errors and Warnings](#doctor-errors-and-warnings)

***

## Gateway Won't Start

**Read these files to understand:**

1. Open `~/.openclaw/openclaw.json` — check if `gateway` section exists and has valid settings
2. Check `gateway.port` — default is 18789. If another process uses it, the gateway can't bind
3. Read `src/gateway/server.impl.ts` → `startGatewayServer()` to understand what happens at startup
4. Read `src/infra/ports.ts` → `ensurePortAvailable()` to understand port conflict detection
5. Check Node version — must be 22+

**Things to look for in config:**

* `gateway.mode` — should be `"local"` for local setup
* `gateway.port` — check for conflicts
* Syntax errors — the file is JSON5 (supports comments and trailing commas) but still has rules

***

## Session Not Responding

**Read these files to understand:**

1. Find the session file: open `~/.openclaw/agents/<agentId>/sessions/sessions.json` → find the session key → locate the `.jsonl` file
2. Open the `.jsonl` file → read the last few lines:
   * Is the last message from `user`? → The AI never responded
   * Is there a `toolCall` without matching `toolResult`? → Tool execution stuck
   * Is there an error message in the assistant's response? → Read the error
3. Check the first `type: "session"` line → what `model` and `authProfile` was used?
4. Read `src/agents/session-write-lock.ts` — is there a stale write lock preventing new writes?
5. Read `src/agents/compaction.ts` — did the context window fill up? Look for compaction entries in the transcript
6. Read `src/agents/pi-embedded-runner/` — the AI execution engine. Errors here mean provider issues

**Common patterns in session logs:**

* `"billing"` or `"rate_limit"` in error text → API quota issue
* `"unauthorized"` or `"forbidden"` → API key problem
* `"context_length_exceeded"` → context window overflow, compaction should trigger
* Repeated `toolCall` → `toolResult(error)` → same `toolCall` → tool loop detected by `src/agents/tool-loop-detection.ts`

***

## Session Transcript Corrupted

**Read these files to understand:**

1. Open the `.jsonl` file — check if any lines are incomplete (truncated JSON)
2. Read `src/agents/session-transcript-repair.ts` — this is the auto-repair logic. It handles:
   * Truncated lines (incomplete JSON)
   * Duplicate entries
   * Out-of-order messages
3. Read `src/agents/session-file-repair.ts` — file-level repair (missing headers, encoding)
4. Check if deleted sessions exist: look for `.deleted.<timestamp>` suffix files

**Likely causes:** Process killed during write, disk full, concurrent writes without lock

***

## Skill Not Loading or Not Triggering

**Read these files to understand:**

1. Open the SKILL.md in question — check frontmatter format:
   * Must start with `---`, have `name:` and `description:`, end with `---`
   * `name` must be lowercase, digits, hyphens only, ≤64 chars
   * `description` must not be empty, ≤1024 chars
2. Read `src/agents/skills/frontmatter.ts` → see exactly how frontmatter is parsed and what errors are caught
3. Read `src/agents/skills/workspace.ts` → `loadSkillEntries()`:
   * See which directories are scanned
   * See how skills are deduplicated (same name: workspace wins)
   * Check limit constants: max 150 skills, 30000 chars, 256KB per file
4. Read `src/agents/system-prompt.ts` → `buildSkillsSection()` — how the skill prompt is injected. If the prompt is truncated, some skills may be dropped

**Not triggering but loaded?** The `description` is the trigger mechanism. Claude reads all skill descriptions and decides which to use. If the description doesn't clearly match the user's intent, it won't trigger.

***

## Model or Auth Failures

**Read these files to understand:**

1. Open `~/.openclaw/openclaw.json` → find `agents.<agentId>` section:
   * `model` — the model ID
   * `modelProvider` — the provider
   * `authProfiles` — array of auth configs
2. Read `src/agents/model-selection.ts` → how the model is chosen. Follows: session override → agent config → default
3. Read `src/agents/model-auth.ts` → how auth is resolved. Follows: auth profile → env var → credentials file
4. Read `src/agents/auth-profiles/` → understand rotation logic:
   * On failure/rate-limit → next profile is tried
   * Cooldown period after failures
   * Read `src/agents/auth-profiles.cooldown-auto-expiry.test.ts` for behavior examples
5. Read `src/agents/model-fallback.ts` → fallback logic when primary model is unavailable
6. Check `~/.openclaw/models.json` (if exists) → custom provider definitions with `baseUrl`

***

## Browser Automation Broken

**Read these files to understand:**

1. Check if Chrome is running with `--remote-debugging-port=9222`
2. Try `curl -s http://localhost:9222/json/list` — if this fails, Chrome debug protocol is not accessible
3. If it returns data, read the `id` and `title` fields — these are the available page targets
4. Read `src/browser/` — the browser automation module
5. Read `src/gateway/server-browser.ts` — how the gateway manages browser sessions

**Key insight:** Chrome's `targetId` changes when pages navigate or reload. The code fetches from `/json/list` to get the current target. If old target IDs are cached, operations will fail with "Session with given id not found".

***

## Channel Disconnected

**Read these files to understand:**

1. Open `~/.openclaw/openclaw.json` → find the channel section (e.g., `telegram`, `discord`, `slack`)
2. Check if the bot token is present and looks valid (not empty, not truncated)
3. Read `src/gateway/server-channels.ts` → how channels are initialized and connected
4. Read `src/gateway/channel-health-monitor.ts` → how health checks work
5. For specific channels:
   * Telegram: `src/telegram/` — check webhook config, bot token format
   * Discord: `src/discord/` — check bot token, guild permissions
   * Slack: `src/slack/` — check bot token + app token (both needed)

**Env vars to check:** `DISCORD_BOT_TOKEN`, `SLACK_BOT_TOKEN`, `SLACK_APP_TOKEN` — these override config values

***

## Config Not Taking Effect

**Quick check (3.2+):** Run `openclaw config validate` first — it catches syntax errors and invalid keys before you dig deeper.

**Read these files to understand:**

1. Validate config syntax: `openclaw config validate --json` (3.2+)
2. Confirm which config file is actually loaded:
   * Run `openclaw config file` to see the resolved path (3.1+)
   * Check `OPENCLAW_CONFIG_PATH` env var — if set, this overrides everything
   * Check `OPENCLAW_STATE_DIR` — determines the state directory
   * Default: `~/.openclaw/openclaw.json`
2. Check for legacy configs: `~/.clawdbot/clawdbot.json` — if this exists, it may be loaded instead
3. Read `src/config/io.ts` → full config loading logic, including JSON5 parsing
4. Read `src/config/paths.ts` → `resolveConfigPath()` to understand the resolution order
5. Read `src/gateway/config-reload.ts` → hot-reload: some changes apply without restart, others require restart
6. Check `~/.openclaw/config-audit.jsonl` — every config write is logged here with before/after

**Common issue:** Multiple config files exist (legacy migration). The resolution logic checks multiple paths. Read `resolveConfigPath()` to see exactly which file wins.

***

## Event Queue Blocking / Lane Congestion

**Symptom:** Messages drop with `DiscordMessageListener timed out after 30000ms` or `Slow listener detected`. Bot appears stuck / typing but never responds.

**Root cause:** OpenClaw's main lane is shared — one slow session blocks ALL other channels. The `DiscordMessageListener` has a 30-second hard timeout; exceeded = message silently dropped.

➜ **Read [lane-diagnostics.md](lane-diagnostics.md#event-queue-blocking--lane-congestion)** for full diagnosis steps, command benchmarks, common causes, and resolution strategies.

***

## Subagent Blocking Main Lane

**Symptom:** Same as above, but caused by subagent announce retries. You see `Subagent announce ... retrying N/4 ... gateway timeout after 60000ms` — each cycle = 60s blocking, 4 retries = 240+ seconds.

**Key:** Subagent model (`agents.defaults.subagents.model`) is separate from session model. Discord `/models` command does NOT change the subagent model.

➜ **Read [lane-diagnostics.md](lane-diagnostics.md#subagent-blocking-main-lane)** for diagnosis and config fix.

***

## Model Fallback Not Working

**Symptom:** Primary model fails but agent doesn't fall back. You see `FailoverError` wrapping the primary model's error, or `Unknown model: <provider>/<model>` in logs.

**Quick check:** Are fallbacks from multiple providers? Is each provider authenticated? Is each model ID registered?

➜ **Read [lane-diagnostics.md](lane-diagnostics.md#model-fallback-not-working)** for full misconfiguration patterns and diagnostic commands.

***

## Doctor Errors and Warnings

**Symptom:** `openclaw doctor` reports errors, warnings, or migration notices. Or other commands say "please run `openclaw doctor` first."

**CLI flags:**

```bash
openclaw doctor                    # Interactive mode (prompts for repairs)
openclaw doctor --repair           # Auto-apply recommended fixes without prompting
openclaw doctor --repair --force   # Aggressive: overwrites custom supervisor configs too
openclaw doctor --deep             # Scan for extra gateway installs (launchd/systemd)
openclaw doctor --yes              # Accept all default prompts
openclaw doctor --non-interactive  # Only safe migrations, skip restart/service actions
```

**What doctor checks (19 steps in order):**

| # | Check | What it means if it warns |
|---|-------|--------------------------|
| 1 | Config normalization | Legacy config shapes found, doctor will auto-migrate |
| 2 | Legacy config key migrations | Deprecated keys → `run doctor` to migrate (e.g. `routing.*` → `channels.*`) |
| 3 | Legacy state migrations | Old disk layout → sessions/agent dirs need moving |
| 4 | State integrity | State dir missing, permissions wrong, transcript files orphaned |
| 5 | Model auth health | OAuth tokens expired/expiring, auth profiles in cooldown/disabled |
| 6 | Hooks model validation | `hooks.gmail.model` references invalid model |
| 7 | Sandbox image repair | Docker image missing for sandbox mode |
| 8 | Gateway service migrations | Legacy launchd/systemd service → needs update |
| 9 | Security warnings | DM policy open without allowlist |
| 10 | systemd linger | Linux: linger not enabled → gateway dies after logout |
| 11 | Skills status | Skills blocked/missing/eligibility issues |
| 12 | Gateway auth | No `gateway.auth.token` set (offers to generate) |
| 13 | Gateway health + restart | Gateway unhealthy → offers restart |
| 14 | Channel status | Channels disconnected/errored |
| 15 | Supervisor config audit | systemd/launchd config outdated (e.g. missing restart delay) |
| 16 | Gateway runtime + port | Service installed but not running, port 18789 collision |
| 17 | Runtime best practices | Running on Bun instead of Node, or version-manager path (nvm/fnm) |
| 18 | Config write | Persists changes and stamps wizard metadata |
| 19 | Workspace tips | Memory system missing, workspace not under git |

**Common doctor-reported issues and fixes:**

| Issue | What to do |
|-------|-----------|
| `legacy config keys found` | Let doctor auto-migrate, or manually update `openclaw.json` per the migration map |
| `OAuth token expired` | Run interactively to refresh, or `openclaw models auth add --provider <name>` |
| `auth profile in cooldown` | Wait for cooldown to expire, or check if API key/billing is valid |
| `state dir permissions` | `chmod 700 ~/.openclaw` + `chmod 600 ~/.openclaw/openclaw.json` |
| `systemd linger not enabled` | `loginctl enable-linger $(whoami)` |
| `gateway service not running` | `systemctl --user start openclaw-gateway` |
| `supervisor config outdated` | Run `openclaw doctor --repair` or `openclaw gateway install --force` |
| `port 18789 in use` | `lsof -i :18789` to find the conflicting process |
| `nvm/fnm path detected` | Doctor may suggest migrating to system Node to avoid path issues after upgrades |
| `service file overwritten` | **⚠️ `openclaw doctor` can overwrite your `.service` file!** Always use `override.conf` for customizations |

**⚠️ Important caveat:** `openclaw doctor --repair` and `--force` can overwrite the systemd service file at `~/.config/systemd/user/openclaw-gateway.service`. If you have custom `EnvironmentFile=` or other settings, **always** put them in `override.conf` (see [cli-reference.md](cli-reference.md#systemd-service-files)).

**Deep troubleshooting:** For full details, read the local docs source:
- **Doctor internals:** `~/github/openclaw/docs/gateway/doctor.md` (284 lines, all 19 check steps explained)
- **Troubleshooting triage:** `~/github/openclaw/docs/help/troubleshooting.md` (decision tree + error signatures)
- **Official docs:** https://docs.openclaw.ai/

> **Note:** The local docs at `~/github/openclaw/docs/` are the source for `docs.openclaw.ai`. If you need deeper troubleshooting beyond this checklist, read the relevant markdown files there directly.
