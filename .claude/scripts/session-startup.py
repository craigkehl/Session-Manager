#!/usr/bin/env python3
"""
Session startup script — runs via SessionStart hook.

Outputs a MINIMAL "system active" message. At startup there is no user
prompt yet, so content-relevance retrieval cannot run — and dumping the 5
most recent sessions here would spend context on recency, not relevance.
That job now belongs to the UserPromptSubmit hook (session-context-inject.py),
which surfaces past sessions relevant to the actual question once it's asked.

So this script stays deliberately terse: confirm the system is active, show
the repo and session count, point at /recall, and surface any cross-cutting
communication guidance (which is not query-dependent).
"""

import json
import subprocess
import sys
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


def main():
    repo = detect_repo()

    sessions = []
    if SESSIONS_FILE.exists():
        try:
            sessions = json.loads(SESSIONS_FILE.read_text())
        except Exception:
            pass

    count = len(sessions)
    if count == 0:
        msg = ("Sessions manager active. No prior sessions on record yet — "
               f"this is the first tracked session (repo: {repo}).")
        print(json.dumps({"systemMessage": msg}))
        return

    lines = [
        f"Sessions manager active — {count} prior session(s) on record (repo: {repo}).",
        "Relevant past context will surface automatically as topics come up.",
        "Use /recall <topic> to search session history on demand.",
    ]

    # Active communication guidance is cross-cutting (not query-dependent),
    # so it's the one thing worth surfacing eagerly at startup.
    if PROFILE_FILE.exists():
        try:
            profile = json.loads(PROFILE_FILE.read_text())
            profile_patterns = [
                p["reinforcement_instruction"]
                for p in profile.get("patterns", [])
                if p.get("occurrences", 0) >= 3 and p.get("reinforcement_instruction")
            ]
            if profile_patterns:
                lines.append("")
                lines.append("Active communication guidance:")
                for inst in profile_patterns:
                    lines.append(f"  - {inst}")
        except Exception:
            pass

    print(json.dumps({"systemMessage": "\n".join(lines)}))


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        # Output valid JSON even on failure so the hook doesn't silently break
        print(json.dumps({"systemMessage": f"Sessions startup error: {e}"}))
        sys.exit(0)
