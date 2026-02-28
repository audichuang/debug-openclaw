# OpenClaw Common Tasks

Step-by-step guides for operational tasks that go beyond basic debugging.

## Table of Contents

* [Find Session by Group/Channel Name](#find-session-by-groupchannel-name)
* [Trace Skill Invocation in a Session](#trace-skill-invocation-in-a-session)
* [Add a Custom Model Provider](#add-a-custom-model-provider)
* [Verify Model Configuration](#verify-model-configuration)
* [Check Why a Channel Is Offline](#check-why-a-channel-is-offline)
* [Understand Agent Binding (Group → Agent Routing)](#understand-agent-binding)

***

## Find Session by Group/Channel Name

**Goal:** Given a group name (e.g., "My Telegram Group"), find the session transcript.

### Steps

1. **Determine the agent ID:**
   * Read `~/.openclaw/openclaw.json` → `agents.list` → find the relevant agent `id`
   * Default agent is typically `"main"`

2. **Open the session index:**
   * Read `~/.openclaw/agents/<agentId>/sessions/sessions.json`
   * Keys follow patterns like `agent:main:telegram:group:-123456789`
   * Look for keys matching the channel type (telegram, discord, etc.)

3. **Match by title or key:**
   * Each entry has a `title` field — match against the group name
   * If matching by ID, Telegram group IDs are negative numbers (e.g., `-123456789`)
   * Discord uses channel IDs (positive numbers)

4. **Open the transcript:**
   * The `sessionId` value in the matched entry → find `<sessionId>.jsonl` in the same directory
   * Read the JSONL file to see the full conversation history

### If the group name doesn't appear in sessions.json

* The group may use a different agent — check `agentBindings` in `openclaw.json`
* Read `src/routing/session-key.ts` → `buildAgentPeerSessionKey()` to understand key construction
* Search across all agent directories: look in `~/.openclaw/agents/*/sessions/sessions.json`

***

## Trace Skill Invocation in a Session

**Goal:** Determine if a skill was triggered and used correctly in a conversation.

### Steps

1. **Find the session JSONL file** (see above)

2. **Check the system prompt** for skill mentions:
   * Skills are listed in the system prompt as metadata (name + description)
   * The system prompt is NOT stored in the JSONL — it's assembled at runtime
   * To see what skills are currently loaded: run `openclaw skills status`

3. **Look for skill usage patterns in the transcript:**
   * Skills that have `scripts/` → look for `toolCall` with `exec` running those scripts
   * Skills that have `references/` → look for `toolCall` reading reference files (file read tool)
   * Skills triggered by description match → the AI's response text may mention the skill name

4. **If a skill DIDN'T trigger when it should have:**
   * Check if the skill is loaded: `openclaw skills status`
   * Check the skill's `description` field — does it match the user's request?
   * Check if the skill was filtered out: read `src/agents/skills/workspace.ts` → `filterSkillEntries()`
   * Check if skill limits were hit (max 150 skills, 30000 chars total)

5. **If a skill triggered but behaved incorrectly:**
   * Read the SKILL.md file to understand what it instructs
   * Check tool execution results in the JSONL for errors (`isError: true`)
   * Check if scripts exist and are executable
   * Check if required env vars are set (e.g., Doppler configs)

***

## Add a Custom Model Provider

**Goal:** Configure a custom API endpoint (proxy, self-hosted model, etc.).

### Steps

1. **Create or edit `~/.openclaw/models.json`:**

```json
{
  "mode": "merge",
  "providers": {
    "my-proxy": {
      "baseUrl": "https://proxy.example.com/v1",
      "apiKey": "sk-your-key",
      "api": "openai-completions",
      "models": [
        {
          "id": "gpt-4o",
          "name": "GPT-4o via Proxy",
          "reasoning": false,
          "input": ["text", "image"],
          "cost": { "input": 2.5, "output": 10, "cacheRead": 1.25, "cacheWrite": 2.5 },
          "contextWindow": 128000,
          "maxTokens": 16384
        }
      ]
    }
  }
}
```

2. **Set the agent to use the custom provider:**
   * Edit `~/.openclaw/openclaw.json` → `agents.list[].model`:
   ```json5
   "model": "my-proxy/gpt-4o"  // format: provider-name/model-id
   ```

3. **Verify:**
   * Restart the gateway (or wait for hot-reload)
   * Send a test message and check the session JSONL first line for `"model"` field

### Available API types

| `api` value | Use for |
|-------------|---------|
| `"openai-completions"` | OpenAI-compatible APIs (most proxies) |
| `"anthropic-messages"` | Anthropic API and compatible proxies |
| `"google-generative-ai"` | Google Gemini API |
| `"ollama"` | Local Ollama server |
| `"bedrock-converse-stream"` | AWS Bedrock |

### Troubleshooting custom providers

* **Read `src/agents/models-config.providers.ts`** → `normalizeProviders()` to see how providers are processed
* **Read `src/config/types.models.ts`** → `ModelProviderConfig` for all valid fields
* Check if API key env var is set: provider name maps to `<PROVIDER_NAME>_API_KEY` env var
* Read `src/agents/models-config.providers.ts` → `resolveEnvApiKeyVarName()` for exact mapping

***

## Verify Model Configuration

**Goal:** Confirm the correct model is being used for a specific agent.

### Steps

1. **Read config:**
   * `~/.openclaw/openclaw.json` → `agents.list` → find the agent → check `model` field
   * Can be a string (`"claude-sonnet-4-20250514"`) or object (`{ primary, fallbacks }`)

2. **Check overrides:**
   * `~/.openclaw/models.json` → custom provider/model definitions
   * Environment variables: `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, etc.

3. **Check the actual model used in a session:**
   * Open the session JSONL → read the first `type: "session"` line → `model` field
   * This shows what model was actually used, not just what was configured

4. **For deeper understanding:**
   * Read `src/agents/model-selection.ts` → model selection order
   * Read `src/agents/model-fallback.ts` → what happens when primary fails

***

## Check Why a Channel Is Offline

**Goal:** Diagnose why a Telegram/Discord/Slack bot is not responding.

### Steps

1. **Check channel config:**
   * Read `~/.openclaw/openclaw.json` → find the channel section (e.g., `telegram`)
   * Verify bot token is present and not empty

2. **Check gateway status:**
   * Run `openclaw channels status --probe`
   * This shows which channels are connected, errored, or disabled

3. **Check channel env vars:**
   * Telegram: `TELEGRAM_BOT_TOKEN`
   * Discord: `DISCORD_BOT_TOKEN`
   * Slack: `SLACK_BOT_TOKEN` + `SLACK_APP_TOKEN` (both required)
   * Env vars override config file values

4. **Check gateway logs:**
   * Gateway log location: `/tmp/openclaw-gateway.log`
   * macOS: run `scripts/clawlog.sh` for unified logs
   * Look for connection errors, token validation failures

5. **For deeper understanding:**
   * Read `src/gateway/server-channels.ts` → channel initialization
   * Read `src/gateway/channel-health-monitor.ts` → health check logic
   * Read the specific channel module:
     * `src/telegram/` for Telegram
     * `src/discord/` for Discord
     * `src/slack/` for Slack

***

## Debug Auth Profile Rotation (Multi-Account)

**Goal:** Diagnose why a second OAuth/API-key account isn't being used, or understand how profile rotation works.

### How rotation actually works

OpenClaw auth profile rotation is **session-scoped, not per-message**:

* A session picks one profile and **sticks with it** until compaction happens
* Rotation advances on: (1) new session created, (2) compaction triggered
* The picked profile is stored as `authProfileOverride` in `sessions.json`
* This is written by `src/agents/auth-profiles/session-override.ts` → `resolveSessionAuthProfileOverride()`

Within a provider, the **round-robin order** (when no override is set) is:
* Sorted by `lastUsed` oldest-first (never-used = 0 = always first)
* OAuth > token > api_key type preference
* Profiles in cooldown go to the end

### Files to check

| What | Where |
|------|-------|
| Profile credentials + tokens | `~/.openclaw/agents/main/agent/auth-profiles.json` |
| Per-session profile pin | `~/.openclaw/agents/main/sessions/sessions.json` → `authProfileOverride` |
| Profile order config | `~/.openclaw/openclaw.json` → `auth.profiles` |
| Usage stats & cooldowns | `auth-profiles.json` → `usageStats` |
| Last successful profile | `auth-profiles.json` → `lastGood` |

### Step-by-step diagnosis

**1. Check if the second profile is registered in both places:**

```bash
# Must appear in openclaw.json auth.profiles
cat ~/.openclaw/openclaw.json | python3 -c "
import json,sys; d=json.load(sys.stdin)
for k,v in d.get('auth',{}).get('profiles',{}).items():
    print(k, '->', v.get('provider'), v.get('mode'))
"

# Must also have credentials in auth-profiles.json
cat ~/.openclaw/agents/main/agent/auth-profiles.json | python3 -c "
import json,sys; d=json.load(sys.stdin)
for k,v in d.get('profiles',{}).items():
    print(k, '->', v.get('provider'), v.get('type'))
"
```

The rotation candidate list follows this logic (from `src/agents/auth-profiles/order.ts`):

* If `openclaw.json` `auth.profiles` has **any entries for this provider** → only those profiles enter rotation; profiles in `auth-profiles.json` but not in `auth.profiles` are excluded.
* If `openclaw.json` `auth.profiles` has **no entries for this provider** → all profiles from `auth-profiles.json` are used automatically.

So if you have entries for `openai-codex` in `auth.profiles`, you must add every account there. If you have no entries at all for a provider, `auth-profiles.json` is the source of truth.

**2. Check the session's current override:**

```bash
python3 -c "
import json
d = json.load(open('/home/audichuang/.openclaw/agents/main/sessions/sessions.json'))
key = 'agent:main:telegram:group:-XXXXXXXXX'  # replace with your session key
e = d.get(key, {})
print('authProfileOverride:', e.get('authProfileOverride'))
print('authProfileOverrideSource:', e.get('authProfileOverrideSource'))
print('compactionCount:', e.get('compactionCount'))
"
```

If `authProfileOverride` is set and the session is NOT new / no compaction, it will keep using that profile.

**3. Check usageStats to see which profiles were actually used:**

```bash
cat ~/.openclaw/agents/main/agent/auth-profiles.json | python3 -c "
import json,sys,datetime
d=json.load(sys.stdin)
for k,v in d.get('usageStats',{}).items():
    lu=v.get('lastUsed',0)
    dt=datetime.datetime.fromtimestamp(lu/1000).strftime('%m-%d %H:%M:%S') if lu else 'never'
    print(f'{k}: lastUsed={dt} errors={v.get(\"errorCount\",0)}')
print()
print('lastGood:', d.get('lastGood',{}))
"
```

### Fix: force a session to switch to the new profile

Clear the session's `authProfileOverride` so the next message re-evaluates round-robin (picks oldest lastUsed):

```bash
python3 -c "
import json, time
path = '/home/audichuang/.openclaw/agents/main/sessions/sessions.json'
d = json.load(open(path))
key = 'agent:main:telegram:group:-XXXXXXXXX'  # replace
e = d[key]
e.pop('authProfileOverride', None)
e.pop('authProfileOverrideSource', None)
e.pop('authProfileOverrideCompactionCount', None)
e['updatedAt'] = int(time.time() * 1000)
json.dump(d, open(path,'w'), indent=2, ensure_ascii=False)
print('Cleared.')
"
```

No gateway restart needed — `sessions.json` is read per-request.

### Common pitfall: added second account AFTER session was already running

1. Session was first created when only the old profile existed
2. `authProfileOverride` was auto-set to the old profile
3. Even after adding the new profile to `openclaw.json`, the session keeps the old override
4. **Fix:** clear the override as above, then the next message picks the new profile

### Important: runtime snapshot caching

The gateway loads `auth-profiles.json` into an **in-memory snapshot** at startup via `activateSecretsRuntimeSnapshot()`.
If you add a new profile to `openclaw.json` while the gateway is running, the log says:
```
config change requires gateway restart (auth.profiles.<new-profile>)
```
→ **A full gateway restart is required** for the new profile to enter the rotation.

### Source code

* `src/agents/auth-profiles/session-override.ts` → `resolveSessionAuthProfileOverride()` — reads/writes `authProfileOverride` in sessions.json
* `src/agents/auth-profiles/order.ts` → `resolveAuthProfileOrder()` — builds the round-robin candidate list
* `src/agents/auth-profiles/usage.ts` → `markAuthProfileUsed()` — updates `usageStats.lastUsed` after each use
* `src/agents/auth-profiles/store.ts` → `ensureAuthProfileStore()` — loads store from runtime snapshot or disk
* `src/secrets/runtime.ts` → `activateSecretsRuntimeSnapshot()` — sets in-memory auth store at gateway startup

***

## Understand Agent Binding

**Goal:** Understand how groups/channels are routed to specific agents.

Agent bindings in `openclaw.json` control which agent handles messages from specific channels or groups.

### Config format

```json5
{
  "agentBindings": [
    {
      "agentId": "ops",           // Route to this agent
      "match": {
        "channel": "telegram",    // Channel type
        "peer": {
          "kind": "group",        // "group", "channel", or "direct"
          "id": "-123456789"      // Group/channel/user ID
        }
      }
    }
  ]
}
```

### How routing works

1. Message arrives with channel + peer info
2. System checks `agentBindings` for a matching rule
3. If matched → routes to the specified agent (separate config, sessions, skills)
4. If no match → routes to default agent

### Source code

* Read `src/config/types.agents.ts` → `AgentBinding` type definition
* Read `src/routing/session-key.ts` → `buildAgentPeerSessionKey()` for session key construction
