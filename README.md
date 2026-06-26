# Sessions Management System

A Claude Code add-on that gives every AI session memory of your previous conversations. At the start of each session Claude automatically reads your recent work history and injects relevant context — what you discussed, what was decided, and what's still pending — without any manual effort.

---

## What It Does

Each conversation is recorded as a structured session entry: initiative, repo, Jira tickets, themes, key subjects, a one-sentence summary, and action items. A `SessionStart` hook injects the five most recent relevant sessions before your first message. A feedback learning agent tracks miscommunications over time and surfaces corrective instructions back to the primary agent.

**The result:** Claude knows where you left off, references past decisions specifically, and stops asking you to repeat context you've already given.

---

## Quick Start

```bash
git clone <this-repo>
cd session-manager
python3 .claude/scripts/install-hook.py --mode directory --target ~/dev/your-repos
```

Then open Claude Code in any repo under that directory. The `SESSIONS CONTEXT` block will appear at the start of your next session.

See [SETUP.md](SETUP.md) for all three installation modes and how to choose between them.

---

## Installation Modes

| Mode | Scope | Command |
|------|-------|---------|
| **Project** | This repo only (already configured) | *(no action needed)* |
| **Directory** | All repos under a parent folder | `install-hook.py --mode directory --target <path>` |
| **Global** | Every Claude Code session | `install-hook.py --mode global` |

The **directory mode** is the recommended starting point. It matches how most engineers already organize repos — all work under one parent folder — and avoids firing the hook on unrelated personal projects.

> **Note:** Modes 2 and 3 require an absolute path to `session-startup.py` and are therefore machine-specific. The installer generates that path for you. If you move this repo, re-run the installer to update it. See [SETUP.md](SETUP.md) for full details.

---

## File Structure

```
.claude/
├── agents/
│   ├── sessions-manager.md      # Retrieves and stores session context
│   └── feedback-learning.md     # Learns from miscommunications
├── scripts/
│   ├── session-startup.py       # SessionStart hook — injects context at session open
│   ├── install-hook.py          # Installs the hook into your chosen settings scope
│   ├── query-sessions.py        # Filters sessions.json by initiative + repo
│   ├── list-repos.py            # Lists repos by initiative
│   └── validate-entry.py        # Validates session entry schema
├── data/                        # gitignored — local to your machine
│   ├── sessions.json
│   ├── feedback-log.json
│   ├── communication-profile.json
│   └── keywords-taxonomy.json
└── settings.json                # Project-scope hook + MCP permissions
```

Committed files (agents, scripts, taxonomy, CLAUDE.md) are safe to share. All personal data lives in `.claude/data/` and is gitignored.

---

## How Sessions Are Stored

Each entry follows this schema:

```json
{
  "timestamp": "2026-06-25T14:30:00Z",
  "initiative": { "name": "Platform Modernization", "id": "INIT-42" },
  "repo": "my-repo",
  "jira_tickets": ["FS-1234"],
  "themes": ["authentication", "performance"],
  "key_subjects": ["token expiration", "caching layer"],
  "tags": ["backend", "security"],
  "summary": "Decided on 24-hour sliding window for session tokens.",
  "action_items": ["benchmark caching approach", "review with team"]
}
```

The `sessions-manager` agent handles storage and retrieval. It uses Atlassian MCP to resolve Jira tickets to their parent initiative automatically.

---

## Feedback Learning

When Claude misunderstands something and you correct it, invoke the `feedback-learning` agent. It logs the miscommunication, detects recurring patterns, and builds a communication profile that gets injected into future sessions. After three occurrences of the same pattern type, a corrective instruction is added to your profile and surfaced at the start of every session.

---

## Requirements

- Claude Code with an Atlassian MCP server configured (for Jira initiative resolution)
- Python 3.9+
- No additional packages — all scripts use the standard library

---

## Sharing with Your Team

Clone the repo, run the installer with your preferred scope, and your personal data files start accumulating locally. Each engineer gets their own `sessions.json` and communication profile. The taxonomy and agent definitions evolve from the same shared starting point.

For team-wide session sharing (so engineers can see each other's context), replace the local `sessions.json` with a shared store — a team S3 bucket or a shared git-tracked file are the natural next steps.
