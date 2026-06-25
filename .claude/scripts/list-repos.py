#!/usr/bin/env python3
"""List all distinct repos ever associated with a given initiative in sessions.json."""

import argparse
import json
import sys
from pathlib import Path

DATA_DIR = Path(__file__).parent.parent / "data"
SESSIONS_FILE = DATA_DIR / "sessions.json"


def main():
    parser = argparse.ArgumentParser(description="List repos for an initiative")
    parser.add_argument("--initiative-id", required=True, help="Initiative ID to look up")
    args = parser.parse_args()

    if not SESSIONS_FILE.exists():
        print(json.dumps({"initiative_id": args.initiative_id, "repos": []}))
        return

    sessions = json.loads(SESSIONS_FILE.read_text())
    repos = sorted({
        entry.get("repo", "")
        for entry in sessions
        if entry.get("initiative", {}).get("id", "") == args.initiative_id
        and entry.get("repo")
    })

    print(json.dumps({"initiative_id": args.initiative_id, "repos": repos}))


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(json.dumps({"error": str(e)}), file=sys.stderr)
        sys.exit(1)
