# Design Principles

## Origin

I mentioned to my manager a need for team specific and iterative guidance on working with AI tools. He agreed — by putting me on the agenda for a 5-minute "Evolving with AI" slot at the next team meeting.

That constraint shaped everything. Five minutes is not enough time to teach architecture. It is enough time to show someone one thing that is immediately useful to them. The team ranged from engineers who had barely opened Claude Code to engineers already writing agentic workflows — so a single presentation pitched at one level would leave half the room behind.

The solution was to build a real, working tool and let the tool itself carry multiple levels of meaning simultaneously:

- An engineer who has only used chat sees: *a system that gives Claude memory across sessions*
- An engineer exploring Claude Code sees: *how CLAUDE.md, settings.json, and agents fit together*
- An engineer ready to go deeper sees: *a live demonstration of every principle worth knowing — markdown vs JSON, right-sized agents, scripts over LLMs, hooks for enforcement, cascading settings, progressive context management, just-in-time relevance retrieval*

The system is genuinely useful. The principles are genuinely illustrated by it. The five-minute demo is genuinely completable. None of those things required a trade-off against the others.

---

## The Seven Principles

### 1. Markdown for instructions, JSON for data

**Rule:** Use `.md` files for anything a human or LLM reads as prose. Use `.json` for anything a program reads structurally.

**Where this appears:**
- Agent definitions → `.claude/agents/*.md` — prose system prompts, written to be read
- Session entries → `.claude/data/sessions.json` — typed schema, queried by scripts
- Keyword taxonomy → `.claude/data/keywords-taxonomy.json` — structured lookup table
- Hook output → `{"systemMessage": "..."}` — JSON envelope even when content is text
- Communication profile → `.claude/data/communication-profile.json` — machine-readable patterns

**Why it matters:** Markdown edited by a human stays readable. JSON consumed by a script stays reliable. Mixing them — storing structured data in markdown tables, or writing agent prompts in JSON strings — creates friction in both directions.

---

### 2. Right-size the model and protect the main context

**Rule:** Sub-agents should use the smallest model that can do the job. Give them only the tools they need. Pass structured input; get structured output. Never let a sub-agent's work pollute the main conversation context.

**Where this appears:**
- Both agents specify `model: claude-sonnet-4-6` — not Opus
- `sessions-manager` tools: `[Read, Write, Bash, mcp__atlassian__*]` — no browser, no edit
- `feedback-learning` tools: `[Read, Write]` — the minimal possible set
- All agent inputs use named ACTION fields with typed JSON payloads
- All agent outputs are JSON objects: `{ "stored": true, "entry_index": 47 }`

**Why it matters:** A sub-agent doing a focused task doesn't need reasoning power — it needs reliability. Cheaper models are faster and more predictable for structured work. JSON shapes on input and output mean the primary agent never has to parse prose, and the sub-agent's token usage never bleeds into your conversation.

---

### 3. Scripts for reliability and speed, LLMs for judgment

**Rule:** Anything deterministic — counting, filtering, sorting, validating, parsing — should be a Python script, not an LLM call. Reserve LLM calls for things that require understanding.

**Where this appears:**
- `validate-entry.py` — schema validation via regex and type checks, not "does this look right?"
- `query-sessions.py` — filtering by initiative ID and date range, pure Python
- `list-repos.py` — set comprehension over JSON, sub-millisecond
- `session-precompact.py` — structural extraction from JSONL (regex, path parsing), no LLM
- `session-checkpoint.py` — focus detection via `Counter` on directory paths, no LLM
- `rank_sessions.py` — the relevance engine: TF-IDF cosine + boosts, ranking past sessions against the user's prompt. The temptation is to ask an LLM "which past sessions are relevant?"; instead this is deterministic math that runs in under 10ms, never hallucinates a match, and can be unit-tested by `eval_ranking.py`
- LLM is used for: summarizing a session (judgment), classifying a miscommunication (understanding), writing a reinforcement instruction (language)

**Why it matters:** LLMs are slow, non-deterministic, and cost tokens. A script that validates an ISO 8601 timestamp runs in microseconds and never hallucinates "yes this looks fine." Use the right tool for the job. Scripts also make behavior auditable — you can read `validate-entry.py` and know exactly what passes.

---

### 4. Hooks for enforcement, not instructions

**Rule:** Anything that must happen every session — context injection, compaction capture, fallback storage — should be wired into a hook, not left to CLAUDE.md instructions. Instructions can be forgotten; hooks fire regardless.

**Where this appears:**
- `SessionStart` hook → `session-startup.py` emits a minimal "active" message (no eager dump)
- `UserPromptSubmit` hook → `session-context-inject.py` runs just-in-time relevance retrieval against the prompt, and reinjects recovered context after a compaction
- `PreCompact` hook → `session-precompact.py` captures the transcript before it's shed
- `Stop` hook (async) → `session-checkpoint.py` monitors focus drift after every turn
- `SessionEnd` hook → `session-fallback.py` writes a stub if the agent never stored

**The inherent asymmetry:** `SessionStart` and all mid-session hooks are fully enforced. `SessionEnd` storage of a rich summary still requires the LLM — the hook can only write a stub because it has no access to the conversation. This is a genuine limitation of the hook system, not a design gap. The fallback hook is defense in depth, not a complete fix.

**Why it matters:** A CLAUDE.md instruction saying "store the session at the end" works until it doesn't — the session ends abruptly, context fills, the LLM gets absorbed in a task. A hook fires unconditionally. Design for failure, not for ideal behavior.

---

### 5. Cascading settings at the right level

**Rule:** Place settings, permissions, and hooks at the most specific scope that satisfies the requirement. Project → directory → global. Never put something global that should be project-scoped.

