#!/usr/bin/env python3
"""
Session Query Tool - Quick session diagnostics for OpenClaw

Usage:
    python session_query.py <session_id_or_key>
    python session_query.py --key "agent:main:telegram:group:-5142412129"
    python session_query.py <session_id> --errors
    python session_query.py <session_id> --tools
    python session_query.py <session_id> --tail 20
"""

import argparse
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional


@dataclass
class SessionInfo:
    session_id: str
    session_key: str
    agent_id: str
    model: str
    provider: str
    created: str
    messages: list[dict]


def get_home() -> Path:
    return Path(os.path.expanduser("~"))


def get_sessions_index(agent_id: str = "main") -> dict:
    """Load sessions.json index."""
    sessions_json = get_home() / ".openclaw" / "agents" / agent_id / "sessions" / "sessions.json"
    if not sessions_json.exists():
        return {}
    with open(sessions_json) as f:
        return json.load(f)


def get_session_info(session_id_or_key: str, agent_id: str = "main") -> Optional[SessionInfo]:
    """Find session info from ID or session key."""
    sessions = get_sessions_index(agent_id)

    # Build reverse mapping: sessionId -> sessionKey
    id_to_key = {}
    for key, entry in sessions.items():
        sid = entry.get("sessionId")
        if sid:
            id_to_key[sid] = key

    # Determine session_id and session_key
    session_id = None
    session_key = None

    # If it's already a session ID (UUID format with dashes)
    if "-" in session_id_or_key and len(session_id_or_key) == 36:
        session_id = session_id_or_key
        session_key = id_to_key.get(session_id)
    else:
        # Try as session key
        key = session_id_or_key
        if not key.startswith("agent:"):
            key = f"agent:{agent_id}:{key}"

        if key in sessions:
            session_key = key
            session_id = sessions[key].get("sessionId")

    if not session_id:
        # Try partial key match
        for k, v in sessions.items():
            if session_id_or_key in k:
                session_key = k
                session_id = v.get("sessionId")
                break

    if not session_id:
        return None

    # Get model/provider from sessions.json
    entry = sessions.get(session_key, {})
    model = entry.get("modelOverride") or entry.get("model") or "unknown"
    provider = entry.get("providerOverride") or entry.get("provider") or "unknown"
    created = entry.get("createdAt")
    if created:
        # Convert millis timestamp to ISO
        from datetime import datetime

        created = datetime.fromtimestamp(created / 1000).isoformat() + "Z"

    return SessionInfo(
        session_id=session_id,
        session_key=session_key or "unknown",
        agent_id=agent_id,
        model=model,
        provider=provider,
        created=created,
        messages=[],
    )


def get_session_file(session_info: SessionInfo) -> Optional[Path]:
    """Get session JSONL file path."""
    sessions_dir = get_home() / ".openclaw" / "agents" / session_info.agent_id / "sessions"
    return sessions_dir / f"{session_info.session_id}.jsonl"


def load_session(path: Path) -> list[dict]:
    """Load session JSONL file."""
    messages = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                messages.append(json.loads(line))
    return messages


def extract_messages(messages: list[dict]) -> list[dict]:
    """Extract actual message entries from session file."""
    # Just return all messages - we can filter by type directly
    return messages


