# OpenClaw Config File Formats

Detailed format reference for all configuration files. Read the relevant section when you need to understand or modify a specific config.

## Table of Contents

* [openclaw.json — Main Config](#openclawjson--main-config)
* [models.json — Custom Providers & Models](#modelsjson--custom-providers--models)
* [sessions.json — Session Store Index](#sessionsjson--session-store-index)
* [Session JSONL — Transcript Format](#session-jsonl--transcript-format)
* [Session Key Format](#session-key-format)

***

## openclaw.json — Main Config

**Location:** `~/.openclaw/openclaw.json` (JSON5 — supports comments and trailing commas)

**To understand all valid fields:** Read `src/config/schema.ts` and `src/config/types.ts`

### Top-level Structure

```json5
{
  // Agent definitions
  "agents": {
    "defaults": { /* shared defaults */ },
    "list": [
      {
        "id": "main",           // Agent identifier
        "default": true,        // Is this the default agent?
        "name": "My Agent",     // Display name
        "workspace": "/path",   // Workspace directory
        "model": "claude-sonnet-4-20250514",  // or { primary, fallbacks }
        "skills": ["debug-openclaw", "session-logs"],  // Allowlist (omit = all)
        // Note: per-agent "model" overrides agents.defaults.model
        "identity": { "name": "Bot", "description": "..." },
        "groupChat": { /* group chat settings */ },
        "tools": { /* tool policies */ },
        "sandbox": { "mode": "off" | "non-main" | "all" }
      }
    ]
  },

  // Gateway server settings
  "gateway": {
    "port": 18789,
    "mode": "local" | "remote",
    "bind": "loopback" | "lan" | "auto" | "tailnet" | "custom",
    "auth": {
      "mode": "none" | "token" | "password" | "trusted-proxy",
      "token": "..."
    },
    "controlUi": { "enabled": true },
    "reload": { "mode": "hybrid" },
    "channelHealthCheckMinutes": 5
  },

  // Channel configs — each at top level
  "telegram": {
    "botToken": "123456:ABC-DEF...",
    "allowedUsers": ["user1"],
    "groupChat": { /* ... */ }
  },
  "discord": {
    "botToken": "...",
    "appId": "...",
    "guildId": "..."
  },
  "slack": {
    "botToken": "xoxb-...",
    "appToken": "xapp-..."
  },

  // Skills config
  "skills": {
    "install": { "preferBrew": true },
    "disable": ["unwanted-skill"],
    "limits": {
      "maxSkillsInPrompt": 150,
      "maxSkillsPromptChars": 30000,
      "maxSkillFileBytes": 256000
    }
  },

  // Session settings
  "session": {
    "store": "/custom/store/path"
  },

  // Model overrides (alternative to separate models.json)
  "models": {
    "mode": "merge" | "replace",
    "providers": { /* same format as models.json providers */ }
  },

  // Default agent model configuration (agents.defaults)
  // agents.defaults.model.primary — the primary model
  // agents.defaults.model.fallbacks — ordered fallback list
  // agents.defaults.models — dict of all registered model IDs (keyed by provider/model)

  // Agent bindings — map channels/groups to specific agents
  "agentBindings": [
    {
      "agentId": "ops",
      "match": {
        "channel": "telegram",
        "peer": { "kind": "group", "id": "-123456789" }
      }
    }
  ]
}
```

### Key Config Types

**To see exact type definitions**, read these files:

* Agent config: `src/config/types.agents.ts` → `AgentConfig`
* Gateway config: `src/config/types.gateway.ts` → `GatewayConfig`
* Model config: `src/config/types.models.ts` → `ModelsConfig`, `ModelProviderConfig`
* Channel configs: `src/config/types.discord.ts`, `src/config/types.telegram.ts`, etc.
* Agent bindings: `src/config/types.agents.ts` → `AgentBinding`

***

## models.json — Custom Providers & Models

**Location:** `~/.openclaw/models.json` (optional, JSON format)

Use this to add custom providers (e.g., proxy, self-hosted, or alternative API endpoints).

### Structure

```json
{
  "mode": "merge",
  "providers": {
    "my-provider": {
      "baseUrl": "https://my-proxy.example.com/v1",
      "apiKey": "sk-...",
      "api": "openai-completions",
      "models": [
        {
          "id": "my-model",
          "name": "My Custom Model",
          "reasoning": false,
          "input": ["text", "image"],
          "cost": { "input": 3, "output": 15, "cacheRead": 0.3, "cacheWrite": 3.75 },
          "contextWindow": 128000,
          "maxTokens": 8192
        }
      ]
    }
  }
}
```

### Provider Config Fields

| Field | Type | Description |
|-------|------|-------------|
| `baseUrl` | string | API endpoint URL |
| `apiKey` | string | API key (or env var reference) |
| `api` | string | API protocol: `"openai-completions"`, `"openai-responses"`, `"anthropic-messages"`, `"google-generative-ai"`, `"github-copilot"`, `"ollama"`, `"bedrock-converse-stream"` |
| `authHeader` | boolean | If `true`, sends API key via `Authorization: Bearer` header instead of provider-specific header |
| `auth` | string | Auth mode: `"api-key"` (default), `"aws-sdk"`, `"oauth"`, `"token"` |
| `headers` | object | Additional HTTP headers |
| `models` | array | Model definitions (see below) |

### Model Definition Fields

| Field | Type | Description |
|-------|------|-------------|
| `id` | string | Model identifier (used in API calls) |
| `name` | string | Display name |
| `reasoning` | boolean | Extended thinking support |
| `input` | array | Input modalities: `["text"]` or `["text", "image"]` |
| `cost` | object | Per-million-token costs: `{ input, output, cacheRead, cacheWrite }` |
| `contextWindow` | number | Max context tokens |
| `maxTokens` | number | Max output tokens |

### Using a Custom Provider

After adding to `models.json`, set the model in `openclaw.json`:

```json5
{
  "agents": {
    "list": [{
      "id": "main",
      "model": "my-provider/my-model"  // format: provider/model
    }]
  }
}
```

**Source code to read:** `src/agents/models-config.providers.ts` → `normalizeProviders()` for how providers are resolved

***

## sessions.json — Session Store Index

**Location:** `~/.openclaw/agents/<agentId>/sessions/sessions.json`

Maps session keys to session metadata.

### Structure

```json
{
  "agent:main:main": {
    "sessionId": "abc123-def456",
    "title": "Chat Title",
    "updatedAt": "2025-01-15T10:30:00Z"
  },
  "agent:main:telegram:group:-123456789": {
    "sessionId": "xyz789",
    "title": "My Telegram Group",
    "updatedAt": "2025-01-15T11:00:00Z"
  }
}
```

**The key is the session key** (see format below). **The `sessionId` points to the transcript file**: `<sessionId>.jsonl` in the same directory.

***

## Session JSONL — Transcript Format

**Location:** `~/.openclaw/agents/<agentId>/sessions/<sessionId>.jsonl`

Each line is an independent JSON object. Read line by line.

### Line Types

**Session metadata (first line):**

```json
{"type":"session","timestamp":"2025-01-15T10:30:00Z","model":"claude-sonnet-4-20250514","authProfile":"default"}
```

**User message:**

```json
{"type":"message","timestamp":"...","message":{"role":"user","content":[{"type":"text","text":"Hello"}]}}
```

**Assistant response:**

```json
{"type":"message","timestamp":"...","message":{"role":"assistant","content":[{"type":"text","text":"Hi!"}],"usage":{"input":100,"output":50,"cost":{"total":0.001}}}}
```

**Tool call:**

```json
{"type":"message","timestamp":"...","message":{"role":"assistant","content":[{"type":"toolCall","name":"exec","input":{"command":"ls"}}]}}
```

**Tool result:**

```json
{"type":"message","timestamp":"...","message":{"role":"toolResult","content":[{"type":"toolResult","toolCallId":"...","text":"file1.txt\nfile2.txt","isError":false}]}}
```

### What to look for when debugging

* **Last few lines** — What was the final state?
* **`isError: true`** in tool results — Tool execution failures
* **`usage.cost.total`** — Cost tracking
* **Missing `toolResult` after `toolCall`** — Execution interrupted
* **Error keywords in text** — `billing`, `rate_limit`, `unauthorized`, `context_length_exceeded`

***

## Session Key Format

Session keys identify unique conversations. Understanding the format helps you find the right session.

### Format Patterns

| Pattern | Example | Meaning |
|---------|---------|---------|
| `agent:<agentId>:main` | `agent:main:main` | Default CLI/web session |
| `agent:<agentId>:<channel>:direct:<peerId>` | `agent:main:telegram:direct:123456` | DM with user |
| `agent:<agentId>:<channel>:group:<groupId>` | `agent:main:telegram:group:-123456789` | Group chat |
| `agent:<agentId>:<channel>:channel:<channelId>` | `agent:main:discord:channel:987654` | Discord channel |
| `global` | `global` | Legacy global session |

### How to find a session by group name

1. Open `sessions.json`
2. Look for keys containing the channel name and group ID
3. The `sessionId` value points to the `.jsonl` transcript file
4. If you only have a group name (not ID), search transcript files for the group name

**Source code:** `src/routing/session-key.ts` → `buildAgentPeerSessionKey()` for exact key construction logic
