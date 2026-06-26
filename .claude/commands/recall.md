---
description: Search past session history for context relevant to a topic
argument-hint: <topic or question>
---

The user wants to recall past session context about: **$ARGUMENTS**

Run the relevance engine on demand. Because the user explicitly asked, use a
wider net than the automatic just-in-time retrieval: more results, no gate.

```bash
python3 .claude/scripts/rank_sessions.py --query "$ARGUMENTS" --top-k 5 --threshold 0.0
```

Parse the JSON output (`matches` array, each with `timestamp`, `repo`,
`initiative`, `summary`, `decisions`, `action_items`, `score`, `base_sim`).

Then present the results to the user as a readable list, most relevant first.
Unlike the automatic injection (which shows summary only to protect context),
here show the **full** view for each match:

- **Date / initiative / repo** header
- The one-sentence **summary**
- Any **decisions** (these are the durable, reusable conclusions — surface them)
- Any open **action_items**

If `matches` is empty, tell the user no past sessions were relevant to that
topic and suggest they rephrase or broaden the query. Do not invent sessions.

Keep your presentation tight — this is a lookup, not an essay.