def print_summary(session_info: SessionInfo, messages: list[dict]) -> None:
    """Print session summary."""
    print(f"📋 Session Info:")
    print(f"   Session ID: {session_info.session_id}")
    print(f"   Session Key: {session_info.session_key}")
    print(f"   Model: {session_info.model} @ {session_info.provider}")
    print(f"   Created: {session_info.created}")

    # Count roles - check both "message" type entries and their role field
    user_count = 0
    assistant_count = 0

    for m in messages:
        if m.get("type") != "message":
            continue
        role = m.get("message", {}).get("role")
        if role == "user":
            user_count += 1
        elif role == "assistant":
            assistant_count += 1

    # Count tool calls and results
    tool_calls = 0
    tool_errors = 0
    for m in messages:
        if m.get("type") != "message":
            continue
        content = m.get("message", {}).get("content", [])
        for c in content:
            if c.get("type") == "toolCall":
                tool_calls += 1
            elif c.get("type") == "toolResult" and c.get("isError"):
                tool_errors += 1

    # Calculate cost
    total_cost = 0.0
    for m in messages:
        if m.get("type") == "message":
            usage = m.get("message", {}).get("usage", {})
            if usage:
                total_cost += usage.get("cost", {}).get("total", 0)

    print(f"\n📊 Statistics:")
    print(f"   Total entries: {len(messages)}")
    print(f"   User messages: {user_count} | Assistant: {assistant_count}")
    print(f"   Tool calls: {tool_calls} | Errors: {tool_errors}")
    print(f"   Total cost: ${total_cost:.4f}")

    if messages:
        print(f"\n⏰ Time range:")
        print(f"   First: {messages[0].get('timestamp', 'N/A')}")
        print(f"   Last:  {messages[-1].get('timestamp', 'N/A')}")

    # Model changes
    model_changes = [m for m in messages if m.get("type") == "model_change"]
    if model_changes:
        print(f"\n🔄 Model changes:")
        for mc in model_changes:
            print(f"   {mc.get('timestamp')}: {mc.get('provider')}/{mc.get('modelId')}")


def print_tail(messages: list[dict], n: int = 20) -> None:
    """Print last N messages in human-readable format."""
    print(f"\n📜 Last {n} entries:\n")
    for msg in messages[-n:]:
        msg_type = msg.get("type")

        if msg_type == "session":
            print(f"[SESSION] ID: {msg.get('id')} | {msg.get('timestamp')}")
            continue

        if msg_type == "model_change":
            print(f"[MODEL] {msg.get('provider')}/{msg.get('modelId')} | {msg.get('timestamp')}")
            continue

        if msg_type == "thinking_level_change":
            print(f"[THINKING] {msg.get('thinkingLevel')} | {msg.get('timestamp')}")
            continue

        if msg_type == "custom":
            custom_type = msg.get("customType", "unknown")
            print(f"[CUSTOM:{custom_type}] {msg.get('timestamp')}")
            continue

        if msg_type != "message":
            print(f"[{msg_type}] {msg.get('timestamp')}")
            continue

        role = msg.get("message", {}).get("role")
        content = msg.get("message", {}).get("content", [])

        for c in content:
            c_type = c.get("type")
            if c_type == "text":
                text = c.get("text", "")[:300]
                print(f"[{role}] {text}")
            elif c_type == "toolCall":
                name = c.get("name", "unknown")
                tool_id = c.get("id", "")[:8]
                # Get tool arguments - use "arguments" field, not "input"
                args = c.get("arguments", {})
                inp_str = ""
                if isinstance(args, dict) and args:
                    # For browser tool, show action and key params
                    if name == "browser":
                        action = args.get("action", "")
                        url = args.get("targetUrl", "")[:50] if args.get("targetUrl") else ""
                        profile = args.get("profile", "")
                        inp_str = f" | {action}" + (f" ({profile})" if profile else "")
                        inp_str += f" → {url}" if url else ""
                    # For exec, show command
                    elif name == "exec" and "command" in args:
                        cmd = args.get("command", "")[:70]
                        # Show just the first line
                        cmd = cmd.split("\n")[0]
                        inp_str = f" | {cmd}"
                    # For read, show file path
                    elif name == "read" and "path" in args:
                        path = args.get("path", "")[:60]
                        inp_str = f" | {path}"
                    # For web_search, show query
                    elif name == "web_search" and "query" in args:
                        query = args.get("query", "")[:60]
                        inp_str = f" | {query}"
                    # Generic: show first 2 keys
                    else:
                        keys = list(args.keys())[:2]
                        parts = []
                        for k in keys:
                            v = args.get(k, "")
                            if isinstance(v, str):
                                v = v[:40]
                            parts.append(f"{k}: {v}")
                        inp_str = " | " + ", ".join(parts) if parts else ""
                print(f"[{role} tool] {name} ({tool_id}){inp_str}")
            elif c_type == "toolResult":
                name = c.get("name", "unknown")
                tool_id = c.get("id", "")[:8]
                error = c.get("isError", False)
                result_preview = ""
                if error:
                    err = c.get("error", "")
                    if err:
                        result_preview = f" | Error: {err[:80]}"
                else:
                    # Show brief success
                    result_preview = " | ✅"
                print(f"[{role} result] {name} ({tool_id}){result_preview}")


