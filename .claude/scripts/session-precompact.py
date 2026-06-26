#!/usr/bin/env python3
"""
PreCompact hook — fires before Claude compacts the context window.

Reads the session JSONL transcript, extracts a structured snapshot of what
is about to be shed, and appends it as a new epoch in rolling-summary.json.
Sets pending-reinject.flag so the next UserPromptSubmit reinjects the
accumulated summary back into context.

Teaches: use hooks + scripts for guaranteed capture instead of relying on
the LLM to remember to store context before it loses it.
"""

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import transcript_utils as tx

DATA_DIR = Path(__file__).parent.parent / "data"
ROLLING_SUMMARY = DATA_DIR / "rolling-summary.json"
REINJECT_FLAG = DATA_DIR / "pending-reinject.flag"


def extract_epoch(transcript_path: str) -> dict:
    """
    Structurally extract key information from the transcript without an LLM
    call. Fast, deterministic, no token cost.

    Files are taken from actual edit/write tool_use blocks (authoritative),
    not regex-scraped from prose — so this reflects what was really touched.
    """
    user_messages = []
    assistant_messages = []
    action_items = []

    # NOTE: use only NON-capturing groups (?:...) here. re.findall returns
    # captured groups instead of the full match when any group captures, which
    # would yield fragments like " will" instead of the whole action phrase.
    action_patterns = [
        re.compile(r"(?:we(?:'ll| will)|next step|todo|action item|need to|should|will need)[^.!?\n]{5,80}", re.IGNORECASE),
        re.compile(r"^\s*[-*]\s+(?:TODO|FIXME|NOTE|ACTION):\s*.+", re.MULTILINE),
    ]

    role_turns = 0
    for role, text in tx.iter_role_text(transcript_path):
        role_turns += 1
        if role == "user":
            user_messages.append(text[:300])
        elif role == "assistant":
            assistant_messages.append(text[:400])
            for pat in action_patterns:
                for match in pat.findall(text):
                    item = match.strip()
                    if len(item) > 10 and item not in action_items:
                        action_items.append(item[:120])

    # Files actually edited (from tool_use blocks), most recent kept.
    files_touched = []
    for path in tx.edited_file_paths(transcript_path):
        if path not in files_touched:
            files_touched.append(path)
    files_touched = files_touched[-30:]

    # Most recent user intent — captures where the session's focus landed.
    recent_user = user_messages[-5:] if user_messages else []

    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "turn_count": role_turns,
        "recent_user_intent": recent_user,
        "files_touched": files_touched,
        "extracted_action_items": action_items[:10],
        "assistant_excerpt": assistant_messages[-1][:500] if assistant_messages else "",
    }


def main():
    raw = sys.stdin.read()
    try:
        hook_input = json.loads(raw)
    except json.JSONDecodeError:
        sys.exit(0)

    transcript_path = hook_input.get("transcript_path", "")
    session_id = hook_input.get("session_id", "unknown")
    compaction_type = hook_input.get("compaction_type", "auto")

    if not transcript_path:
        sys.exit(0)

    epoch = extract_epoch(transcript_path)
    # Nothing meaningful extracted (empty/unreadable transcript) → skip.
    if epoch["turn_count"] == 0 and not epoch["files_touched"]:
        sys.exit(0)
    epoch["session_id"] = session_id
    epoch["compaction_type"] = compaction_type

    # Load or initialize rolling summary
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    summary = {"session_id": session_id, "epochs": []}
    if ROLLING_SUMMARY.exists():
        try:
            summary = json.loads(ROLLING_SUMMARY.read_text())
        except Exception:
            pass

    summary["epochs"].append(epoch)
    summary["last_compaction"] = epoch["timestamp"]
    ROLLING_SUMMARY.write_text(json.dumps(summary, indent=2))

    # Signal that next UserPromptSubmit should reinject this context
    REINJECT_FLAG.write_text(epoch["timestamp"])

    # Allow compaction to proceed
    sys.exit(0)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        sys.exit(0)
