---
name: debug-openclaw
description: Debug and operate OpenClaw gateway, sessions, channels, models, and automation. Use this skill whenever anyone asks about OpenClaw—whether troubleshooting or running commands. Covers sessions not responding, bot not responding, "Slow listener detected", "DiscordMessageListener timed out after 30000ms", event queue/lane blocking, "FailoverError", "Unknown model", model fallback failures, channel disconnects, skill loading, "context_length_exceeded", doctor errors; AND operations like systemd service management, CLI commands, config changes, model auth, update/rollback.
---

# Debug & Operate OpenClaw

Comprehensive guide for investigating and operating OpenClaw. This skill teaches you WHERE to look, WHAT to read, and HOW to operate — covering both debugging and day-to-day operations.

## Investigation Flow

When debugging any OpenClaw issue, follow this order:

1. **Understand the symptom** — What is the user experiencing?
2. **Check the right files** — Use the sections below to find the relevant files
3. **Read and analyze** — Open the files, read the content, form your diagnosis
4. **Trace through source** — If needed, read the source code to understand behavior

## Architecture Overview

Read [references/architecture.md](references/architecture.md) for full details. Key concepts:

* **Gateway** — HTTP + WebSocket server (default port 18789) that manages all agent sessions
* **Session** — Each conversation is a `.jsonl` file storing the full transcript
* **Agent** — An AI agent instance with its own config, sessions, identity
* **Pi-Embedded Runner** — The core engine that sends messages to AI providers and handles responses
* **Skills** — Modular extensions loaded from SKILL.md files and injected into the system prompt

## Quick Operations

The most common commands you'll need. For full reference, read [references/cli-reference.md](references/cli-reference.md).

```bash
# Service management (Linux systemd)
systemctl --user status openclaw-gateway      # Is it running?
systemctl --user restart openclaw-gateway     # Restart after config change
journalctl --user -u openclaw-gateway -n 20   # Recent logs

# Fast log search (prefer over journalctl for large logs)
tail -500 /tmp/openclaw/openclaw-$(date +%Y-%m-%d).log | grep -E "error|timeout|Slow"

# Channel and model status
openclaw channels status --probe              # Channel connectivity
openclaw doctor                               # Full health check
openclaw skills status                        # List loaded skills
openclaw --version                            # Check installed version
```

## Additional References

