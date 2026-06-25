#!/usr/bin/env python3
"""
Session startup script — runs via SessionStart hook.
Outputs a SESSIONS CONTEXT block injected before the first exchange.
At startup the initiative is unknown, so returns the 5 most recent sessions
across all initiatives plus the active communication profile.
"""

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

DATA_DIR = Path(__file__).parent.parent / "data"
SESSIONS_FILE = DATA_DIR / "sessions.json"
PROFILE_FILE = DATA_DIR / "communication-profile.json"


def detect_repo() -> str:
    try:
        result = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0:
            url = result.stdout.strip()
            # Extract repo name from URL (last path component, strip .git)
            name = url.rstrip("/").split("/")[-1]
            if name.endswith(".git"):
                name = name[:-4]
            return name
    except Exception:
        pass
    return "unknown"


def fmt_date(ts: str) -> str:
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        return dt.strftime("%Y-%m-%d")
    except Exception:
        return ts[:10] if len(ts) >= 10 else ts


def main():
    repo = detect_repo()

    sessions = []
    if SESSIONS_FILE.exists():
        try:
            sessions = json.loads(SESSIONS_FILE.read_text())
        except Exception:
            pass

    if not sessions:
        print(f"SESSIONS CONTEXT\n----------------\nNo prior sessions found. This is the first session tracked in this project.\nCurrent repo: {repo}")
        return

    # Sort newest first, take 5 most recent
    sorted_sessions = sorted(sessions, key=lambda s: s.get("timestamp", ""), reverse=True)
    recent = sorted_sessions[:5]

    # Group by initiative for display
    lines = ["SESSIONS CONTEXT", "----------------"]
    lines.append(f"Current repo: {repo}")
    lines.append(f"Total sessions on record: {len(sessions)}")
    lines.append("")
    lines.append("Recent sessions (most recent first):")

    for entry in recent:
        initiative = entry.get("initiative", {})
        init_name = initiative.get("name", "unknown")
        entry_repo = entry.get("repo", "unknown")
        date = fmt_date(entry.get("timestamp", ""))
        summary = entry.get("summary", "")
        action_items = entry.get("action_items", [])
        ai_str = ", ".join(action_items) if action_items else "none"

        lines.append(f"  - {date} [{init_name} / {entry_repo}]: {summary}")
        lines.append(f"    Action items: {ai_str}")

    # Active communication guidance
    profile_patterns = []
    if PROFILE_FILE.exists():
        try:
            profile = json.loads(PROFILE_FILE.read_text())
            profile_patterns = [
                p["reinforcement_instruction"]
                for p in profile.get("patterns", [])
                if p.get("occurrences", 0) >= 3 and p.get("reinforcement_instruction")
            ]
        except Exception:
            pass

    if profile_patterns:
        lines.append("")
        lines.append("Active communication guidance:")
        for inst in profile_patterns:
            lines.append(f"  - {inst}")

    lines.append("")
    lines.append("Note: Invoke sessions-manager with ACTION: retrieve + HINT_TICKET once a Jira ticket is mentioned to get initiative-filtered context.")

    print(json.dumps({"systemMessage": "\n".join(lines)}))


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        # Output valid JSON even on failure so the hook doesn't silently break
        print(json.dumps({"systemMessage": f"Sessions startup error: {e}"}))
        sys.exit(0)
