# Sessions Management System

A Claude Code add-on that gives every AI session memory of your previous conversations. As you work, Claude surfaces relevant context from past sessions — what you discussed, what was decided, what's still pending — at the moment it's relevant, without any manual effort.

---

## What It Does

Each conversation is recorded as a structured session entry: initiative, repo, Jira tickets, themes, key subjects, decisions, a one-sentence summary, and action items.

Retrieval is **just-in-time and relevance-driven**, not a dump at startup. When you ask a question, a `UserPromptSubmit` hook ranks your past sessions against what you actually asked (deterministic TF-IDF scoring, no LLM) and injects only the ones that genuinely match — at most two, summary only, and never the same session twice in one conversation. If nothing is relevant, nothing is injected. `SessionStart` shows only a one-line "active" message; `/recall <topic>` searches history on demand.

A feedback learning agent tracks miscommunications over time and surfaces corrective instructions back to the primary agent.

**The result:** Claude pulls up the right past decision exactly when it matters, references it specifically, and stops asking you to repeat context you've already given — all without spending context on sessions that aren't relevant to the task at hand.

---

## Quick Start

```bash
git clone <this-repo>
cd session-manager
python3 .claude/scripts/install-hook.py --mode directory --target ~/dev/your-repos
```

Then open Claude Code in any repo under that directory. A one-line "sessions manager active" message appears at session start; relevant past context surfaces automatically as you ask questions.

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
├── commands/
│   └── recall.md                # /recall <topic> — on-demand history search
├── scripts/
│   ├── session-startup.py       # SessionStart hook — minimal "active" message
│   ├── session-context-inject.py # UserPromptSubmit — relevance retrieval + reinject
│   ├── session-precompact.py    # PreCompact — capture context before it's shed
│   ├── session-checkpoint.py    # Stop — focus-drift detection
│   ├── session-fallback.py      # SessionEnd — fallback stub + cleanup
│   ├── rank_sessions.py         # TF-IDF relevance engine (shared tokenizer)
│   ├── eval_ranking.py          # Dev-only: precision harness + threshold sweep
│   ├── install-hook.py          # Installs the hook into your chosen settings scope
│   ├── query-sessions.py        # Initiative/repo filter (used by retrieve action)
│   ├── list-repos.py            # Lists repos by initiative
│   └── validate-entry.py        # Validates session entry schema
├── data/                        # gitignored — local to your machine
│   ├── sessions.json
│   ├── feedback-log.json
│   ├── communication-profile.json
│   └── keywords-taxonomy.json
└── settings.json                # Project-scope hooks + MCP permissions
```

Committed files (agents, commands, scripts, taxonomy, CLAUDE.md) are safe to share. All personal data lives in `.claude/data/` and is gitignored.

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
  "action_items": ["benchmark caching approach", "review with team"],
  "decisions": ["use a 24-hour sliding window for token expiry"]
}
```

`decisions` captures durable, reusable conclusions (distinct from `action_items`, which go stale once done) — these are the highest-value thing a future session can recall. Each stored entry also carries a derived `_tokens` field (a precomputed normalized blob the ranker scores against) and an optional `files_touched` list folded from mid-session capture.

The `sessions-manager` agent handles storage and retrieval. It uses Atlassian MCP to resolve Jira tickets to their parent initiative automatically.

---

## How Retrieval Works

Relevance ranking is pure deterministic Python — no LLM, no embeddings service, no external dependencies:

- **TF-IDF cosine similarity** between your prompt and each stored session's content. IDF weighting means a rare, specific match (a distinctive `key_subject`) outranks a generic shared word.
- **Structured boosts** (multiplicative): same initiative ×1.5, same repo ×1.25, recency decay (30-day half-life). These re-rank among already-relevant results — they can't drag an off-topic session over the bar.
- **Hard gating**: a similarity threshold (nothing irrelevant gets injected), a top-2 cap, and a per-session dedup set so no past session is injected twice in one conversation. Most turns inject nothing and cost zero tokens.

`rank_sessions.py` is the engine; `eval_ranking.py` is a dev-only harness that measures retrieval precision against synthetic queries and calibrates the threshold. Run it any time after the corpus grows:

```bash
python3 .claude/scripts/eval_ranking.py
```

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