def print_errors(messages: list[dict]) -> None:
    """Print all errors in the session."""
    print("\n❌ Errors found:\n")
    found = False

    for i, msg in enumerate(messages):
        if msg.get("type") != "message":
            continue

        content = msg.get("message", {}).get("content", [])
        for c in content:
            if c.get("type") == "toolResult" and c.get("isError"):
                found = True
                tool_name = c.get("name", "unknown")
                tool_id = c.get("id", "")[:8]
                error_msg = c.get("error", c.get("message", ""))
                ts = msg.get("timestamp", "")
                print(f"--- [{ts}] Tool: {tool_name} ({tool_id}) ---")
                print(f"Error: {error_msg[:500]}")
                print()

    if not found:
        print("No errors found ✅")


def print_tool_usage(messages: list[dict]) -> None:
    """Print tool usage breakdown with details."""
    tools: dict[str, dict] = {}
    errors_by_tool: dict[str, int] = {}

    for msg in messages:
        if msg.get("type") != "message":
            continue

        content = msg.get("message", {}).get("content", [])
        for c in content:
            if c.get("type") == "toolCall":
                name = c.get("name", "unknown")
                if name not in tools:
                    tools[name] = {"count": 0, "errors": 0, "first_use": None, "last_use": None}
                tools[name]["count"] += 1
                ts = msg.get("timestamp", "")
                if not tools[name]["first_use"]:
                    tools[name]["first_use"] = ts
                tools[name]["last_use"] = ts

            elif c.get("type") == "toolResult":
                name = c.get("name", "unknown")
                is_error = c.get("isError", False)
                if name not in errors_by_tool:
                    errors_by_tool[name] = 0
                if is_error:
                    errors_by_tool[name] += 1
                    if name in tools:
                        tools[name]["errors"] += 1

    if not tools:
        print("\nNo tool calls found")
        return

    print("\n🔧 Tool usage:\n")
    print(f"{'Count':>6} | {'Errors':>6} | Tool")
    print("-" * 50)
    for name, info in sorted(tools.items(), key=lambda x: -x[1]["count"]):
        errors = info["errors"]
        print(f"{info['count']:>6} | {errors:>6} | {name}")
        if errors > 0:
            print(f"       └─ {errors} errors in this tool")

    print(
        f"\n📈 Total: {sum(t['count'] for t in tools.values())} calls, {sum(t['errors'] for t in tools.values())} errors"
    )


def search_messages(messages: list[dict], keyword: str, limit: int = 20) -> None:
    """Search for keyword in messages."""
    print(f'\n🔍 Search results for "{keyword}" (showing {limit} results):\n')

    count = 0
    for msg in messages:
        if count >= limit:
            break

        if msg.get("type") != "message":
            continue

        role = msg.get("message", {}).get("role")
        content = msg.get("message", {}).get("content", [])

        for c in content:
            if c.get("type") == "text":
                text = c.get("text", "")
                if keyword.lower() in text.lower():
                    count += 1
                    ts = msg.get("timestamp", "")
                    print(f"[{ts}] [{role}]")
                    print(f"   {text[:400]}...")
                    print()

    if count == 0:
        print("No matches found")


def list_model_changes(messages: list[dict]) -> None:
    """List all model changes in session."""
    print("\n🔄 Model changes:\n")
    changes = [m for m in messages if m.get("type") == "model_change"]
    if not changes:
        print("No model changes")
        return

    prev_provider = None
    prev_model = None

    for mc in changes:
        ts = mc.get("timestamp", "")
        provider = mc.get("provider") or "unknown"
        model = mc.get("modelId") or "unknown"

        # Detect fallback
        indicator = ""
        if prev_provider and prev_model:
            if provider != prev_provider or model != prev_model:
                indicator = " [FALLBACK/RESET]"

        print(f"   {ts} → {provider}/{model}{indicator}")

        prev_provider = provider
        prev_model = model


