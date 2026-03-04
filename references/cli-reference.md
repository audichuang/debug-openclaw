# OpenClaw CLI & Operations Reference

Quick reference for CLI commands, gateway API, and systemd service management.

## Core CLI Commands

```bash
openclaw onboard              # Run onboarding wizard
openclaw doctor               # Validate install and health
openclaw status               # Show global status
openclaw version              # Print CLI version
openclaw dashboard            # Open dashboard URL
openclaw config --list        # List all config values
openclaw config --get <key>   # Get specific config value
openclaw config --set <k=v>   # Set config value (avoids manual JSON editing)
openclaw config validate      # Validate config files before gateway startup (3.2+)
openclaw config validate --json  # Same, with JSON output
openclaw config file          # Print active config file path (3.1+)
openclaw update               # Update CLI to latest
```

## Gateway Lifecycle

```bash
# CLI commands
openclaw gateway              # Start gateway in foreground
openclaw gateway status       # Show runtime status
openclaw gateway health       # Check health endpoint
openclaw gateway restart      # Restart managed gateway
openclaw gateway stop         # Stop managed gateway
openclaw gateway install      # Install background service
openclaw gateway uninstall    # Remove background service
openclaw gateway call <path>  # Call gateway API directly (e.g. debug endpoints)

# systemd (Linux — the actual production setup)
systemctl --user start openclaw-gateway
systemctl --user stop openclaw-gateway
systemctl --user restart openclaw-gateway
systemctl --user status openclaw-gateway
systemctl --user enable openclaw-gateway    # Auto-start on login

# View logs (most common debugging entry point)
journalctl --user -u openclaw-gateway -n 50 --no-pager
journalctl --user -u openclaw-gateway --since "1 hour ago" --no-pager
journalctl --user -u openclaw-gateway -f    # Follow live

# Direct log file (faster than journalctl for large logs)
tail -500 /tmp/openclaw/openclaw-$(date +%Y-%m-%d).log | grep "pattern"
```

### systemd Service Files

| File | Purpose |
|------|---------|
| `~/.config/systemd/user/openclaw-gateway.service` | Main service definition (may be overwritten by `openclaw doctor`) |
| `~/.config/systemd/user/openclaw-gateway.service.d/override.conf` | Persistent overrides (survives `openclaw doctor`) |
| `~/.config/openclaw/gateway.env` | Environment variables (API keys via `EnvironmentFile=`) |

**Important:** `openclaw doctor` can overwrite the main `.service` file. Put customizations in `override.conf`:

```ini
# ~/.config/systemd/user/openclaw-gateway.service.d/override.conf
[Service]
EnvironmentFile=/home/<user>/.config/openclaw/gateway.env
```

**Best practice — what goes where:**

| Setting | Where | Why |
|---------|-------|-----|
| `ExecStart` (Node/openclaw path) | Main `.service` — let doctor manage | Path changes on every update |
| `Restart`, `RestartSec`, `KillMode` | Main `.service` — let doctor manage | Doctor updates best defaults |
| `OPENCLAW_GATEWAY_TOKEN` | `gateway.env` | Must survive doctor rewrites |
| API keys (`JINA_API_KEY`, etc.) | `gateway.env` | Same — never in .service |
| `EnvironmentFile=` | `override.conf` | Links .service → gateway.env |

After editing service files:
```bash
systemctl --user daemon-reload
systemctl --user restart openclaw-gateway
```

## Channel Commands

```bash
openclaw channels list                    # List configured channels
openclaw channels status --probe          # Check channel connectivity (most useful for debugging)
openclaw channels login --channel <name>  # Authenticate a channel
openclaw channels logout --channel <name> # Disconnect a channel
```

**Channel env vars override config:**
- `DISCORD_BOT_TOKEN`
- `TELEGRAM_BOT_TOKEN`
- `SLACK_BOT_TOKEN` + `SLACK_APP_TOKEN` (both required)

## Model Commands

```bash
openclaw models list                          # Show available models
openclaw models                               # Alias for list — shows full model + auth overview
openclaw models status                        # Compact status (configured models, auth, OAuth status)
openclaw models set <model>                   # Set default model
openclaw models auth add --provider <name>    # Add provider auth (OAuth flow)
openclaw models auth list                     # Show provider auth entries
openclaw models auth remove --provider <name> # Remove provider auth
openclaw models fallbacks list                # Show current fallback chain
openclaw models fallbacks add <model>         # Add model to fallbacks (e.g. my-proxy/gpt-4o)
openclaw models fallbacks remove <model>      # Remove model from fallbacks
openclaw models fallbacks clear               # Clear all fallbacks
openclaw models aliases list                  # List model aliases
openclaw models aliases add <alias> <model>   # Create alias
openclaw models scan                          # Discover local models (Ollama, etc.)
```

## Automation & Advanced Tools

