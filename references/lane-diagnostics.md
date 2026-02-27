# OpenClaw Lane & Execution Diagnostics

In-depth guides for diagnosing execution-flow issues: event queue blocking, subagent lane contention, model fallback failures, and diagnostic command performance.

## Table of Contents

* [Event Queue Blocking / Lane Congestion](#event-queue-blocking--lane-congestion)
* [Subagent Blocking Main Lane](#subagent-blocking-main-lane)
* [Model Fallback Not Working](#model-fallback-not-working)

***

## Event Queue Blocking / Lane Congestion

**Symptom:** Messages in one or more Discord/Telegram channels get `DiscordMessageListener timed out after 30000ms` or `Slow listener detected: DiscordMessageListener took Xs`. Bot appears stuck / typing but never responds. Messages are silently dropped.

**Architecture context:**

OpenClaw processes Discord/Telegram events through an **EventQueue** that dispatches to listeners (e.g. `DiscordMessageListener`). The critical constraint:

* Each listener invocation runs on a **lane** associated with the session (e.g. `lane=session:agent:main:discord:channel:<id>`)
* The **main lane** is shared — if one session's run takes a long time, it blocks other sessions from starting
* The `DiscordMessageListener` has a **30-second hard timeout**. If the listener can't finish processing a message within 30 seconds (because the main lane is occupied), the message is **silently dropped**
* This means: **one slow channel blocks ALL other channels**

**How to diagnose:**

> **Performance note:** `journalctl` is slower than direct log file access. OpenClaw writes structured JSON logs to `/tmp/openclaw/openclaw-YYYY-MM-DD.log`. For fastest results, grep the log file directly. Always wrap commands in `timeout` to avoid hangs from I/O contention.

1. Check gateway logs for timeout and slow listener patterns (fastest method):
   ```bash
   # Fastest: grep the log file directly (~10ms for 7.7MB file)
   timeout 10 grep -E "timed out|Slow listener|lane task" /tmp/openclaw/openclaw-$(date +%Y-%m-%d).log | tail -20

   # For recent events only (~0ms):
   tail -500 /tmp/openclaw/openclaw-$(date +%Y-%m-%d).log | grep -E "timed out|Slow listener|lane task"

   # journalctl alternative (slower, but supports time range filtering):
   timeout 15 journalctl --user -u openclaw-gateway --since "1 hour ago" --no-pager | grep -E "timed out|Slow listener|lane task"
   ```

2. Look for `lane task error` or `lane task done` entries — these show which session/channel is occupying the lane and for how long:
   ```
   lane task done: lane=session:agent:main:discord:channel:<ID> durationMs=850076
   ```
   If `durationMs` > 30000, this run blocked all other channels from processing new messages.

3. Correlate the blocking channel ID with `sessions.json` (use `jq`, ~30ms):
   ```bash
   timeout 10 jq -r '."agent:main:discord:channel:<ID>" | {sessionId, groupChannel, displayName, model, modelProvider}' \
     ~/.openclaw/agents/main/sessions/sessions.json
   ```

4. Read the blocking session's `.jsonl` to understand what it was doing (use `tail`, ~2ms):
   ```bash
   # Quick overview: line count + last 3 entries
   wc -l ~/.openclaw/agents/main/sessions/<sessionId>.jsonl
   tail -3 ~/.openclaw/agents/main/sessions/<sessionId>.jsonl | python3 -c "
   import sys, json
   for l in sys.stdin:
       e = json.loads(l)
       role = e.get('message',{}).get('role','')
       ts = e.get('timestamp','')
       t = e.get('type','')
       print(f'{ts} {t or role}')
   "
   ```
   * Was it a large context (high `inputTokens`)? → check first `type: "session"` line
   * Was it waiting for a tool call (e.g. `exec` running a long script)?
   * Did it have repeated API errors causing retry loops?

### Diagnostic Command Efficiency Guide

When diagnosing OpenClaw issues, command choice matters less than avoiding **I/O contention**. Benchmarks on a clean system (sessions.json 4.2MB, log file 7.7MB/8346 lines, session JSONL 172K/60 lines):

**Query sessions.json:**

| Method | Time | Notes |
|--------|------|-------|
| `grep -A1 "channelId" sessions.json` | **2ms** | Fastest, but output is raw — need manual parsing |
| `jq -r '."key".sessionId' sessions.json` | 32ms | Best balance of speed + structured output |
| `python3 -c "json.load(...)..."` | 36ms | Slowest, but fine — no real penalty |

**Search log file:**

| Method | Time | Notes |
|--------|------|-------|
| `grep "pattern" logfile` | **2ms** | Full scan, all matches |
| `grep -m5 "pattern" logfile` | 2ms | Stop after N matches |
| `tail -500 logfile \| grep "pattern"` | 2ms | Recent events only |
| `journalctl --since ... \| grep` | 7ms | Slower, but supports native time filtering |
| `tac logfile \| grep -m5` | 6ms | Reverse search (most recent first) |

**Read session JSONL:**

| Method | Time | Notes |
|--------|------|-------|
| `wc -l file.jsonl` | **1ms** | Just line count |
| `tail -3 file.jsonl \| jq .timestamp` | 3ms | Last N entries, structured |
| `python3 readlines()` | 11ms | Full file parse — unnecessary for tail reads |

**Parse structured log entries:**

| Method | Time | Notes |
|--------|------|-------|
| `grep -oP '"1":"lane task [^"]*"' logfile` | **2ms** | Inline extraction, no subprocess |
| `grep "pattern" logfile \| python3 json.loads(...)` | 19ms | Full JSON parse per line |

**Critical rules:**
- **Always use `timeout`** — I/O contention from concurrent processes can make ANY command hang indefinitely
- **Never run multiple searches on the same file simultaneously** — this was the #1 cause of 30+ minute hangs in practice
- **`jq` is the best default for JSON** — faster than python3 invocations and structured output
- **`tail -N | grep` for recent events** — avoids scanning the full file when you only need the latest entries
- **`grep -oP` for inline extraction** — 10x faster than piping to python3/jq for simple field extraction

**Common causes of lane congestion:**

| Cause | Log pattern | Duration |
|-------|------------|----------|
| API overload / 504 errors | `FailoverError: 504 Streaming failed` | 110+ seconds per retry cycle |
| Subagent announce retries | `Subagent announce ... retrying N/4 ... gateway timeout after 60000ms` | 240+ seconds (4 × 60s) |
| Large context processing | `lane task done: durationMs=<high>` with no errors | Varies (can be 60-850+ seconds) |
| Embedded run timeout | `embedded run timeout: runId=... timeoutMs=600000` | Up to 600 seconds |
| Long tool execution | `exec` tool running a slow script/process | Depends on script |

**Resolution:**

* **Immediate:** Reset the blocking session via Discord `/reset` command or OpenClaw Control UI
* **If API errors:** Wait for the API to recover, or switch the blocking session's model to a working provider
* **If subagent retries:** Kill stuck subagent processes (`ps aux | grep prep_funday` etc.) and restart gateway
* **Systemic:** Avoid running long tasks (podcast generation, large code execution) on the same agent that handles real-time chat — use a separate agent or dedicated subagent with its own model

***

## Subagent Blocking Main Lane

**Symptom:** Same as Event Queue Blocking, but specifically caused by subagent operations. You see `Subagent announce` retry messages in the logs.

**Architecture context:**

* Subagents are spawned via `sessions_spawn` tool and run in their own child sessions
* Subagent model is configured globally: `agents.defaults.subagents.model` in `openclaw.json`
* When a subagent **completes or fails**, it sends a completion announcement back to the parent session (the "announce" callback)
* The announce callback runs on the **main lane** — if the parent session's model API is down, the announce retries up to 4 times with 60-second gateway timeouts
* **Each failed announce cycle = 60 seconds blocking the main lane**
* 4 retries × 60s = **240+ seconds of pure lane blockage**

**How to diagnose:**

1. Check for subagent announce failures:
   ```bash
   journalctl --user -u openclaw-gateway --since "1 hour ago" --no-pager | grep -E "Subagent announce|subagent.*retry"
   ```

2. Check active subagent runs:
   ```bash
   cat ~/.openclaw/subagents/runs.json | python3 -m json.tool
   ```
   Look for runs with no `endedAt` (still active) or with `outcome.status: "error"`.

3. Check running subagent processes:
   ```bash
   ps -eo pid,lstart,etime,args | grep -E "prep_funday|notebooklm|doppler" | grep -v grep
   ```
   Look for processes running for an unusually long time (30+ minutes).

**Key distinction:** The subagent `model` is a separate config from the session model. Changing the model via Discord `/models` command only changes the **session model**, not the subagent model. The subagent model is set globally in:
```json
"agents": {
  "defaults": {
    "subagents": {
      "model": "openai-codex/gpt-5.2"  // ← this is what subagents use
    }
  }
}
```

**Resolution:**

* **Immediate:** Kill orphaned subagent processes and restart gateway
* **Config fix:** Change `agents.defaults.subagents.model` to a reliable provider
* **Subagent model also supports fallback:**
  ```json
  "subagents": {
    "model": {
      "primary": "openai-codex/gpt-5.2",
      "fallbacks": ["google-gemini-cli/gemini-3-flash-preview"]
    }
  }
  ```

***

## Model Fallback Not Working

**Symptom:** Primary model fails (504, rate limit, overloaded) but the agent doesn't fall back to alternative models. You see `FailoverError` in logs wrapping the primary model's error, and the request just fails.

**Architecture context:**

The fallback chain is defined in `agents.defaults.model`:
```json
"model": {
  "primary": "google/gemini-3.1-pro-preview",
  "fallbacks": [
    "google/gemini-3-flash-preview",
    "openai-codex/gpt-5.2",
    ...
  ]
}
```

For each fallback entry like `provider/model-id`, OpenClaw needs:
1. The **provider** must be either a built-in provider with valid auth, or defined in `models.providers` with `baseUrl` and `apiKey`
2. The **model ID** must be registered in that provider's `models` array (for custom providers)

**How to diagnose:**

1. Check which fallbacks are actually valid:
   ```bash
   # List configured custom providers and their models
   jq -r '.models.providers | to_entries[] | "\(.key): [\([.value.models[].id] | join(", "))]"' \
     ~/.openclaw/openclaw.json
   ```

2. Cross-reference with the fallback list:
   ```bash
   jq -r '.agents.defaults.model.fallbacks[]' ~/.openclaw/openclaw.json
   ```

3. Look for `Unknown model` errors in logs:
   ```bash
   journalctl --user -u openclaw-gateway --since "1 hour ago" --no-pager | grep "Unknown model"
   ```
   Each `Unknown model: <provider>/<model>` means that fallback entry is **invalid and skipped instantly**.

**Common misconfiguration patterns:**

| Problem | Example | Fix |
|---------|---------|-----|
| Provider not defined in `models.providers` | `google-gemini-cli/gemini-3-flash` but `google-gemini-cli` not in providers | Either define the provider or use a built-in provider with valid auth |
| Model not registered in provider | `google/gemini-3-flash-preview` but Google provider only has `gemini-3.1-pro-preview` | Add the model to the provider's `models` array |
| All fallbacks are from same provider | All entries use `google/*` and Google API is down | Add fallbacks from different providers (e.g. `openai-codex`, `anthropic`, `minimax`) |
| Built-in provider has no auth | `openai-codex/gpt-5.2` but no OAuth token configured | Run `openclaw models auth` to authenticate |
| Fallback order puts broken entries first | 8 invalid `google-gemini-cli/*` entries before any valid one | Reorder to put known-working providers first |

**Built-in vs Custom providers:**

* **Built-in providers** (e.g. `google`, `openai-codex`, `anthropic`, `openrouter`, `google-gemini-cli`): Do NOT need `models.providers` entries. They use auth profiles (check `auth.profiles` in config) and environment variables
* **Custom providers** (e.g. `taobao`, `kiro`, `minimax`): MUST be defined in `models.providers` with `baseUrl`, `apiKey`, and a `models` array listing available model IDs

**Resolution:**

* Ensure fallback list has entries from **multiple different providers** that are actually configured
* Put the most reliable/fastest fallback first (local proxies, fast models)
* For custom providers, make sure every model ID in the fallback list is registered in that provider's `models` array
* Test provider availability: `curl -s -o /dev/null -w "%{http_code}" <baseUrl>`
