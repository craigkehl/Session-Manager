# Sessions Management System

This project maintains AI session context across conversations using structured JSON storage, two specialized sub-agents, and Atlassian MCP integration. Every Claude Code session opened in this directory automatically participates in session tracking.

---

## Session Lifecycle

### At Every Session Start

Invoke the sessions-manager agent in retrieve mode:

```
ACTION: retrieve
CURRENT_REPO: <detect from `git remote get-url origin` if possible, otherwise "unknown">
HINT_TICKET: <first Jira ticket mentioned in this session, or null>
HINT_INITIATIVE: <initiative name if already known, or null>
```

Use the returned **SESSIONS CONTEXT** block to inform conversation. Reference past sessions specifically — say "In your June 20th session on the Platform Modernization initiative..." not vague references.

If a Jira ticket is mentioned early, re-invoke with `HINT_TICKET` set so the sessions-manager can resolve the initiative via Atlassian MCP.

### During the Session

- **Jira ticket mentioned** → note it; update the session entry you'll store at the end
- **Correction or clarification detected** → invoke the feedback-learning agent immediately:
  ```
  CONTEXT_SLICE: <~500 tokens around the miscommunication>
  ORIGINAL_RESPONSE: <what you said that was wrong>
  CORRECTION: <what the engineer said to correct it>
  ```
- **Need vocabulary for tagging** → invoke sessions-manager with:
  ```
  ACTION: get-keywords
  CATEGORY: <backend | frontend | security | database | devops | infrastructure | all>
  ```

### At Every Session End

Invoke the sessions-manager agent in store mode. Construct the entry first:

**What counts as a theme:** high-level topic areas discussed (e.g., "authentication", "performance optimization") — not specific functions or filenames.

**What counts as a key subject:** specific concepts, components, or technical items named (e.g., "session token management", "DynamoDB GSI design").

**How to write the summary:** one sentence, ≤ 200 characters, past tense, describing the main outcome (e.g., "Discussed token expiration strategy and agreed on 24-hour sliding window approach.").

**Tags:** use existing keywords from the taxonomy. Get suggestions with `ACTION: get-keywords` if needed.

```
ACTION: store
ENTRY: {
  "timestamp": "<ISO 8601 now>",
  "initiative": { "name": "<resolved name>", "id": "<resolved id>" },
  "repo": "<repo name>",
  "jira_tickets": ["FS-XXXX"],
  "themes": ["theme1", "theme2"],
  "key_subjects": ["subject1", "subject2"],
  "tags": ["backend", "security"],
  "summary": "One sentence summary of the session outcome.",
  "action_items": ["item1", "item2"]
}
```

If Atlassian MCP was unavailable during the session, add `"mcp_unresolved": true` to the entry.

---

## Detection Signals for Feedback-Learning Invocation

Invoke the feedback-learning agent when you observe any of these:
- Engineer says "that's wrong", "no", "actually", "I meant", "you misunderstood"
- Engineer rephrases the same request a second time
- Engineer explicitly corrects a domain term or concept interpretation

Do NOT invoke for clarifying questions the engineer asks you, or for routine back-and-forth.

---

## File Structure

```
/Users/craigkehl/dev/FamilySearch/AI/Session Manager/
├── CLAUDE.md                         ← this file (activates system each session)
├── .gitignore                        ← protects local data files
│
├── 1-sessions_sys.md                 ← core system spec + primary agent prompt
├── 2-sessions_manager_agent          ← sessions manager agent original spec
├── 3-feedback_learning_agent         ← feedback learning agent original spec
├── 4-presentation_materials          ← PowerPoint outline
├── 5-feedback_flow_diagram.md        ← flow diagram (required before implementation)
├── 6-integration_design.md           ← agent communication design + data flow
│
└── .claude/
    ├── settings.json                 ← project permissions (committed)
    ├── settings.local.json           ← local overrides (gitignored)
    │
    ├── agents/
    │   ├── sessions-manager.md       ← agent: retrieves and stores session context
    │   └── feedback-learning.md      ← agent: learns from miscommunications
    │
    ├── scripts/
    │   ├── query-sessions.py         ← filters sessions.json by initiative+repo
    │   ├── list-repos.py             ← lists repos by initiative
    │   └── validate-entry.py         ← validates session entry schema
    │
    └── data/                         ← gitignored (local to each engineer's machine)
        ├── sessions.json             ← append-only session history
        ├── feedback-log.json         ← miscommunication log
        ├── communication-profile.json ← learned patterns + health ratio
        └── keywords-taxonomy.json    ← categorized vocabulary with frequency counts
```

---

## Permissions Required

The following are pre-approved in `.claude/settings.json`:
- `Bash(python3 .claude/scripts/*.py)` — run local data scripts
- `mcp__atlassian__getJiraIssue` — resolve ticket → initiative chain
- `mcp__atlassian__search` — search Atlassian for initiative details
- `mcp__atlassian__searchJiraIssuesUsingJql` — query Jira issues by JQL

---

## Sharing This System with Team Members

The committed files (spec docs, agent definitions, scripts, taxonomy, `CLAUDE.md`) can be shared via git. Each team member gets their own local data files (gitignored) — their `sessions.json`, `feedback-log.json`, and `communication-profile.json` are personal to their machine. The keyword taxonomy starts seeded and evolves independently per engineer.

For team-wide session sharing, a future phase would replace the local `sessions.json` with a shared store (e.g., a team S3 bucket or shared git-tracked file).
