#!/usr/bin/env python3
"""
Stop hook — fires after every Claude turn.

Throttled: only evaluates focus on every 5th turn OR when edit velocity
triggers early (3 of the last 4 edits in the same directory).

Focus detection reads the session JSONL transcript and looks at which
directories the most recent tool-use edits touched. If focus has narrowed
AND at least one compaction has occurred, writes focus-suggestion.json
so the next UserPromptSubmit can surface it.

Also writes a .session-stored marker check for the SessionEnd fallback.

Teaches: Stop fires on every turn — throttle aggressively and exit fast.
All evaluation is structural (path parsing), no LLM call.
"""

import json
import sys
from collections import Counter
from pathlib import Path

DATA_DIR = Path(__file__).parent.parent / "data"
TURN_COUNTER = DATA_DIR / "turn-counter.json"
FOCUS_SUGGESTION = DATA_DIR / "focus-suggestion.json"
ROLLING_SUMMARY = DATA_DIR / "rolling-summary.json"
SESSION_STORED = DATA_DIR / ".session-stored"

EVAL_EVERY_N_TURNS = 5
VELOCITY_WINDOW = 4        # look at last N edits
VELOCITY_THRESHOLD = 3     # if this many of the window hit one dir, trigger early
NARROWING_THRESHOLD = 3    # of last N_RECENT_EDITS, how many must share a dir
N_RECENT_EDITS = 4


def read_counter() -> dict:
    if TURN_COUNTER.exists():
        try:
            return json.loads(TURN_COUNTER.read_text())
        except Exception:
            pass
    return {"turn": 0, "last_dirs": []}


def write_counter(data: dict) -> None:
    TURN_COUNTER.write_text(json.dumps(data))


def extract_edited_dirs(transcript_path: str) -> list[str]:
    """
    Parse the session JSONL for tool_use blocks that wrote/edited files.
    Returns the parent directory of each file touched, most recent last.

    This is what "turns 3, 4, 5 all touch src/auth/" means in practice:
    we look at the tool_use inputs for Write/Edit/MultiEdit calls, extract
    the file_path argument, and take its parent directory. That gives us
    a sequence of directories across recent turns.
    """
    dirs = []
    edit_tools = {"Write", "Edit", "MultiEdit", "NotebookEdit"}

    try:
        with open(transcript_path) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue

                content = entry.get("content", [])
                if not isinstance(content, list):
                    continue

                for block in content:
                    if not isinstance(block, dict):
                        continue
                    if block.get("type") != "tool_use":
                        continue
                    if block.get("name") not in edit_tools:
                        continue

                    inp = block.get("input", {})
                    file_path = inp.get("file_path") or inp.get("path", "")
                    if file_path:
                        parent = str(Path(file_path).parent)
                        dirs.append(parent)
    except Exception:
        pass

    return dirs


def check_focus_narrowing(dirs: list[str]) -> tuple[bool, str, int, int]:
    """
    Returns (narrowed, directory, edit_count_in_dir, total_recent_edits).

    Two triggers:
    1. Edit velocity: 3 of last 4 edits in one dir (catches fast narrowing)
    2. Steady state: evaluated every 5 turns, same ratio over last 4 edits

    Both use the same threshold — this means the velocity trigger just
    evaluates sooner rather than using a different rule.
    """
    if len(dirs) < VELOCITY_WINDOW:
        return False, "", 0, 0

    recent = dirs[-VELOCITY_WINDOW:]
    counts = Counter(recent)
    top_dir, top_count = counts.most_common(1)[0]

    if top_dir in (".", ""):
        return False, "", 0, 0

    if top_count >= VELOCITY_THRESHOLD:
        return True, top_dir, top_count, len(recent)

    return False, "", 0, 0


def compaction_count() -> int:
    if not ROLLING_SUMMARY.exists():
        return 0
    try:
        summary = json.loads(ROLLING_SUMMARY.read_text())
        return len(summary.get("epochs", []))
    except Exception:
        return 0


def main():
    raw = sys.stdin.read()
    try:
        hook_input = json.loads(raw)
    except json.JSONDecodeError:
        sys.exit(0)

    DATA_DIR.mkdir(parents=True, exist_ok=True)

    counter = read_counter()
    counter["turn"] += 1
    turn = counter["turn"]

    transcript_path = hook_input.get("transcript_path", "")
    edited_dirs = extract_edited_dirs(transcript_path) if transcript_path else []

    # Update rolling dir history for velocity detection
    counter["last_dirs"] = (counter.get("last_dirs", []) + edited_dirs)[-20:]

    # Velocity trigger: check every turn (cheap — just Counter on a short list)
    narrowed, directory, edit_count, total = check_focus_narrowing(counter["last_dirs"])
    should_suggest = narrowed and not FOCUS_SUGGESTION.exists()

    # Throttled full eval: every N turns (already covered by velocity above,
    # but keeps the turn rhythm for future expansion)
    if not narrowed and (turn % EVAL_EVERY_N_TURNS == 0):
        narrowed, directory, edit_count, total = check_focus_narrowing(counter["last_dirs"])
        should_suggest = narrowed and not FOCUS_SUGGESTION.exists()

    if should_suggest:
        n_compactions = compaction_count()
        # Only surface suggestion if focus has truly narrowed AND session has
        # some depth (5+ turns) — avoids false positives on small sessions
        if turn >= 5:
            suggestion = {
                "directory": directory,
                "edit_count_in_dir": edit_count,
                "total_recent_edits": total,
                "compaction_count": n_compactions,
                "detected_at_turn": turn,
            }
            FOCUS_SUGGESTION.write_text(json.dumps(suggestion))
            # Reset dir history so we don't re-trigger immediately
            counter["last_dirs"] = []

    write_counter(counter)
    sys.exit(0)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        sys.exit(0)
