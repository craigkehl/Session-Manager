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

DATA_DIR = Path(__file__).parent.parent / "data"
ROLLING_SUMMARY = DATA_DIR / "rolling-summary.json"
REINJECT_FLAG = DATA_DIR / "pending-reinject.flag"


def extract_text(content) -> str:
    """Flatten assistant content (string or list of blocks) to plain text."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict):
                parts.append(block.get("text", ""))
        return " ".join(parts)
    return ""


def parse_transcript(transcript_path: str) -> list[dict]:
    turns = []
    try:
        with open(transcript_path) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    turns.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    except Exception:
        pass
    return turns


def extract_epoch(turns: list[dict]) -> dict:
    """
    Structurally extract key information from a turn list without an LLM call.
    Fast, deterministic, no token cost.
    """
    user_messages = []
    assistant_messages = []
    files_mentioned = set()
    action_items = []

    # Patterns for structural extraction
    file_pattern = re.compile(r'[\w./\-]+\.(?:py|ts|tsx|js|jsx|md|json|yaml|yml|sh|env|toml|cfg)\b')
    action_patterns = [
        re.compile(r"(?:we('ll| will)|next step|todo|action item|need to|should|will need)[^.!?\n]{5,80}", re.IGNORECASE),
        re.compile(r"^\s*[-*]\s+(?:TODO|FIXME|NOTE|ACTION):\s*.+", re.MULTILINE),
    ]

    for turn in turns:
        role = turn.get("role", "")
        content = extract_text(turn.get("content", ""))
        if not content:
            continue

        if role == "user":
            user_messages.append(content[:300])
            for f in file_pattern.findall(content):
                files_mentioned.add(f)

        elif role == "assistant":
            assistant_messages.append(content[:400])
            for f in file_pattern.findall(content):
                files_mentioned.add(f)
            for pat in action_patterns:
                for match in pat.findall(content):
                    item = match.strip()
                    if len(item) > 10 and item not in action_items:
                        action_items.append(item[:120])

    # Summarize themes from last 5 user turns (most recent intent)
    recent_user = user_messages[-5:] if user_messages else []

    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "turn_count": len([t for t in turns if t.get("role") in ("user", "assistant")]),
        "recent_user_intent": recent_user,
        "files_touched": sorted(files_mentioned)[:30],
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

    turns = parse_transcript(transcript_path)
    if not turns:
        sys.exit(0)

    epoch = extract_epoch(turns)
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