def detect_model_issues(messages: list[dict]) -> None:
    """Detect model-related issues like errors, fallbacks, context overflow."""
    print("\n⚠️ Model/Provider Issues:\n")

    issues = []

    # Check for model_change with null values (often means fallback/reset)
    for mc in messages:
        if mc.get("type") == "model_change":
            if not mc.get("provider") or not mc.get("modelId"):
                issues.append(
                    {
                        "ts": mc.get("timestamp"),
                        "type": "model_reset",
                        "detail": "Model reset to default (possible fallback)",
                    }
                )

    # Check for context overflow errors
    for msg in messages:
        if msg.get("type") == "message":
            content = msg.get("message", {}).get("content", [])
            for c in content:
                if c.get("type") == "toolResult":
                    error = c.get("error", "")
                    if error and any(
                        kw in str(error).lower()
                        for kw in ["context_length", "max_tokens", "rate limit", "quota"]
                    ):
                        issues.append(
                            {
                                "ts": msg.get("timestamp"),
                                "type": "context_error",
                                "detail": error[:100],
                            }
                        )

    if not issues:
        print("   No model issues detected ✅")
        return

    for issue in issues:
        print(f"   [{issue['ts']}] {issue['type']}: {issue['detail']}")


def main():
    parser = argparse.ArgumentParser(description="OpenClaw Session Query Tool")
    parser.add_argument("session", nargs="?", help="Session ID or session key")
    parser.add_argument("--key", help="Session key (e.g., agent:main:telegram:group:-5142412129)")
    parser.add_argument("--agent", default="main", help="Agent ID (default: main)")
    parser.add_argument("--summary", action="store_true", help="Show session summary")
    parser.add_argument("--tail", type=int, default=0, help="Show last N messages")
    parser.add_argument("--errors", action="store_true", help="Show only errors")
    parser.add_argument("--tools", action="store_true", help="Show tool usage")
    parser.add_argument("--search", help="Search for keyword")
    parser.add_argument("--models", action="store_true", help="Show model changes")
    parser.add_argument(
        "--issues", action="store_true", help="Detect model issues (fallbacks, errors)"
    )
    parser.add_argument("--limit", type=int, default=20, help="Search result limit")

    args = parser.parse_args()

    # Get session ID/key
    session_id_or_key = args.session or args.key
    if not session_id_or_key:
        parser.print_help()
        return

    # Get session info
    session_info = get_session_info(session_id_or_key, args.agent)
    if not session_info:
        print(f"Error: Session not found for '{session_id_or_key}'", file=sys.stderr)
        # Show available keys as hint
        sessions = get_sessions_index(args.agent)
        if sessions:
            print(f"\nAvailable session keys ({len(sessions)} total):", file=sys.stderr)
            for k in list(sessions.keys())[:10]:
                print(f"   {k}", file=sys.stderr)
        sys.exit(1)

    # Get session file
    session_file = get_session_file(session_info)
    if not session_file or not session_file.exists():
        print(f"Error: Session file not found: {session_file}", file=sys.stderr)
        sys.exit(1)

    # Load session
    messages = load_session(session_file)
    session_info.messages = messages

    # Execute requested operations
    if args.summary or (
        not args.tail
        and not args.errors
        and not args.tools
        and not args.search
        and not args.models
        and not args.issues
    ):
        print_summary(session_info, messages)

    if args.tail > 0:
        print_tail(messages, args.tail)

    if args.errors:
        print_errors(messages)

    if args.tools:
        print_tool_usage(messages)

    if args.search:
        search_messages(messages, args.search, args.limit)

    if args.models:
        list_model_changes(messages)

    if args.issues:
        detect_model_issues(messages)


if __name__ == "__main__":
    main()
