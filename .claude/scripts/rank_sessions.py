#!/usr/bin/env python3
"""
rank_sessions.py — relevance engine for past-session knowledge retrieval.

Given a query (the user's prompt), ranks stored sessions by content relevance
using TF-IDF cosine similarity plus multiplicative structured boosts, then
gates on a similarity threshold and a top-K cap.

This is a pure-stdlib, deterministic ranker — no LLM, no external deps. It
demonstrates the project principle "scripts for reliability and speed, LLMs
for judgment": ranking is deterministic work, so it belongs in a script.

Modes:
  --query "<text>"      rank sessions against this query, print JSON
  (stdin)               if no --query, read the query from stdin JSON {"query": ...}
  --emit-tokens "<text>"  print the normalized token blob for <text> and exit
                          (used by the store path to precompute entry._tokens)

Output (rank mode):
  {
    "matches": [
      {"timestamp","repo","initiative","summary","score","base_sim",
       "decisions","action_items"}
    ],
    "total_searched": N
  }
"""

import argparse
import json
import math
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

DATA_DIR = Path(__file__).parent.parent / "data"
SESSIONS_FILE = DATA_DIR / "sessions.json"
TAXONOMY_FILE = DATA_DIR / "keywords-taxonomy.json"

# Tuning parameters (see plan / eval_ranking.py for calibration)
SIM_THRESHOLD = 0.12      # gate on base_sim (pre-boost)
TOP_K = 2
INIT_BOOST = 1.5
REPO_BOOST = 1.25
RECENCY_HALFLIFE_DAYS = 30.0

MIN_TOKEN_LEN = 3

# Small English stopword set + a tiny domain stoplist. The domain words appear
# in nearly every session here, so they carry no discriminating signal.
STOPWORDS = {
    "a", "an", "the", "and", "or", "but", "if", "then", "else", "when",
    "at", "by", "for", "with", "about", "against", "between", "into",
    "through", "during", "before", "after", "above", "below", "to", "from",
    "up", "down", "in", "out", "on", "off", "over", "under", "again",
    "further", "is", "are", "was", "were", "be", "been", "being", "have",
    "has", "had", "do", "does", "did", "doing", "would", "should", "could",
    "can", "will", "just", "of", "as", "this", "that", "these", "those",
    "i", "we", "you", "it", "they", "he", "she", "my", "our", "your",
    "how", "what", "why", "where", "who", "which", "whom", "use", "using",
    "used", "need", "want", "get", "got", "make", "made", "let", "us",
    # domain stoplist — too common in this corpus to discriminate
    "session", "sessions", "claude",
}


def load_taxonomy() -> dict:
    if TAXONOMY_FILE.exists():
        try:
            return json.loads(TAXONOMY_FILE.read_text())
        except Exception:
            pass
    return {}


def taxonomy_terms(taxonomy: dict) -> list[str]:
    """All terms across all categories, lowercased."""
    terms = []
    for category in taxonomy.values():
        if isinstance(category, list):
            for item in category:
                if isinstance(item, dict) and "term" in item:
                    terms.append(item["term"].lower())
    return terms


def tokenize(text: str, taxonomy_term_list: list[str]) -> list[str]:
    """
    Deterministic tokenizer shared by index-time and query-time so the two
    can never drift. Steps:
      1. lowercase
      2. fold multi-word taxonomy phrases into single underscored tokens
         (must happen before splitting so "state management" survives intact)
      3. split on non-alphanumeric (keep underscores from step 2)
      4. drop stopwords
      5. min length 3, BUT whitelist any token matching a taxonomy term
         (so API, SSO, AWS, i18n, CSS, ci/cd survive)
    """
    if not text:
        return []

    text = text.lower()

    # Build a normalized lookup of taxonomy terms.
    # Multi-word phrases -> underscored; single words kept for the whitelist.
    single_word_terms = set()
    multiword = []
    for term in taxonomy_term_list:
        normalized = re.sub(r"[^a-z0-9]+", "_", term).strip("_")
        if " " in term or "/" in term or "-" in term:
            multiword.append((term, normalized))
        else:
            single_word_terms.add(normalized)
        # also allow the normalized single-word form to be whitelisted
        single_word_terms.add(normalized)

    # Fold multi-word phrases first (longest first to avoid partial overlaps)
    for term, normalized in sorted(multiword, key=lambda x: -len(x[0])):
        pattern = re.escape(term).replace(r"\ ", r"[\s/_-]+")
        text = re.sub(pattern, f" {normalized} ", text)

    # Split on anything that isn't alphanumeric or underscore
    raw_tokens = re.split(r"[^a-z0-9_]+", text)

    tokens = []
    for tok in raw_tokens:
        if not tok or tok == "_":
            continue
        if tok in STOPWORDS:
            continue
        # whitelist taxonomy matches regardless of length
        if tok in single_word_terms:
            tokens.append(tok)
            continue
        if len(tok) >= MIN_TOKEN_LEN:
            tokens.append(tok)
    return tokens