* **CLI & Operations** — Read [references/cli-reference.md](references/cli-reference.md) for all CLI commands, gateway lifecycle, systemd service management, update/rollback, and a quick diagnostic cheatsheet.
* **Config file formats** — Read [references/config-formats.md](references/config-formats.md) when you need to understand or modify `openclaw.json`, `models.json`, `sessions.json`, or session JSONL transcripts. Includes session key format patterns.
* **Common operational tasks** — Read [references/common-tasks.md](references/common-tasks.md) for step-by-step guides: finding sessions by group name, tracing skill invocations, adding custom model providers, verifying model config, diagnosing channel issues, understanding agent bindings.
* **Debug checklist** — Read [references/debug-checklist.md](references/debug-checklist.md) for symptom-based diagnosis (gateway won't start, session not responding, skill not loading, channel disconnected, config issues, doctor errors).
* **Lane & execution diagnostics** — Read [references/lane-diagnostics.md](references/lane-diagnostics.md) for event queue blocking, subagent lane blocking, model fallback failures, and diagnostic command benchmarks.
* **Official docs (local source)** — The local repo at `~/github/openclaw/docs/` is the source for https://docs.openclaw.ai/. For deep troubleshooting:
  * `help/troubleshooting.md` — Triage decision tree with error signatures
  * `gateway/doctor.md` — All 19 doctor checks explained in detail
  * `help/debugging.md` — Debug overrides, raw stream logging, watch mode
  * `help/faq.md` — Comprehensive FAQ

## Where to Look by Problem Type

### Session Issues

**Goal: Understand what happened in a conversation**

| What to check | Where to find it |
|----------------|-----------------|
| Session transcripts | `~/.openclaw/agents/<agentId>/sessions/*.jsonl` |
| Session index | `~/.openclaw/agents/<agentId>/sessions/sessions.json` |
| Session key mapping | Read `sessions.json` to find which `.jsonl` maps to which chat |
| What agent ID to use | System prompt `Runtime` line contains `agent=<id>` |

**How to read a session JSONL:**

* Each line is a JSON object
* `type: "session"` = session metadata (model, auth profile, timestamp)
* `type: "message"` + `message.role: "user"` = user messages
* `type: "message"` + `message.role: "assistant"` = AI responses
* `message.content[].type: "toolCall"` = tool invocations
* `message.content[].type: "toolResult"` = tool results (check `isError`)
* `message.usage.cost.total` = cost per response

**Source code to read for deeper understanding:**

* `src/gateway/session-utils.ts` — Session resolution, store loading
* `src/gateway/session-utils.fs.ts` — Session file I/O (read/write transcript)
* `src/agents/session-transcript-repair.ts` — How transcript corruption is handled
* `src/agents/session-write-lock.ts` — Session concurrency control

---

### Model & Auth Issues

**Goal: Verify model configuration and API authentication**

| What to check | Where to find it |
|----------------|-----------------|
| Main config | `~/.openclaw/openclaw.json` — look at `agents.<id>.model`, `agents.<id>.modelProvider` |
| Model overrides | `~/.openclaw/models.json` (if exists) — custom provider/model definitions |
| Auth profiles | Config `agents.<id>.authProfiles` — multiple API key rotation |
| Environment API keys | `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `GOOGLE_API_KEY` etc. |
| Credentials store | `~/.openclaw/credentials/` |
| Session-level model info | In `.jsonl` first line: `type: "session"` contains active model |

**What to look for in config:**

* `model` — The model ID (e.g., `claude-sonnet-4-20250514`)
* `modelProvider` — Provider name (e.g., `anthropic`, `openai`, `google`)
* `authProfiles` — Array of API key configs for rotation on failure
* `modelFallback` — Fallback model if primary fails

**Source code to read for deeper understanding:**

* `src/agents/model-selection.ts` — How the model is chosen
* `src/agents/model-auth.ts` — How auth is resolved for each request
* `src/agents/model-fallback.ts` — Fallback logic on provider failure
* `src/agents/auth-profiles/` — Auth profile rotation mechanism
* `src/agents/models-config.providers.ts` — Provider endpoint/URL configuration
* `src/agents/cli-credentials.ts` — Credential storage and retrieval

---

### Event Queue / Lane Issues

**Goal: Understand why messages are being dropped or delayed across channels**

| What to check | Where to find it |
|----------------|-----------------|
| Listener timeouts | `journalctl --user -u openclaw-gateway` — grep for `timed out\|Slow listener` |
| Lane task duration | Same logs — grep for `lane task done\|lane task error` — shows which session is blocking and for how long |
| Blocking channel ID | `lane task` log lines contain `lane=session:agent:main:discord:channel:<ID>` |
| Session lookup | `jq '."agent:main:discord:channel:<ID>"' ~/.openclaw/agents/main/sessions/sessions.json` |
| Active subagent runs | `~/.openclaw/subagents/runs.json` |
| Subagent model config | `~/.openclaw/openclaw.json` → `agents.defaults.subagents.model` |
| Model fallback config | `~/.openclaw/openclaw.json` → `agents.defaults.model.fallbacks` |
| Running subagent processes | `ps -eo pid,etime,args \| grep -E "prep_funday\|notebooklm\|doppler"` |

**Key insight:** OpenClaw's main lane is **serial** — one slow run blocks all channels. A 30-second listener timeout means dropped messages. See [references/lane-diagnostics.md](references/lane-diagnostics.md) for detailed diagnosis steps, command benchmarks, and resolution strategies.

---

### Channel Issues

**Goal: Verify messaging channel (Telegram/Discord/Slack/etc.) connectivity**

| What to check | Where to find it |
|----------------|-----------------|
| Channel config | `~/.openclaw/openclaw.json` — `telegram`, `discord`, `slack` sections |
| Channel status | Run `openclaw channels status --probe` |
| Bot tokens | Config fields or env vars: `DISCORD_BOT_TOKEN`, `TELEGRAM_BOT_TOKEN`, etc. |
| Webhook settings | Channel-specific config sections |
| Gateway logs | `/tmp/openclaw-gateway.log` or macOS unified logs via `scripts/clawlog.sh` |

**What to look for in config:**

* Each channel has its own top-level config section (e.g., `telegram: { botToken: "..." }`)
* Check if token is present and not empty
* Check if the channel is enabled (not explicitly disabled)
* Check gateway mode: `gateway.mode` should be `"local"` for local setup

**Source code to read for deeper understanding:**

* `src/gateway/server-channels.ts` — Channel connection management
* `src/gateway/channel-health-monitor.ts` — Health check logic
* `src/telegram/`, `src/discord/`, `src/slack/` — Channel-specific code

---

### Skill Loading Issues

**Goal: Verify a skill is correctly loaded and available to the agent**

| What to check | Where to find it |
|----------------|-----------------|
| Skill status | Run `openclaw skills status` |
| SKILL.md frontmatter | Open the SKILL.md, check `name` and `description` between `---` markers |
| Skill file size | Must be ≤ 256KB per SKILL.md |
| Skill directories scanned | `.agents/skills/`, `.agent/skills/`, `_agents/skills/`, `_agent/skills/` in workspace |
| Managed skills dir | `~/.openclaw/skills/` |
| Skills config | `~/.openclaw/openclaw.json` → `skills` section |

**Rules the loader enforces:**

* SKILL.md must have valid YAML frontmatter with `name` and `description`
* `name`: lowercase, digits, hyphens only, ≤64 chars
* Max 150 skills in prompt, max 30,000 total chars
* Max 300 candidates scanned per root directory
* Skills are deduplicated by name (workspace skills win over managed/bundled)

**Source code to read for deeper understanding:**

* `src/agents/skills/workspace.ts` → `loadSkillEntries()` — The main loading pipeline
* `src/agents/skills/frontmatter.ts` — How YAML frontmatter is parsed and validated
* `src/agents/skills/types.ts` — `SkillEntry`, `SkillSnapshot` type definitions
* `src/agents/skills/config.ts` — Skill config resolution
* `src/agents/system-prompt.ts` → `buildSkillsSection()` — How skills are injected into the system prompt

---

### Gateway Issues

**Goal: Understand why the gateway won't start or behaves unexpectedly**

| What to check | Where to find it |
|----------------|-----------------|
| Gateway config | `~/.openclaw/openclaw.json` → `gateway` section |
| Default port | 18789 (check `gateway.port` in config) |
| Gateway logs | `/tmp/openclaw-gateway.log` |
| macOS logs | Run `scripts/clawlog.sh` |
| Port occupancy | `lsof -i :18789` |
| Running processes | `pgrep -f "openclaw.*gateway"` |
| Node version | `node --version` (must be 22+) |
| Doctor diagnostic | `openclaw doctor` |

**Source code to read for deeper understanding:**

* `src/gateway/server.impl.ts` → `startGatewayServer()` — Main entry point
* `src/gateway/server-http.ts` — HTTP route registration
* `src/gateway/config-reload.ts` — Config hot-reload mechanism
* `src/config/paths.ts` — How paths (config, state dir) are resolved
* `src/infra/ports.ts` — Port availability checking

---

### Browser / Playwright Issues

**Goal: Understand browser automation failures**

| What to check | Where to find it |
|----------------|-----------------|
| Chrome debug endpoint | `curl -s http://localhost:9222/json/list` |
| Chrome processes | `pgrep -f "chrome\|chromium"` |
| Target/session ID | The `/json/list` response shows current page targets |

**Key concept:** Chrome's `targetId` changes when pages navigate. The code re-fetches from `/json/list` to handle this.

**Source code to read for deeper understanding:**

* `src/browser/` — All browser automation code
* `src/gateway/server-browser.ts` — Gateway's browser session management

---

### Config System

**Goal: Understand how configuration is loaded and which file is active**

| What to check | Where to find it |
|----------------|-----------------|
| Active config | `~/.openclaw/openclaw.json` (JSON5 format, supports comments) |
| Legacy configs | `~/.clawdbot/clawdbot.json`, `~/.moldbot/moldbot.json` |
| Override env vars | `OPENCLAW_CONFIG_PATH`, `OPENCLAW_STATE_DIR`, `OPENCLAW_HOME` |
| Config audit log | `~/.openclaw/config-audit.jsonl` |
| Config schema | Read `src/config/schema.ts` for all valid config fields |

**Resolution order:**

1. `OPENCLAW_CONFIG_PATH` env var (explicit override)
2. `$OPENCLAW_STATE_DIR/openclaw.json`
3. Legacy paths (auto-migrated)

**Source code to read for deeper understanding:**

* `src/config/io.ts` — Config read/write logic, JSON5 parsing
* `src/config/paths.ts` — Path resolution logic
* `src/config/defaults.ts` — Default config values
* `src/config/validation.ts` — Config validation
* `src/config/schema.ts` + `src/config/zod-schema.ts` — Full config schema
