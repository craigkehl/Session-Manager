# Setup Guide — Sessions Management System

This guide explains how to install the `SessionStart` hook that powers automatic session context injection. There are three scope options — pick the one that matches how you work.

---

## How the Hook Works

When Claude Code starts a session, it runs `.claude/scripts/session-startup.py`. That script reads your local `sessions.json` and injects recent session summaries into the conversation before your first message. This requires an **absolute path** to the script because the hook runs from your project directory, not from this repo.

The installer (`install-hook.py`) resolves the absolute path from your current machine and writes it into the correct settings file automatically.

---

## Installation Modes

### Option 1 — Project Only (already configured)

The hook is pre-installed in `.claude/settings.json` in this repo. It fires only when Claude Code is opened inside this directory.

No action needed. This is the default.

---

### Option 2 — Directory Scope (recommended for team repos)

Install into a **parent directory** you specify. Claude Code walks up the directory tree and merges settings from each `.claude/settings.json` it finds, so every repo nested under that parent inherits the hook automatically.

**Best for:** engineers who keep all their work repos under a single folder (e.g. `~/dev/FamilySearch/`).

```bash
python3 .claude/scripts/install-hook.py --mode directory --target ~/dev/FamilySearch
```

This creates or updates `~/dev/FamilySearch/.claude/settings.json` with the hook pointing at the absolute path of `session-startup.py` on your machine.

**Result:** Every repo under `~/dev/FamilySearch/` automatically gets session context at the start of each Claude Code session.

---

### Option 3 — Global Scope

Install into `~/.claude/settings.json`. The hook fires on **every** Claude Code session on your machine, regardless of which directory you're in.

```bash
python3 .claude/scripts/install-hook.py --mode global
```

**Best for:** engineers who want cross-project memory even outside their work repos (personal projects, experiments, etc.).

**Trade-off:** fires on every session, including unrelated directories.

---

## If You Move This Repo

Because the hook uses an absolute path, **moving or renaming this repo breaks the hook silently** — no error, just no context injected. If you relocate the repo:

```bash
# Re-run the installer for whichever mode you chose
python3 .claude/scripts/install-hook.py --mode directory --target ~/dev/FamilySearch
```

The installer is idempotent — it won't duplicate the hook if one already exists, but it will update the path.

---

## Feeding This File to Your AI Client

If you open a session in another AI tool (not Claude Code) and want to set up this system, you can paste this entire file as context. Tell your AI:

> "Read SETUP.md and install the sessions management hook using the mode that makes sense for my setup. My repos live under [your path here]. Use install-hook.py."

The AI can run `install-hook.py` on your behalf once it knows your preferred scope and repo root.

---

## What Gets Installed

The installer writes a `SessionStart` hook entry like this into your chosen settings file:

```json
{
  "hooks": {
    "SessionStart": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "python3 '/absolute/path/to/.claude/scripts/session-startup.py'"
          }
        ]
      }
    ]
  }
}
```

It merges safely with any existing hooks or settings already in that file.

---

## Verifying the Install

After running the installer, open Claude Code in a repo that falls under your chosen scope. The first system message should include a `SESSIONS CONTEXT` block. If you see it, the hook is working.

If you don't see it, check:
1. The absolute path in the settings file still points to `session-startup.py`
2. Python 3 is available at `python3` on your PATH
3. The settings file is valid JSON (no trailing commas, no syntax errors)
