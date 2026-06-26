#!/usr/bin/env python3
"""
UserPromptSubmit hook — fires before each user prompt reaches Claude.

Does real work only when one of two flag files exists:
  pending-reinject.flag  — a compaction just happened, inject rolling summary
  focus-suggestion.json  — focus has narrowed, inject branch/compact suggestion

Teaches: hooks can inject context at the right moment without the LLM
having to remember to ask for it. JSON shapes make the injection predictable
and auditable.
"""

import json
import sys
from pathlib import Path

DATA_DIR = Path(__file__).parent.parent / "data"
ROLLING_SUMMARY = DATA_DIR / "rolling-summary.json"
REINJECT_FLAG = DATA_DIR / "pending-reinject.flag"
FOCUS_SUGGESTION = DATA_DIR / "focus-suggestion.json"


def format_rolling_summary(summary: dict) -> str:
    epochs = summary.get("epochs", [])
    if not epochs:
        return ""

    lines = [
        "--- CONTEXT RECOVERED AFTER COMPACTION ---",
        f"This session has been compacted {len(epochs)} time(s). "
        "The following was captured before each compaction:",
        "",
    ]

    for i, epoch in enumerate(epochs, 1):
        lines.append(f"Epoch {i} ({epoch.get('timestamp', '')[:10]}, "
                     f"{epoch.get('turn_count', 0)} turns, "
                     f"{epoch.get('compaction_type', 'auto')} compaction):")

        intent = epoch.get("recent_user_intent", [])
        if intent:
            lines.append("  Recent focus:")
            for msg in intent[-3:]:
                lines.append(f"    - {msg[:200]}")

        files = epoch.get("files_touched", [])
        if files:
            lines.append(f"  Files in scope: {', '.join(files[:10])}")

        actions = epoch.get("extracted_action_items", [])
        if actions:
            lines.append("  Captured action items:")
            for a in actions[:5]:
                lines.append(f"    - {a}")

        lines.append("")

    lines.append("--- END RECOVERED CONTEXT ---")
    return "\n".join(lines)


def format_focus_suggestion(suggestion: dict) -> str:
    directory = suggestion.get("directory", "")
    edit_count = suggestion.get("edit_count_in_dir", 0)
    total_edits = suggestion.get("total_recent_edits", 0)
    compaction_count = suggestion.get("compaction_count", 0)

    lines = [
        "--- FOCUS NARROWING DETECTED ---",
        f"{edit_count} of your last {total_edits} edits are in: {directory}",
    ]

    if compaction_count > 0:
        lines.append(
            f"This session has also been compacted {compaction_count} time(s). "
            "Earlier instructions and context may no longer be visible to Claude."
        )

    lines += [
        "",
        "Consider one of:",
        f'  /compact "focus on {directory} only"',
        "    Prunes context to just the relevant scope — often fixes Claude",
        "    ignoring earlier instructions or losing track of constraints.",
        "",
        "  Start a new Claude Code session for this focused work",
        "    Paste only the context relevant to this specific problem.",
        "",
        "--- END SUGGESTION ---",
    ]
    return "\n".join(lines)


def main():
    raw = sys.stdin.read()
    try:
        json.loads(raw)  # validate input but we don't need fields
    except json.JSONDecodeError:
        sys.exit(0)

    additional_context_parts = []

    # Check for post-compaction reinject
    if REINJECT_FLAG.exists():
        try:
            summary = json.loads(ROLLING_SUMMARY.read_text())
            context = format_rolling_summary(summary)
            if context:
                additional_context_parts.append(context)
        except Exception:
            pass
        finally:
            REINJECT_FLAG.unlink(missing_ok=True)

    # Check for focus narrowing suggestion
    if FOCUS_SUGGESTION.exists():
        try:
            suggestion = json.loads(FOCUS_SUGGESTION.read_text())
            context = format_focus_suggestion(suggestion)
            if context:
                additional_context_parts.append(context)
        except Exception:
            pass
        finally:
            FOCUS_SUGGESTION.unlink(missing_ok=True)

    if not additional_context_parts:
        sys.exit(0)

    output = {
        "hookSpecificOutput": {
            "hookEventName": "UserPromptSubmit",
            "additionalContext": "\n\n".join(additional_context_parts),
        }
    }
    print(json.dumps(output))
    sys.exit(0)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        sys.exit(0)
