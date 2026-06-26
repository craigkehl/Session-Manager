# Live Demo Guide — Sessions Management System

5-minute walkthrough for a software development team. Run these commands in sequence from the project directory.

**Setup**: Open a terminal, `cd` to this project directory before starting.

---

## ACT 1 — The Problem (30 seconds, no commands)

> "Every Claude Code session starts from scratch. You mention a Jira ticket, re-explain the initiative, repeat context you already gave last week. This system fixes that automatically."

---

## ACT 2 — Show the Schema Enforcement (1 minute)

**Bad entry — catches errors:**
```bash
python3 .claude/scripts/validate-entry.py --entry-json '{"timestamp":"yesterday","initiative":{"name":"","id":""},"summary":"","jira_tickets":[],"themes":[],"key_subjects":[],"tags":[],"action_items":[]}'
```
Expected output:
```json
{"valid": false, "errors": ["timestamp is not valid ISO 8601: 'yesterday'", "initiative.name must be a non-empty string", "missing required field: summary"], "warnings": []}
```

> "It enforces the schema. Bad data doesn't get in."

**Good entry — passes:**
```bash
python3 .claude/scripts/validate-entry.py --entry-json '{"timestamp":"2026-06-25T16:00:00Z","initiative":{"name":"AI Developer Productivity","id":"unknown"},"repo":"AI/Session-Manager","jira_tickets":[],"themes":["agentic workflows"],"key_subjects":["sessions JSON schema"],"tags":["backend"],"summary":"Designed the sessions management system architecture.","action_items":["present to team"]}'
```
Expected output:
```json
{"valid": true, "errors": [], "warnings": []}
```

---

## ACT 3 — Retrieve Past Sessions (2 minutes)

**What repos have we worked in for this initiative?**
```bash
python3 .claude/scripts/list-repos.py --initiative-id unknown
```
Expected output:
```json
{"initiative_id": "unknown", "repos": ["AI/Session-Manager", "help-chatbot", "zion"]}
```

> "Three repos already tracked under this initiative."

**What happened in this repo?**
```bash
python3 .claude/scripts/query-sessions.py --initiative-id unknown --repo AI/Session-Manager
```
Expected output:
```json
{
  "primary": [
    {
      "timestamp": "2026-06-25T16:00:00Z",
      "repo": "AI/Session-Manager",
      "jira_tickets": [],
      "themes": ["agentic workflows", "session continuity", "feedback learning", "knowledge management"],
      "key_subjects": ["sessions JSON schema", "Atlassian MCP initiative traversal", "keyword taxonomy", "feedback learning agent", "Python helper scripts", "context efficiency rules"],
      "summary": "Designed and implemented a multi-agent session management system for tracking AI conversation context across Claude Code sessions.",
      "action_items": ["present system to team", "share repo with team members", "resolve Jira initiative ID for AI Developer Productivity"]
    },
    {
      "timestamp": "2026-06-18T10:15:00Z",
      "repo": "AI/Session-Manager",
      ...
      "summary": "Explored persistent AI session memory for FamilySearch engineers, identifying JSON and markdown as primary storage mechanisms."
    }
  ],
  "cross_repo": [
    {
      "timestamp": "2026-06-24T09:45:00Z",
      "repo": "help-chatbot",
      "summary": "Explored integrating session context retrieval into help-chatbot to personalize responses based on user's recent research patterns."
    },
    {
      "timestamp": "2026-06-21T14:30:00Z",
      "repo": "zion",
      "summary": "Reviewed how AI workflow tooling could surface relevant Zion component decisions from past sessions during component selection."
    }
  ],
  "total_searched": 4
}
```

> "Two sessions from this repo, plus cross-repo work from help-chatbot and zion in the past week — all from the same initiative. This is what Claude sees when a new session starts."

---

## ACT 4 — The Money Shot (1.5 minutes)

> "Now watch what happens when I open a fresh Claude Code session in this project."

1. Open a **new** Claude Code session in this directory (or show the SESSIONS CONTEXT block below)
2. Claude will automatically invoke the sessions-manager agent and return:

```
SESSIONS CONTEXT
----------------
Initiative: AI Developer Productivity (unknown)
Repo: AI/Session-Manager

Recent sessions (last 5):
  - 2026-06-25: Designed and implemented a multi-agent session management system for tracking AI conversation context across Claude Code sessions.
    Action items: present system to team, share repo with team members, resolve Jira initiative ID for AI Developer Productivity
  - 2026-06-18: Explored persistent AI session memory for FamilySearch engineers, identifying JSON and markdown as primary storage mechanisms.
    Action items: decide on storage format, prototype sessions JSON schema

Cross-repo sessions (past week):
  - 2026-06-24 (help-chatbot): Explored integrating session context retrieval into help-chatbot to personalize responses based on user's recent research patterns.
  - 2026-06-21 (zion): Reviewed how AI workflow tooling could surface relevant Zion component decisions from past sessions during component selection.
```

> "Claude now opens every session knowing what you worked on, what decisions were made, and what's pending — without you typing a word."

---

## ACT 5 — Team Sharing (30 seconds, no commands)

> "Everything that runs the system — the agents, scripts, keyword vocabulary — is committed to git. You clone the repo, open Claude Code, and it works. Your session history stays on your own machine. When we're ready, we replace the local file with a shared store and everyone sees each other's work."

---

## Key Points to Land

- **Zero manual effort** — sessions are captured and retrieved automatically
- **Initiative-scoped** — context matches your actual work, not just recency
- **Cross-repo aware** — see what the frontend team did on the same initiative this week
- **Extensible** — feedback agent learns your communication patterns over time
- **Shareable** — git the scaffolding, keep data local until ready to share

---

## If Questions Come Up

**"What if Jira isn't connected?"**
→ System falls back gracefully, stores `mcp_unresolved: true`, still tracks everything locally.

**"Does it read the whole JSON every session?"**
→ No. It queries by initiative+repo and returns summaries only — 5 entries max plus recent cross-repo work.

**"How do team members get started?"**
→ Clone the repo, open Claude Code in the project directory. That's it. Their personal data files are created automatically on first use.

**"What's the feedback agent?"**
→ A separate agent that watches for corrections ("that's wrong", "I meant X") and builds a profile of how you communicate — so Claude gets better at understanding you specifically over time.
