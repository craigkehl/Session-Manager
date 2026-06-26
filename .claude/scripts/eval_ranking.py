#!/usr/bin/env python3
"""
eval_ranking.py — dev-only evaluation harness for rank_sessions.py.

NOT wired to any hook. Run manually to measure retrieval quality and to
calibrate SIM_THRESHOLD on the current corpus, without a labeled dataset.

Method:
  1. Synthetic queries: for each stored entry, build a query by stitching
     together 2-3 of its OWN key_subjects/themes. The "correct" answer is
     that entry. Leave-one-out: rank the whole corpus, check if the source
     entry is #1 (precision@1) or in the top 2 (precision@2).
  2. Control queries: hardcoded off-topic prompts that MUST return zero
     matches at the production threshold. This is what tunes the threshold
     against false positives — the failure mode that bloats context.
  3. Threshold sweep: report, for several candidate thresholds, the
     precision@1 and the number of control-query injections (want 0).

Usage:
  python3 .claude/scripts/eval_ranking.py
"""

import json

import rank_sessions as rs

CONTROL_QUERIES = [
    "explain monads in haskell",
    "what is the weather today",
    "best pizza toppings for a party",
    "how do tides work on the moon",
    "translate hello into french",
]

SWEEP = [0.08, 0.10, 0.12, 0.15, 0.20]


def load_sessions() -> list[dict]:
    if rs.SESSIONS_FILE.exists():
        try:
            return json.loads(rs.SESSIONS_FILE.read_text())
        except Exception:
            return []
    return []


def synthetic_query(entry: dict) -> str:
    """Build a natural-ish query from an entry's own subjects/themes."""
    subjects = (entry.get("key_subjects", []) or [])[:2]
    themes = (entry.get("themes", []) or [])[:1]
    parts = subjects + themes
    if not parts:
        parts = [entry.get("summary", "")[:60]]
    return "how did we handle " + " and ".join(parts)


def rank_at(query: str, threshold: float, top_k: int = 5) -> list[dict]:
    # No repo/initiative boost during eval so we measure pure content relevance
    return rs.rank(query, current_repo="", initiative_id="",
                   top_k=top_k, threshold=threshold)["matches"]


def evaluate(threshold: float, sessions: list[dict]) -> dict:
    p1_hits = 0
    p2_hits = 0
    total = 0
    for entry in sessions:
        ts = entry.get("timestamp", "")
        if not ts:
            continue
        total += 1
        query = synthetic_query(entry)
        matches = rank_at(query, threshold, top_k=2)
        match_ts = [m["timestamp"] for m in matches]
        if match_ts and match_ts[0] == ts:
            p1_hits += 1
        if ts in match_ts:
            p2_hits += 1

    control_injections = 0
    for cq in CONTROL_QUERIES:
        if rank_at(cq, threshold, top_k=2):
            control_injections += 1

    return {
        "threshold": threshold,
        "p1": p1_hits / total if total else 0.0,
        "p2": p2_hits / total if total else 0.0,
        "total_queries": total,
        "control_injections": control_injections,
    }


def main():
    sessions = load_sessions()
    if not sessions:
        print("No sessions to evaluate.")
        return

    print(f"Corpus: {len(sessions)} sessions\n")
    print(f"{'thresh':>7} | {'P@1':>5} | {'P@2':>5} | {'controls fired':>14}")
    print("-" * 44)

    best = None
    for threshold in SWEEP:
        r = evaluate(threshold, sessions)
        flag = "  <-- 0 controls" if r["control_injections"] == 0 else ""
        print(f"{r['threshold']:>7.2f} | {r['p1']:>5.0%} | {r['p2']:>5.0%} | "
              f"{r['control_injections']:>14}{flag}")
        # Best = highest P@1 among thresholds with zero control injections
        if r["control_injections"] == 0:
            if best is None or r["p1"] > best["p1"]:
                best = r

    print()
    if best:
        print(f"Recommended SIM_THRESHOLD = {best['threshold']:.2f} "
              f"(P@1={best['p1']:.0%}, P@2={best['p2']:.0%}, zero false positives)")
        print(f"Current production value  = {rs.SIM_THRESHOLD:.2f}")
    else:
        print("No threshold achieved zero control injections — corpus may be too small "
              "or control queries overlap stored vocabulary.")


if __name__ == "__main__":
    main()
