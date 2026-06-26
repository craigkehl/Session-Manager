#!/usr/bin/env python3
"""
UserPromptSubmit hook — fires before each user prompt reaches Claude.

Three jobs, all gated so they stay silent unless there's something worth
injecting:
  1. pending-reinject.flag  — a compaction just happened, reinject rolling summary
  2. focus-suggestion.json  — focus has narrowed, inject branch/compact suggestion
  3. relevance retrieval     — rank past sessions against THIS prompt and inject
                               the most relevant ones (summary only, gated, deduped)

Job 3 is the just-in-time knowledge retrieval: instead of dumping recent
sessions at startup, we wait for the user's question and surface only past
sessions whose content is relevant to it. Ranking is delegated to
rank_sessions.py (deterministic TF-IDF, no LLM). A per-session dedup set
ensures no past session is injected more than once per current session, so
running on every turn never compounds into context bloat.

Teaches: hooks inject context at the right moment without the LLM having to
ask; scripts do the deterministic ranking; JSON shapes keep it auditable.
"""

import json
import subprocess
import sys
from pathlib import Path

DATA_DIR = Path(__file__).parent.parent / "data"
SCRIPTS_DIR = Path(__file__).parent
ROLLING_SUMMARY = DATA_DIR / "rolling-summary.json"
REINJECT_FLAG = DATA_DIR / "pending-reinject.flag"
FOCUS_SUGGESTION = DATA_DIR / "focus-suggestion.json"
INJECTED_SESSIONS = DATA_DIR / "injected-sessions.json"
RANK_SCRIPT = SCRIPTS_DIR / "rank_sessions.py"


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


def detect_repo() -> str:
    """Repo name from git origin (same approach as the other session scripts)."""
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
    return ""


def load_injected() -> set:
    if INJECTED_SESSIONS.exists():
        try:
            return set(json.loads(INJECTED_SESSIONS.read_text()))
        except Exception:
            pass
    return set()


def save_injected(injected: set) -> None:
    try:
        INJECTED_SESSIONS.write_text(json.dumps(sorted(injected)))
    except Exception:
        pass


def retrieve_relevant(prompt: str) -> str:
    """
    Rank past sessions against the prompt via rank_sessions.py, drop any
    already injected this session, and format the survivors as a compact
    block. Returns "" when nothing new clears the relevance gate.
    """
    if not prompt.strip() or not RANK_SCRIPT.exists():
        return ""

    repo = detect_repo()
    try:
        result = subprocess.run(
            ["python3", str(RANK_SCRIPT),
             "--query", prompt,
             "--current-repo", repo,
             "--top-k", "2"],
            capture_output=True, text=True, timeout=8,
        )
        if result.returncode != 0:
            return ""
        data = json.loads(result.stdout or "{}")
    except Exception:
        return ""

    matches = data.get("matches", [])
    if not matches:
        return ""

    already = load_injected()
    fresh = [m for m in matches if m.get("timestamp") not in already]
    if not fresh:
        return ""

    lines = ["--- RELEVANT PAST SESSIONS ---",
             "Past sessions related to your question:"]
    for m in fresh:
        date = (m.get("timestamp", "") or "")[:10]
        init = m.get("initiative", "unknown")
        repo_name = m.get("repo", "unknown")
        summary = m.get("summary", "")
        lines.append(f"  - [{date}] [{init} / {repo_name}]: {summary}")
        already.add(m.get("timestamp"))
    lines.append("Use /recall <topic> for full details including decisions.")
    lines.append("--- END RELEVANT SESSIONS ---")

    save_injected(already)
    return "\n".join(lines)


def main():
    raw = sys.stdin.read()
    try:
        hook_input = json.loads(raw)
    except json.JSONDecodeError:
        sys.exit(0)

    prompt = hook_input.get("prompt", "") if isinstance(hook_input, dict) else ""

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

    # Just-in-time relevance retrieval against the user's prompt
    relevant = retrieve_relevant(prompt)
    if relevant:
        additional_context_parts.append(relevant)

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
