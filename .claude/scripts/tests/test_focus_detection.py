#!/usr/bin/env python3
"""
Tests for transcript parsing and focus detection.

Run: python3 .claude/scripts/tests/test_focus_detection.py

These guard against the schema-regression bug that shipped originally: the
hooks read entry["content"] when the real transcript nests content under
entry["message"]["content"]. The fixture uses the REAL nested schema, so if
anyone reverts to flat parsing, these tests fail loudly instead of the
feature silently never firing.

No test framework dependency — plain asserts, stdlib only.
"""

import sys
from pathlib import Path

# Make the scripts dir importable
SCRIPTS_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(SCRIPTS_DIR))

import transcript_utils as tx  # noqa: E402

FIXTURE = str(Path(__file__).parent / "fixture-transcript.jsonl")

passed = 0
failed = 0


def check(name: str, cond: bool):
    global passed, failed
    if cond:
        passed += 1
        print(f"  PASS  {name}")
    else:
        failed += 1
        print(f"  FAIL  {name}")


def test_edited_paths_parsed():
    paths = tx.edited_file_paths(FIXTURE)
    # 4 edit/write tool_uses in the fixture
    check("edited_file_paths finds all 4 edits", len(paths) == 4)
    check("first edit is tokens.py", paths[0].endswith("auth/tokens.py"))
    check("includes nested handler edits",
          any(p.endswith("handlers/login.py") for p in paths))


def test_role_text_parsed():
    pairs = list(tx.iter_role_text(FIXTURE))
    roles = [r for r, _ in pairs]
    check("captures user and assistant turns",
          "user" in roles and "assistant" in roles)
    # thinking + text both flattened
    joined = " ".join(t for _, t in pairs)
    check("flattens thinking blocks", "token handler" in joined)
    check("flattens text blocks", "session validator" in joined)
    check("ignores system entries without message",
          all(r in ("user", "assistant") for r in roles))


def _load(filename: str, module_name: str):
    """Load a hyphenated script file as an importable module."""
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        module_name, str(SCRIPTS_DIR / filename))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_focus_narrowing_fires():
    mod = _load("session-checkpoint.py", "session_checkpoint")

    dirs = mod.edit_dirs(FIXTURE)
    # All 4 edits live under /proj/src/auth (some in handlers/ subdir)
    check("edit_dirs derived from real schema (non-empty)", len(dirs) == 4)

    narrowed, directory, count, window = mod.check_focus_narrowing(dirs)
    check("focus narrowing detected on clustered edits", narrowed is True)
    check("cluster resolves to the auth subtree",
          directory.endswith("src/auth"))
    check("at least 3 edits in the cluster", count >= 3)


def test_no_narrowing_when_scattered():
    mod = _load("session-checkpoint.py", "session_checkpoint")

    scattered = ["/proj/src/auth", "/proj/ui/components",
                 "/proj/docs", "/proj/build"]
    narrowed, *_ = mod.check_focus_narrowing(scattered)
    check("no narrowing when edits are scattered", narrowed is False)

    too_few = ["/proj/src/auth", "/proj/src/auth"]
    narrowed2, *_ = mod.check_focus_narrowing(too_few)
    check("no narrowing below the window size", narrowed2 is False)


def test_precompact_extracts_from_real_schema():
    mod = _load("session-precompact.py", "session_precompact")

    epoch = mod.extract_epoch(FIXTURE)
    check("precompact counts turns from nested schema", epoch["turn_count"] > 0)
    check("precompact captures edited files", len(epoch["files_touched"]) == 4)
    check("precompact captures recent user intent",
          any("authentication" in m for m in epoch["recent_user_intent"]))
    check("precompact extracts an action item",
          len(epoch["extracted_action_items"]) >= 1)


if __name__ == "__main__":
    print("Transcript parsing + focus detection tests\n")
    test_edited_paths_parsed()
    test_role_text_parsed()
    test_focus_narrowing_fires()
    test_no_narrowing_when_scattered()
    test_precompact_extracts_from_real_schema()
    print(f"\n{passed} passed, {failed} failed")
    sys.exit(1 if failed else 0)
