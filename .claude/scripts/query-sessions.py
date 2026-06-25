#!/usr/bin/env python3
"""Query sessions.json by initiative and repo, returning summaries for primary and cross-repo sessions."""

import argparse
import json
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

DATA_DIR = Path(__file__).parent.parent / "data"
SESSIONS_FILE = DATA_DIR / "sessions.json"


def iso_to_dt(ts: str) -> datetime:
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


def summarize(entry: dict) -> dict:
    return {
        "timestamp": entry.get("timestamp"),
        "repo": entry.get("repo"),
        "jira_tickets": entry.get("jira_tickets", []),
        "themes": entry.get("themes", []),
        "key_subjects": entry.get("key_subjects", []),
        "summary": entry.get("summary", ""),
        "action_items": entry.get("action_items", []),
    }


def main():
    parser = argparse.ArgumentParser(description="Query sessions by initiative and repo")
    parser.add_argument("--initiative-id", required=True, help="Initiative ID to filter by")
    parser.add_argument("--repo", default=None, help="Repo name for primary filter")
    parser.add_argument("--max-recent", type=int, default=5, help="Max primary sessions to return")
    parser.add_argument("--cross-repo-days", type=int, default=7, help="Days back for cross-repo sessions")
    args = parser.parse_args()

    if not SESSIONS_FILE.exists():
        print(json.dumps({"primary": [], "cross_repo": [], "total_searched": 0}))
        return

    sessions = json.loads(SESSIONS_FILE.read_text())
    total = len(sessions)
    cutoff = datetime.now(timezone.utc) - timedelta(days=args.cross_repo_days)

    primary = []
    cross_repo = []

    sorted_sessions = sorted(sessions, key=lambda s: s.get("timestamp", ""), reverse=True)

    for entry in sorted_sessions:
        initiative_id = entry.get("initiative", {}).get("id", "")
        repo = entry.get("repo", "")

        if initiative_id != args.initiative_id:
            continue

        if args.repo and repo == args.repo:
            if len(primary) < args.max_recent:
                primary.append(summarize(entry))
        elif args.repo and repo != args.repo:
            try:
                entry_dt = iso_to_dt(entry.get("timestamp", "1970-01-01T00:00:00Z"))
                if entry_dt >= cutoff:
                    cross_repo.append(summarize(entry))
            except ValueError:
                pass
        elif not args.repo:
            if len(primary) < args.max_recent:
                primary.append(summarize(entry))

    print(json.dumps({"primary": primary, "cross_repo": cross_repo, "total_searched": total}))


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(json.dumps({"error": str(e)}), file=sys.stderr)
        sys.exit(1)