```bash
# Cron
openclaw cron list              # List scheduled jobs
openclaw cron add ...           # Create cron job
openclaw cron run <jobId>       # Run job immediately
openclaw cron remove <jobId>    # Delete job

# Browser
openclaw browser status         # Check browser runtime
openclaw browser start          # Start managed browser
openclaw browser open <url>     # Navigate to URL
openclaw browser screenshot     # Capture screenshot
openclaw browser stop           # Stop browser

# Plugins
openclaw plugins list           # List installed plugins
openclaw plugins install <src>  # Install plugin
openclaw plugins enable <name>  # Enable plugin
openclaw plugins disable <name> # Disable plugin

# Skills
openclaw skills status          # List loaded skills and their status
```

## Quick Diagnostic Cheatsheet

The most common diagnostic commands, ordered by how often you'll use them:

```bash
# 1. Is the gateway running?
systemctl --user status openclaw-gateway

# 2. What's happening right now?
journalctl --user -u openclaw-gateway -n 20 --no-pager

# 3. Are channels connected?
openclaw channels status --probe

# 4. Is there a lane blocking issue?
tail -500 /tmp/openclaw/openclaw-$(date +%Y-%m-%d).log | grep -E "Slow listener|timed out|lane task"

# 5. Which session is blocking?
jq -r '."agent:main:discord:channel:<ID>" | {sessionId, groupChannel, model}' \
  ~/.openclaw/agents/main/sessions/sessions.json

# 6. What model/provider is a session using?
tail -1 ~/.openclaw/agents/main/sessions/<sessionId>.jsonl | jq '{model: .model, provider: .modelProvider}'

# 7. Validate config syntax
openclaw config validate

# 8. Full health check
openclaw doctor
```

## Update & Rollback

### Update OpenClaw

```bash
# 1. Check current version
openclaw version

# 2. Stop gateway before updating
systemctl --user stop openclaw-gateway

# 3. Update CLI (npm global package)
npm install -g openclaw@latest

# 4. Verify new version
openclaw version

# 5. Run doctor to validate (may overwrite .service file!)
openclaw doctor

# 6. If doctor overwrote .service, re-apply customizations
# Check if override.conf still has your EnvironmentFile:
cat ~/.config/systemd/user/openclaw-gateway.service.d/override.conf

# 7. Reload systemd and restart
systemctl --user daemon-reload
systemctl --user start openclaw-gateway

# 8. Verify everything works
systemctl --user status openclaw-gateway
openclaw channels status --probe
```

### Rollback to a specific version

```bash
systemctl --user stop openclaw-gateway
npm install -g openclaw@<version>   # e.g. openclaw@2.24.0
openclaw version                     # Confirm rollback
systemctl --user daemon-reload
systemctl --user start openclaw-gateway
openclaw doctor                      # Re-validate
```

### Check available versions

```bash
npm view openclaw versions --json | tail -5
```

## Config Editing

### Hot-reload vs restart

OpenClaw watches `~/.openclaw/openclaw.json` for changes. Some settings apply immediately (hot-reload), others require a gateway restart.

**Hot-reloadable** (no restart needed):
- `agents.defaults.model` (primary + fallbacks)
- `agents.defaults.subagents.model`
- Model provider settings

**Requires restart:**
- Gateway port/bind changes
- Channel token changes
- Plugin additions

### Editing config safely

```bash
# Option 1: Use CLI (safest, validates input)
openclaw config --set agents.defaults.model.primary=google/gemini-3-flash-preview

# Option 2: Edit JSON directly (supports JSON5 comments + trailing commas)
nano ~/.openclaw/openclaw.json

# Option 3: Use jq for precise edits
jq '.agents.defaults.model.primary = "google/gemini-3-flash-preview"' \
  ~/.openclaw/openclaw.json > /tmp/oc.json && mv /tmp/oc.json ~/.openclaw/openclaw.json
```

### Verify config took effect

```bash
# Check if hot-reload picked up the change
journalctl --user -u openclaw-gateway -n 5 --no-pager | grep "config change"

# If not, restart
systemctl --user restart openclaw-gateway
```

## Session Management

```bash
# List all active sessions
timeout 10 jq -r 'to_entries[] | "\(.key) → \(.value.displayName // "unnamed") [\(.value.model)]"' \
  ~/.openclaw/agents/main/sessions/sessions.json

# Check session details
timeout 10 jq -r '."<session-key>" | {sessionId, groupChannel, model, modelProvider, inputTokens, outputTokens}' \
  ~/.openclaw/agents/main/sessions/sessions.json

# Read last messages in a session
tail -5 ~/.openclaw/agents/main/sessions/<sessionId>.jsonl | \
  python3 -c "import sys,json;[print(json.loads(l).get('timestamp',''), json.loads(l).get('message',{}).get('role',''), json.loads(l).get('type','')) for l in sys.stdin]"

# Check subagent status
jq . ~/.openclaw/subagents/runs.json 2>/dev/null || echo "No active subagent runs"
```

## Tailscale Remote Access

If the gateway is exposed via Tailscale:

```bash
# Check Tailscale status
tailscale status

# Gateway should be accessible at:
# https://<hostname>.tail<id>.ts.net/

# Verify serve is configured
tailscale serve status
```
