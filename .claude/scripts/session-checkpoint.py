#!/usr/bin/env python3
"""
Stop hook — fires after every Claude turn.

Detects when work has narrowed onto one area of the codebase while the
context window is under pressure (a compaction has already happened). When
both are true, it writes focus-suggestion.json so the next UserPromptSubmit
can surface a /compact suggestion — addressing the common "why is Claude
ignoring my earlier instructions" confusion, whose real cause is that those
instructions have aged out of the active window.

Focus is measured structurally from the transcript: the directories of the
most recent file edits. If most of the last few edits cluster under one
directory subtree, focus has narrowed. No LLM call.

Cost: Stop fires every turn, so this exits fast. The only real work is
reading the transcript's tool_use blocks (a few hundred at most) and a
Counter over a short path list — sub-10ms.
"""

import json
import sys
from collections import Counter
from pathlib import Path

import transcript_utils as tx

DATA_DIR = Path(__file__).parent.parent / "data"
TURN_COUNTER = DATA_DIR / "turn-counter.json"
FOCUS_SUGGESTION = DATA_DIR / "focus-suggestion.json"
ROLLING_SUMMARY = DATA_DIR / "rolling-summary.json"

# Focus narrowing: of the last N edits, how many must share a directory subtree.
RECENT_EDITS_WINDOW = 4
NARROWING_THRESHOLD = 3
# Don't suggest until the session has real depth.
MIN_TURNS_BEFORE_SUGGEST = 5


def read_counter() -> dict:
    if TURN_COUNTER.exists():
        try:
            return json.loads(TURN_COUNTER.read_text())
        except Exception:
            pass
    return {"turn": 0, "last_suggested_dir": ""}


def write_counter(data: dict) -> None:
    try:
        TURN_COUNTER.write_text(json.dumps(data))
    except Exception:
        pass


def edit_dirs(transcript_path: str) -> list[str]:
    """Parent directory of each edited file, oldest first."""
    return [str(Path(p).parent) for p in tx.edited_file_paths(transcript_path)]


def deepest_shared_dir(dirs: list[str]) -> str:
    """
    Longest common path prefix (by path segment) of a set of directories.
    This is what lets edits to src/auth/ and src/auth/handlers/ count as the
    same focus area instead of two unrelated directories.
    """
    if not dirs:
        return ""
    split = [Path(d).parts for d in dirs]
    common = []
    for segments in zip(*split):
        first = segments[0]
        if all(s == first for s in segments):
            common.append(first)
        else:
            break
    if not common:
        return ""
    return str(Path(*common))


def check_focus_narrowing(dirs: list[str]) -> tuple[bool, str, int, int]:
    """
    Returns (narrowed, directory, edit_count_in_cluster, window_size).

    Looks at the last RECENT_EDITS_WINDOW edits. Clusters them by their
    deepest shared directory subtree; if NARROWING_THRESHOLD of them fall in
    the largest cluster, focus has narrowed onto that subtree.
    """
    if len(dirs) < RECENT_EDITS_WINDOW:
        return False, "", 0, 0

    recent = dirs[-RECENT_EDITS_WINDOW:]
    recent = [d for d in recent if d not in (".", "")]
    if not recent:
        return False, "", 0, 0

    # Most common exact directory in the window.
    top_dir, top_count = Counter(recent).most_common(1)[0]

    # Widen: also count edits that live under a shared subtree with the
    # leader, so a module split across subdirectories still clusters.
    cluster = [d for d in recent if d == top_dir or d.startswith(top_dir + "/")
               or top_dir.startswith(d + "/")]
    if len(cluster) > top_count:
        directory = deepest_shared_dir(cluster) or top_dir
        count = len(cluster)
    else:
        directory, count = top_dir, top_count

    if count >= NARROWING_THRESHOLD:
        return True, directory, count, len(recent)
    return False, "", 0, 0


def compaction_count() -> int:
    if not ROLLING_SUMMARY.exists():
        return 0
    try:
        return len(json.loads(ROLLING_SUMMARY.read_text()).get("epochs", []))
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

    # A suggestion is only useful once context is actually under pressure.
    # No compaction yet → nothing to suggest. This is also the cheapest gate,
    # so check it before parsing the transcript.
    n_compactions = compaction_count()
    transcript_path = hook_input.get("transcript_path", "")

    if (n_compactions > 0 and turn >= MIN_TURNS_BEFORE_SUGGEST
            and transcript_path and not FOCUS_SUGGESTION.exists()):
        dirs = edit_dirs(transcript_path)
        narrowed, directory, count, window = check_focus_narrowing(dirs)
        # Don't re-suggest the same directory we already flagged this session.
        if narrowed and directory != counter.get("last_suggested_dir", ""):
            FOCUS_SUGGESTION.write_text(json.dumps({
                "directory": directory,
                "edit_count_in_dir": count,
                "total_recent_edits": window,
                "compaction_count": n_compactions,
                "detected_at_turn": turn,
            }))
            counter["last_suggested_dir"] = directory

    write_counter(counter)
    sys.exit(0)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        sys.exit(0)
