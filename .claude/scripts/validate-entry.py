#!/usr/bin/env python3
"""Validate a proposed sessions.json entry against the required schema."""

import argparse
import json
import re
import sys

ISO_8601_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?(Z|[+-]\d{2}:\d{2})$"
)


def validate(entry: dict) -> tuple[bool, list[str], list[str]]:
    errors = []
    warnings = []

    # Required string fields
    ts = entry.get("timestamp", "")
    if not ts:
        errors.append("missing required field: timestamp")
    elif not ISO_8601_RE.match(ts):
        errors.append(f"timestamp is not valid ISO 8601: {ts!r}")

    initiative = entry.get("initiative", {})
    if not isinstance(initiative, dict):
        errors.append("initiative must be an object with name and id")
    else:
        if not initiative.get("name", "").strip():
            errors.append("initiative.name must be a non-empty string")
        if not initiative.get("id", "").strip():
            errors.append("initiative.id must be a non-empty string")

    summary = entry.get("summary", "")
    if not summary.strip():
        errors.append("missing required field: summary")
    elif len(summary) > 200:
        warnings.append(f"summary exceeds 200 characters ({len(summary)} chars) — consider shortening")

    # Required array fields (may be empty)
    for field in ("jira_tickets", "themes", "key_subjects", "tags", "action_items"):
        val = entry.get(field)
        if val is None:
            errors.append(f"missing required field: {field}")
        elif not isinstance(val, list):
            errors.append(f"{field} must be an array")

    # repo required when jira_tickets is non-empty
    tickets = entry.get("jira_tickets", [])
    repo = entry.get("repo", "")
    if isinstance(tickets, list) and tickets and not repo:
        warnings.append("repo is empty but jira_tickets are present — consider setting repo")

    # Warn on unknown top-level keys
    known_keys = {"timestamp", "initiative", "repo", "jira_tickets", "themes",
                  "key_subjects", "tags", "summary", "action_items", "mcp_unresolved"}
    for key in entry:
        if key not in known_keys:
            warnings.append(f"unknown field: {key!r}")

    return len(errors) == 0, errors, warnings


def main():
    parser = argparse.ArgumentParser(description="Validate a session entry JSON")
    parser.add_argument("--entry-json", required=True, help="JSON string of proposed entry")
    args = parser.parse_args()

    try:
        entry = json.loads(args.entry_json)
    except json.JSONDecodeError as e:
        print(json.dumps({"valid": False, "errors": [f"invalid JSON: {e}"], "warnings": []}))
        sys.exit(1)

    valid, errors, warnings = validate(entry)
    print(json.dumps({"valid": valid, "errors": errors, "warnings": warnings}))
    if not valid:
        sys.exit(1)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(json.dumps({"valid": False, "errors": [str(e)], "warnings": []}), file=sys.stderr)
        sys.exit(1)
