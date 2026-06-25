# Section 5: Feedback Learning Agent — Flow Diagram

Required by `3-feedback_learning_agent` before implementation. This document visualizes how feedback enters the system, how it is analyzed, how patterns are identified, and how insights loop back to improve the primary agent's behavior.

---

## Flow Diagram

```
┌─────────────────────────────────────────────────────────────────────┐
│                        PRIMARY AGENT CONVERSATION                    │
│                                                                     │
│  Engineer: "Actually, that's wrong — I meant X not Y."             │
│                                 │                                   │
│                                 ▼                                   │
│              ┌──────────────────────────────┐                       │
│              │    TRIGGER DETECTION         │                       │
│              │                              │                       │
│              │  Signals:                    │                       │
│              │  • Explicit correction       │                       │
│              │    ("that's wrong", "no,")   │                       │
│              │  • Clarification request     │                       │
│              │    ("what I meant was...")   │                       │
│              │  • Repeated rephrasing       │                       │
│              │                              │                       │
│              │  Primary agent invokes       │                       │
│              │  feedback-learning agent     │                       │
│              │  with 3 inputs:              │                       │
│              │  - CONTEXT_SLICE             │                       │
│              │  - ORIGINAL_RESPONSE         │                       │
│              │  - CORRECTION                │                       │
│              └──────────────┬───────────────┘                       │
└─────────────────────────────┼───────────────────────────────────────┘
                              │
                              ▼
              ┌──────────────────────────────┐
              │    FEEDBACK-LEARNING AGENT   │
              │                              │
              │  ┌────────────────────────┐  │
              │  │  1. CAPTURE            │  │
              │  │                        │  │
              │  │  Classify type:        │  │
              │  │  • domain_misunder-    │  │
              │  │    standing            │  │
              │  │  • instruction_        │  │
              │  │    ambiguity           │  │
              │  │  • context_gap         │  │
              │  │                        │  │
              │  │  Build entry:          │  │
              │  │  timestamp, type,      │  │
              │  │  original_response,    │  │
              │  │  correct_interpretation│  │
              │  │  confidence (0–1),     │  │
              │  │  tags, is_recurring    │  │
              │  └──────────┬─────────────┘  │
              │             │                │
              │             ▼                │
              │  ┌────────────────────────┐  │
              │  │  2. DEDUP CHECK        │  │
              │  │                        │  │
              │  │  Read feedback-log.json│  │
              │  │  Match on type + tags  │  │
              │  │  If 2+ prior matches:  │  │
              │  │    is_recurring = true │  │
              │  └──────────┬─────────────┘  │
              │             │                │
              │             ▼                │
              │  ┌────────────────────────┐  │
              │  │  3. APPEND             │  │
              │  │                        │  │
              │  │  Write new entry to    │  │
              │  │  .claude/data/         │  │
              │  │  feedback-log.json     │  │
              │  │                        │  │
              │  │  Increment             │  │
              │  │  health.signals_       │  │
              │  │  detected counter      │  │
              │  └──────────┬─────────────┘  │
              │             │                │
              │             ▼                │
              │  ┌────────────────────────┐  │
              │  │  4. PATTERN ANALYSIS   │  │
              │  │                        │  │
              │  │  Count entries by type │  │
              │  │                        │  │
              │  │  Threshold: 3+         │  │
              │  │  occurrences of same   │  │
              │  │  type = flagged pattern│  │
              │  │                        │  │
              │  │  If threshold reached: │  │
              │  │    → upsert pattern in │  │
              │  │    communication-      │  │
              │  │    profile.json        │  │
              │  │    → increment         │  │
              │  │    patterns_documented │  │
              │  └──────────┬─────────────┘  │
              │             │                │
              │             ▼                │
              │  ┌────────────────────────┐  │
              │  │  5. HEALTH RATIO       │  │
              │  │                        │  │
              │  │  ratio =               │  │
              │  │  patterns_documented / │  │
              │  │  signals_detected      │  │
              │  │                        │  │
              │  │  Update health block   │  │
              │  │  in communication-     │  │
              │  │  profile.json          │  │
              │  └──────────┬─────────────┘  │
              └─────────────┼────────────────┘
                            │
                            ▼
              ┌──────────────────────────────┐
              │  communication-profile.json  │
              │                              │
              │  {                           │
              │    "last_updated": "...",    │
              │    "health": {               │
              │      "signals_detected": N,  │
              │      "patterns_documented":M,│
              │      "ratio": M/N            │
              │    },                        │
              │    "patterns": [             │
              │      {                       │
              │        "type": "...",        │
              │        "occurrences": 3+,    │
              │        "reinforcement_       │
              │         instruction": "..."  │
              │      }                       │
              │    ]                         │
              │  }                           │
              └──────────────┬───────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    PROFILE INJECTION (LOOP-BACK)                     │
│                                                                     │
│  When sessions-manager agent returns context at session start:      │
│                                                                     │
│  1. Reads communication-profile.json                                │
│  2. Appends active reinforcement instructions to SESSIONS CONTEXT   │
│     block under "Active communication guidance:"                    │
│  3. Primary agent receives this guidance alongside session history  │
│  4. Guidance shapes how primary agent interprets the engineer's     │
│     requests for the duration of that session                       │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Signal-to-Action Ratio

The health ratio measures how effectively detected miscommunications are converted into documented, actionable patterns.

| Metric | Definition |
|---|---|
| `signals_detected` | Total corrections/clarifications captured in `feedback-log.json` |
| `patterns_documented` | Total distinct patterns flagged (3+ occurrences) in `communication-profile.json` |
| `ratio` | `patterns_documented / signals_detected` |

**Interpreting the ratio:**
- Ratio near 0: Many signals but no patterns crystallizing — miscommunications are one-offs or the threshold hasn't been reached yet. Normal early in use.
- Ratio 0.1–0.3: Healthy steady-state — signals accumulating, patterns emerging from recurring issues.
- Ratio > 0.5: Either very few signals (system barely used) or threshold is too low.

---

## Miscommunication Types

| Type | Definition | Example |
|---|---|---|
| `domain_misunderstanding` | Agent misread FamilySearch/project-specific terminology | Confused "initiative" (Jira parent) with a generic "goal" |
| `instruction_ambiguity` | Engineer's instruction had multiple valid interpretations; agent chose wrong one | "Update the schema" meant the JSON schema doc, not the database schema |
| `context_gap` | Agent lacked relevant prior context to respond correctly | Didn't know the engineer always prefers TypeScript over JavaScript |

---

## Files Involved

| File | Role |
|---|---|
| `.claude/data/feedback-log.json` | Append-only log of all detected miscommunications |
| `.claude/data/communication-profile.json` | Analyzed patterns + health ratio; read at every session start |
| `.claude/agents/feedback-learning.md` | Agent definition that executes this flow |
| `3-feedback_learning_agent` | Original spec/system prompt |
