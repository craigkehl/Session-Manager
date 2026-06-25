# Section 6: Integration Design — Agent Communication in Claude Code

This document fills the gap not covered by sections 1–4: how the primary agent invokes the sessions-manager and feedback-learning agents within Claude Code, what inputs they receive, and what they return.

---

## How Claude Code Custom Agents Work

Claude Code discovers custom agents by scanning `.claude/agents/*.md` in the project directory. Each agent file has a YAML frontmatter block followed by the agent's system prompt.

The `name` field in frontmatter is the identifier used to invoke the agent. The primary agent (or Claude Code's Task tool) spawns a sub-agent by setting `subagent_type` to that name.

**Agent file format:**
```yaml
---
name: agent-name
description: When to use this agent (used by Claude Code to auto-suggest it)
tools: [Read, Write, Bash, ...]
model: claude-sonnet-4-6
---
[Agent system prompt body follows here]
```

---

## System Data Flow

```
┌─────────────────────────────────────────────────────────────────────┐
│                   CLAUDE CODE SESSION                                │
│                                                                     │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │                    PRIMARY AGENT                             │   │
│  │                                                             │   │
│  │  Guided by CLAUDE.md:                                       │   │
│  │  • Invokes sessions-manager (retrieve) at session start     │   │
│  │  • Invokes feedback-learning on any correction detected     │   │
│  │  • Invokes sessions-manager (store) at session end          │   │
│  └──────┬──────────────────────────────────────┬──────────────┘   │
│         │                                      │                   │
│         ▼                                      ▼                   │
│  ┌──────────────────┐                 ┌──────────────────────┐    │
│  │ sessions-manager │                 │  feedback-learning   │    │
│  │     agent        │                 │       agent          │    │
│  │                  │                 │                      │    │
│  │ Tools:           │                 │ Tools:               │    │
│  │ • Read/Write     │                 │ • Read/Write         │    │
│  │ • Bash (scripts) │                 │   (.claude/data/)    │    │
│  │ • Atlassian MCP  │                 └──────────┬───────────┘    │
│  └──────┬───────────┘                            │                │
│         │                                        │                │
│         ▼                                        ▼                │
│  ┌──────────────────────────┐    ┌───────────────────────────┐   │
│  │   .claude/scripts/       │    │   .claude/data/           │   │
│  │   query-sessions.py      │    │   feedback-log.json       │   │
│  │   list-repos.py          │    │   communication-          │   │
│  │   validate-entry.py      │    │   profile.json            │   │
│  └──────────────────────────┘    └───────────────────────────┘   │
│                                                                     │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │                  .claude/data/                               │  │
│  │   sessions.json          keywords-taxonomy.json             │  │
│  └──────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Sessions-Manager Agent Invocation

### MODE 1: Retrieve (session start)

**When:** CLAUDE.md instructs the primary agent to call this at the start of every session.

**Input prompt to sessions-manager:**
```
ACTION: retrieve
CURRENT_REPO: <repo name detected from cwd git remote, or "unknown">
HINT_TICKET: <Jira ticket number if mentioned early in conversation, or null>
HINT_INITIATIVE: <initiative name if already known, or null>
```

**What the agent does:**
1. If `HINT_TICKET` is provided → call `mcp__atlassian__getJiraIssue`, traverse parent chain until `issuetype.name == "Initiative"`, resolve initiative ID and name
2. Run `python3 .claude/scripts/query-sessions.py --initiative-id <id> --repo <repo>` via Bash
3. Read `.claude/data/communication-profile.json` for active reinforcement instructions
4. Return the SESSIONS CONTEXT block (see output format below)

**Output returned to primary agent:**
```
SESSIONS CONTEXT
----------------
Initiative: [name] ([id])
Repo: [repo]

Recent sessions (last 5):
  - 2026-06-20: Discussed token expiration strategy and implemented caching layer.
    Action items: review token implementation with team, benchmark new caching approach
  - 2026-06-18: Reviewed authentication middleware and identified CORS configuration gap.
    Action items: fix CORS headers before next release

Cross-repo sessions (past week):
  - 2026-06-22 (family-search-ui): Integrated backend auth changes into frontend login flow.

Active communication guidance:
  - When asked about "schema", default to JSON data structure unless database context is explicit.
```

**If Atlassian MCP is unavailable:** use `initiative: { "name": "unknown", "id": "unknown" }`, add `"mcp_unresolved": true` flag to any stored entry.

---

### MODE 2: Store (session end)

**When:** CLAUDE.md instructs the primary agent to call this at the end of every session.

**Input prompt to sessions-manager:**
```
ACTION: store
ENTRY: {
  "timestamp": "2026-06-25T14:30:00Z",
  "initiative": { "name": "Platform Modernization", "id": "INIT-42" },
  "repo": "family-search-platform",
  "jira_tickets": ["FS-1234", "FS-5678"],
  "themes": ["authentication", "performance optimization"],
  "key_subjects": ["session token management", "database indexing"],
  "tags": ["backend", "security"],
  "summary": "Discussed token expiration strategy and implemented caching layer.",
  "action_items": ["review token implementation with team", "benchmark new caching approach"]
}
```

**What the agent does:**
1. Run `python3 .claude/scripts/validate-entry.py --entry-json '<json>'`
2. If valid: Read `sessions.json`, append entry, Write back
3. Increment frequency counters in `keywords-taxonomy.json` for matching tags and themes
4. Confirm initiative resolution via Atlassian MCP if `mcp_unresolved` not already true

**Output returned to primary agent:**
```json
{ "stored": true, "entry_index": 47 }
```
or on failure:
```json
{ "stored": false, "errors": ["missing required field: summary"] }
```

---

### MODE 3: Get Keywords (during session, for tagging)

**When:** Primary agent needs to select tags for a session entry and wants to use consistent vocabulary.

**Input:**
```
ACTION: get-keywords
CATEGORY: backend
```

**Output:**
```json
{
  "category": "backend",
  "keywords": ["API", "authentication", "middleware", "service", "REST", "endpoint", "Java", "Spring", "authorization", "microservice"]
}
```
Keywords sorted by frequency descending so most-used terms surface first.

---

## Feedback-Learning Agent Invocation

**When:** Primary agent detects a correction or clarification from the engineer.

**Detection signals the primary agent watches for:**
- "That's wrong", "Actually...", "No, I meant...", "You misunderstood..."
- Engineer rephrases the same request a second time
- Engineer explicitly corrects a factual or domain interpretation

**Input prompt to feedback-learning:**
```
CONTEXT_SLICE: [~500 tokens of conversation around the miscommunication — include several turns before and after]
ORIGINAL_RESPONSE: [exact text of what the primary agent said that was wrong]
CORRECTION: [exact text of the engineer's correction]
```

**What the agent does:**
1. Classify miscommunication type: `domain_misunderstanding`, `instruction_ambiguity`, or `context_gap`
2. Check `feedback-log.json` for prior entries with same type + tags
3. Build and append entry; set `is_recurring: true` if 2+ prior matches
4. If total occurrences of this type ≥ 3: upsert pattern in `communication-profile.json`
5. Recalculate health ratio

**Output returned to primary agent:**
```json
{ "logged": true, "pattern_flagged": false, "pattern_type": "instruction_ambiguity" }
```
or when a pattern threshold is crossed:
```json
{ "logged": true, "pattern_flagged": true, "pattern_type": "domain_misunderstanding" }
```

---

## Session Lifecycle Summary

```
SESSION START
    │
    ├─ CLAUDE.md activates automatically
    │
    ▼
sessions-manager retrieve
    │
    ├─ Resolves initiative via Atlassian MCP (if ticket known)
    ├─ Calls query-sessions.py
    ├─ Reads communication-profile.json
    └─ Returns SESSIONS CONTEXT block to primary agent
    │
    ▼
CONVERSATION IN PROGRESS
    │
    ├─ Jira ticket mentioned → note for session entry
    ├─ Correction detected → invoke feedback-learning agent
    └─ Vocabulary needed → invoke sessions-manager get-keywords
    │
    ▼
SESSION END
    │
    ▼
sessions-manager store
    │
    ├─ Calls validate-entry.py
    ├─ Appends to sessions.json
    └─ Updates keyword frequencies in keywords-taxonomy.json
```

---

## File Reference

| File | Role |
|---|---|
| `.claude/agents/sessions-manager.md` | Agent definition + system prompt |
| `.claude/agents/feedback-learning.md` | Agent definition + system prompt |
| `.claude/scripts/query-sessions.py` | Filters sessions.json by initiative+repo |
| `.claude/scripts/list-repos.py` | Lists repos by initiative |
| `.claude/scripts/validate-entry.py` | Validates session entry schema |
| `.claude/data/sessions.json` | Append-only session history |
| `.claude/data/feedback-log.json` | Miscommunication log |
| `.claude/data/communication-profile.json` | Analyzed patterns + health ratio |
| `.claude/data/keywords-taxonomy.json` | Categorized vocabulary with frequency |
| `CLAUDE.md` | Activates system in every session; instructs primary agent on lifecycle |
