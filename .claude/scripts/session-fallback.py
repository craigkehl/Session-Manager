#!/usr/bin/env python3
"""
SessionEnd hook — fires when a Claude Code session closes.

If the sessions-manager agent successfully stored a session entry during
the conversation, it writes .session-stored. If that marker is absent,
this script writes a minimal stub entry to sessions.json so every session
has at least a timestamped record.

Also cleans up turn counter and any stale flag files from this session.

Teaches: SessionEnd is the last line of defense. It cannot read the
conversation, so stubs are low-fidelity — but an incomplete record is
better than silence. The next session sees "session on DATE: summary not
captured" and can prompt a back-fill.
"""

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

DATA_DIR = Path(__file__).parent.parent / "data"
SESSIONS_FILE = DATA_DIR / "sessions.json"
SESSION_STORED = DATA_DIR / ".session-stored"
TURN_COUNTER = DATA_DIR / "turn-counter.json"
FOCUS_SUGGESTION = DATA_DIR / "focus-suggestion.json"
REINJECT_FLAG = DATA_DIR / "pending-reinject.flag"


def detect_repo() -> str:
    try:
        result = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0:
            name = result.stdout.strip().rstrip("/").split("/")[-1]
            return name[:-4] if name.endswith(".git") else name
    except Exception:
        pass
    return "unknown"


def turn_count() -> int:
    if TURN_COUNTER.exists():
        try:
            return json.loads(TURN_COUNTER.read_text()).get("turn", 0)
        except Exception:
            pass
    return 0


def main():
    # Clean up per-session state regardless of outcome
    for f in (TURN_COUNTER, FOCUS_SUGGESTION, REINJECT_FLAG):
        f.unlink(missing_ok=True)

    # If the agent already stored an entry, nothing left to do
    if SESSION_STORED.exists():
        SESSION_STORED.unlink(missing_ok=True)
        return

    # Only write a stub for sessions with meaningful depth
    turns = turn_count()
    if turns < 3:
        return

    repo = detect_repo()
    stub = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "initiative": {"name": "unknown", "id": "unknown"},
        "repo": repo,
        "jira_tickets": [],
        "themes": [],
        "key_subjects": [],
        "tags": [],
        "summary": f"Session ended without summary capture ({turns} turns). Back-fill recommended.",
        "action_items": ["back-fill this session summary"],
        "mcp_unresolved": True,
        "stub": True,
    }

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    sessions = []
    if SESSIONS_FILE.exists():
        try:
            sessions = json.loads(SESSIONS_FILE.read_text())
        except Exception:
            pass

    sessions.append(stub)
    SESSIONS_FILE.write_text(json.dumps(sessions, indent=2))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        sys.exit(0)
