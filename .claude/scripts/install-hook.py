#!/usr/bin/env python3
"""
install-hook.py — Install the sessions manager SessionStart hook into your
chosen Claude Code settings file.

Three modes:
  project    .claude/settings.json in this repo (default, already set up)
  directory  A parent directory you specify — applies to all repos nested under it
  global     ~/.claude/settings.json — fires on every Claude Code session

Usage:
  python3 .claude/scripts/install-hook.py --mode project
  python3 .claude/scripts/install-hook.py --mode directory --target ~/dev/FamilySearch
  python3 .claude/scripts/install-hook.py --mode global

See SETUP.md for a full explanation of each mode and its trade-offs.
"""

import argparse
import json
import sys
from pathlib import Path

MARKER = "session-startup.py"


def script_path() -> str:
    return str((Path(__file__).parent / "session-startup.py").resolve())


def load(path: Path) -> dict:
    if path.exists():
        try:
            return json.loads(path.read_text())
        except json.JSONDecodeError as e:
            print(f"Error: could not parse {path}: {e}")
            sys.exit(1)
    return {}


def save(path: Path, settings: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(settings, indent=2) + "\n")


def already_installed(settings: dict) -> bool:
    for entry in settings.get("hooks", {}).get("SessionStart", []):
        for h in entry.get("hooks", []):
            if MARKER in h.get("command", ""):
                return True
    return False


def inject(settings: dict, cmd: str) -> dict:
    settings.setdefault("hooks", {}).setdefault("SessionStart", [])
    settings["hooks"]["SessionStart"].append({"hooks": [{"type": "command", "command": cmd}]})
    return settings


def resolve_settings_path(mode: str, target: str | None) -> Path:
    if mode == "project":
        return Path(__file__).parent.parent / "settings.json"
    if mode == "global":
        return Path.home() / ".claude" / "settings.json"
    if mode == "directory":
        if not target:
            print("Error: --target <path> is required for --mode directory")
            sys.exit(1)
        return Path(target).expanduser().resolve() / ".claude" / "settings.json"
    print(f"Error: unknown mode '{mode}'")
    sys.exit(1)


def main() -> None:
    parser = argparse.ArgumentParser(description="Install sessions manager SessionStart hook")
    parser.add_argument(
        "--mode",
        choices=["project", "directory", "global"],
        default="project",
        help="Which settings file to install into",
    )
    parser.add_argument(
        "--target",
        default=None,
        help="Directory path for --mode directory (e.g. ~/dev/FamilySearch)",
    )
    args = parser.parse_args()

    sp = script_path()
    settings_path = resolve_settings_path(args.mode, args.target)
    settings = load(settings_path)

    if already_installed(settings):
        print(f"Already installed in {settings_path}")
        print(f"  script: {sp}")
        return

    cmd = f"python3 '{sp}'"
    settings = inject(settings, cmd)
    save(settings_path, settings)

    print(f"Hook installed.")
    print(f"  settings: {settings_path}")
    print(f"  command:  {cmd}")
    print()

    if args.mode == "project":
        print("Scope: this repo only.")
    elif args.mode == "directory":
        print(f"Scope: all repos under {Path(args.target).expanduser().resolve()}")
    elif args.mode == "global":
        print("Scope: every Claude Code session on this machine.")

    print()
    print("Note: if you move this repo, re-run this script to update the absolute path.")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(0)