**Where this appears:**
- `.claude/settings.json` (project scope) — hook definitions and MCP permissions apply only to this repo by default
- `install-hook.py --mode directory` — promotes the `SessionStart` hook to a parent directory when you want cross-repo coverage (e.g. all FamilySearch repos)
- `install-hook.py --mode global` — opt-in only, for engineers who want every session tracked
- `keywords-taxonomy.json` committed to the repo — shared starting vocabulary, not personal data
- `.claude/data/*.json` gitignored — personal session history stays on your machine

**Why it matters:** Global settings affect every project, including unrelated personal work. A hook installed at the wrong scope fires where it shouldn't, adds latency where it isn't wanted, and silently captures context the engineer didn't intend to track. Cascading means you can install at the narrowest scope that works, then widen deliberately.

---

### 6. Progressive context management

**Rule:** Long sessions lose context. Design explicitly for compaction events rather than pretending they don't happen. Surface focus drift to the user before it causes confusion.

**Where this appears:**
- `PreCompact` captures a structured epoch of what's being shed into `rolling-summary.json`
- `UserPromptSubmit` reinjects recovered epochs once, immediately after compaction
- `Stop` (async) detects when 3 of the last 4 file edits cluster under one directory subtree — but only suggests once a compaction has actually occurred (i.e. context is genuinely under pressure)
- When focus narrows + compaction has occurred, the next prompt surfaces a `/compact` suggestion with a plain-language explanation of why Claude may seem to be ignoring earlier instructions
- `rolling-summary.json`, `turn-counter.json`, `focus-suggestion.json` are all session-local and gitignored

**The branch suggestion:** when focus narrows mid-session, the right move is often `/compact "focus on <directory> only"` rather than a git branch. This prunes context to what's relevant. The suggestion the system surfaces names the cause — context pressure — rather than just saying "something seems wrong."

**Why it matters:** The most common confusion engineers have with Claude Code is "why isn't it following my instructions anymore?" The answer is almost always context pressure: the instruction is no longer in the active window. Making this visible, naming it, and giving an actionable command (not just a vague warning) addresses the root cause.

---

### 7. Just-in-time relevance retrieval, not eager loading

**Rule:** Surface stored knowledge when it's relevant to what's being asked — not all of it, up front, on the chance some of it matters. Match against the actual question; gate hard; stay silent when nothing fits.

**Where this appears:**
- `session-startup.py` used to dump the 5 most recent sessions at startup, before the user had said anything. It now emits a one-line "active" message.
- `session-context-inject.py` (UserPromptSubmit) ranks past sessions against the user's actual prompt and injects only what clears the bar — at most 2, summary only.
- `rank_sessions.py` scores by content relevance (TF-IDF) with metadata boosts, so a specific topical match beats mere recency.
- A per-session dedup set (`injected-sessions.json`) ensures the same past session is never injected twice in one conversation — so running every turn never compounds into bloat.
- `/recall <topic>` (`.claude/commands/recall.md`) is the explicit escape hatch: when the user *asks* for history, the gate widens (top-5, no threshold) and the full view — including decisions — is shown.

**Why it matters:** Eager loading spends context on recency and hopes it's relevant. Most of it isn't, and it pushes the things that *are* relevant further from the active window. Just-in-time retrieval inverts this: zero cost on turns where nothing matches, precise injection when something does. The cost of retrieval is paid only when it delivers value. This is the same instinct as lazy evaluation — do the work when the answer is actually needed, not before.

---

## Does the System Apply Its Own Principles?

**Markdown vs JSON:** Yes. Every agent prompt is prose `.md`. Every data file is typed JSON. The hook output envelopes are JSON even when the content is a human-readable string.

**Right-sized agents:** Yes. Both agents use Sonnet, not Opus. Tool lists are minimal. All inputs and outputs are JSON-shaped.

**Scripts over LLMs:** Yes. Every hook script is pure Python — no LLM calls. The relevance engine (`rank_sessions.py`) is deterministic TF-IDF, unit-tested by `eval_ranking.py`. The one place an LLM is genuinely needed (writing a session summary) is left to the agent, not attempted structurally.

**Hooks over instructions:** Yes, with one honest gap. Session-end storage of a rich summary still depends on the LLM acting on CLAUDE.md instructions. The `SessionEnd` fallback mitigates but doesn't eliminate this. It is inherent to the hook system's limitation: hooks run outside the conversation and cannot read it.

**Cascading:** Yes. Project-scope by default, with an explicit installer for directory and global promotion.

**Progressive context management:** Yes, newly added. The hook system was added after recognizing that CLAUDE.md-only guidance was insufficient for long sessions.

**Just-in-time retrieval:** Yes. Startup no longer dumps sessions; retrieval is driven by the user's prompt, gated by a relevance threshold, and deduped per session. Calibrated by `eval_ranking.py` (100% precision@1, zero false positives on the current corpus).

---

## What This Taught

Building this quickly forced prioritization. The principles above aren't abstract best practices — each one emerged from a specific failure mode:

- "Markdown vs JSON" from watching people put structured data in CLAUDE.md and then fail to parse it
- "Right-size the model" from watching Opus burn tokens doing a job Sonnet handles reliably
- "Scripts over LLMs" from a session-end storage failure where the LLM "summarized" instead of validating
- "Hooks over instructions" from the first time a session ended without storage because Claude got absorbed in a task
- "Cascading" from accidentally installing a hook globally and having it fire in every personal project
- "Progressive context management" from the exact conversation that produced this document — a session that started with a security review and ended designing turn-counting algorithms, with the original intent long gone from context
- "Just-in-time retrieval" from realizing the startup dump was spending context on recent sessions that had nothing to do with the task at hand — while the one genuinely relevant past session sat unranked in the file