def entry_document(entry: dict, taxonomy_term_list: list[str]) -> list[str]:
    """
    Return the token list for a session entry. Prefer the precomputed _tokens
    blob; fall back to tokenizing visible fields on the fly (no migration
    needed for old entries).
    """
    precomputed = entry.get("_tokens")
    if isinstance(precomputed, str) and precomputed.strip():
        return precomputed.split()

    parts = []
    parts.extend(entry.get("themes", []) or [])
    parts.extend(entry.get("key_subjects", []) or [])
    parts.extend(entry.get("tags", []) or [])
    parts.extend(entry.get("decisions", []) or [])
    parts.extend(entry.get("files_touched", []) or [])
    parts.append(entry.get("summary", "") or "")
    parts.extend(entry.get("action_items", []) or [])
    return tokenize(" ".join(parts), taxonomy_term_list)


def build_idf(documents: list[list[str]]) -> dict:
    """Smoothed IDF over the corpus. Always > 0."""
    n = len(documents)
    df = {}
    for doc in documents:
        for term in set(doc):
            df[term] = df.get(term, 0) + 1
    idf = {}
    for term, d in df.items():
        idf[term] = math.log((n + 1) / (d + 1)) + 1.0
    return idf


def tfidf_vector(tokens: list[str], idf: dict) -> dict:
    """TF-IDF weights for a token list. Unknown query terms get idf=1 default
    so a query term absent from the corpus contributes nothing to any entry."""
    tf = {}
    for t in tokens:
        tf[t] = tf.get(t, 0) + 1
    return {t: count * idf.get(t, 1.0) for t, count in tf.items()}


def cosine(vec_a: dict, vec_b: dict) -> float:
    if not vec_a or not vec_b:
        return 0.0
    # iterate the smaller vector
    if len(vec_a) > len(vec_b):
        vec_a, vec_b = vec_b, vec_a
    dot = sum(w * vec_b.get(t, 0.0) for t, w in vec_a.items())
    if dot <= 0.0:
        return 0.0
    norm_a = math.sqrt(sum(w * w for w in vec_a.values()))
    norm_b = math.sqrt(sum(w * w for w in vec_b.values()))
    if norm_a <= 0.0 or norm_b <= 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


def recency_factor(timestamp: str) -> float:
    try:
        dt = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        age_days = (datetime.now(timezone.utc) - dt).total_seconds() / 86400.0
        if age_days < 0:
            age_days = 0.0
        return 0.5 + 0.5 * math.exp(-age_days / RECENCY_HALFLIFE_DAYS)
    except Exception:
        return 0.5


def rank(query: str, current_repo: str, initiative_id: str,
         top_k: int, threshold: float) -> dict:
    sessions = []
    if SESSIONS_FILE.exists():
        try:
            sessions = json.loads(SESSIONS_FILE.read_text())
        except Exception:
            sessions = []

    if not sessions:
        return {"matches": [], "total_searched": 0}

    taxonomy = load_taxonomy()
    term_list = taxonomy_terms(taxonomy)

    # Build corpus documents and IDF
    documents = [entry_document(e, term_list) for e in sessions]
    idf = build_idf(documents)

    query_tokens = tokenize(query, term_list)
    if not query_tokens:
        return {"matches": [], "total_searched": len(sessions)}
    query_vec = tfidf_vector(query_tokens, idf)

    scored = []
    for entry, doc in zip(sessions, documents):
        if not doc:
            continue
        entry_vec = tfidf_vector(doc, idf)
        base_sim = cosine(query_vec, entry_vec)
        if base_sim < threshold:
            continue

        score = base_sim
        init = entry.get("initiative", {})
        if init.get("id") and init.get("id") != "unknown" and init.get("id") == initiative_id:
            score *= INIT_BOOST
        if current_repo and entry.get("repo") == current_repo:
            score *= REPO_BOOST
        score *= recency_factor(entry.get("timestamp", ""))

        scored.append({
            "timestamp": entry.get("timestamp", ""),
            "repo": entry.get("repo", ""),
            "initiative": init.get("name", "unknown"),
            "summary": entry.get("summary", ""),
            "decisions": entry.get("decisions", []) or [],
            "action_items": entry.get("action_items", []) or [],
            "score": round(score, 4),
            "base_sim": round(base_sim, 4),
        })

    scored.sort(key=lambda m: m["score"], reverse=True)
    return {"matches": scored[:top_k], "total_searched": len(sessions)}


def main():
    parser = argparse.ArgumentParser(description="Rank sessions by relevance to a query")
    parser.add_argument("--query", default=None, help="Query text (else read stdin JSON {'query':...})")
    parser.add_argument("--current-repo", default="", help="Current repo for the repo boost")
    parser.add_argument("--initiative-id", default="", help="Current initiative id for the init boost")
    parser.add_argument("--top-k", type=int, default=TOP_K, help="Max matches to return")
    parser.add_argument("--threshold", type=float, default=SIM_THRESHOLD, help="Min base_sim to qualify")
    parser.add_argument("--emit-tokens", default=None, help="Print normalized token blob for this text and exit")
    args = parser.parse_args()

    # --emit-tokens: used by the store path to precompute entry._tokens
    if args.emit_tokens is not None:
        term_list = taxonomy_terms(load_taxonomy())
        print(" ".join(tokenize(args.emit_tokens, term_list)))
        return

    query = args.query
    if query is None:
        try:
            payload = json.loads(sys.stdin.read() or "{}")
            query = payload.get("query", "")
        except json.JSONDecodeError:
            query = ""

    result = rank(query or "", args.current_repo, args.initiative_id,
                  args.top_k, args.threshold)
    print(json.dumps(result))


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(json.dumps({"matches": [], "total_searched": 0, "error": str(e)}))
        sys.exit(0)
