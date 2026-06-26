#!/usr/bin/env python3
"""
transcript_utils.py — single source of truth for reading Claude Code session
transcripts (the .jsonl file a hook receives via `transcript_path`).

Why this module exists: the on-disk transcript schema is NOT obvious, and
getting it wrong fails silently (you parse nothing, the feature just never
fires). Both session-precompact.py and session-checkpoint.py need to read
transcripts, so the schema lives in exactly one place here.

The schema (verified against real transcripts):
  Each line is a JSON object. The interesting ones have:
    entry["type"]               -> "user" | "assistant" | (others ignored)
    entry["message"]["role"]    -> "user" | "assistant"
    entry["message"]["content"] -> str  (a typed user prompt)
                                or list of blocks, each a dict with "type":
                                   {"type":"text","text": "..."}
                                   {"type":"thinking","thinking": "..."}
                                   {"type":"tool_use","name":"Edit","input":{...}}
                                   {"type":"tool_result", ...}

NOTE: content is under entry["message"]["content"], NOT entry["content"].
That single nesting level is the bug this module prevents.
"""

import json
from pathlib import Path

# Tools whose input names a file path we should attribute focus to.
EDIT_TOOLS = {"Write", "Edit", "MultiEdit", "NotebookEdit"}


def iter_entries(transcript_path: str):
    """Yield each parsed JSONL line as a dict. Tolerant of bad lines."""
    try:
        with open(transcript_path) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    yield json.loads(line)
                except json.JSONDecodeError:
                    continue
    except Exception:
        return


def _blocks(entry: dict):
    """Return the content as a list of blocks (normalizing the str form)."""
    message = entry.get("message")
    if not isinstance(message, dict):
        return []
    content = message.get("content", "")
    if isinstance(content, str):
        return [{"type": "text", "text": content}] if content else []
    if isinstance(content, list):
        return content
    return []


def message_role(entry: dict) -> str:
    """'user' | 'assistant' | '' — preferring message.role, falling back to type."""
    message = entry.get("message")
    if isinstance(message, dict) and message.get("role"):
        return message["role"]
    t = entry.get("type", "")
    return t if t in ("user", "assistant") else ""


def message_text(entry: dict) -> str:
    """Flatten text + thinking blocks of one entry to plain text."""
    parts = []
    for block in _blocks(entry):
        if not isinstance(block, dict):
            continue
        if block.get("type") == "text" and block.get("text"):
            parts.append(block["text"])
        elif block.get("type") == "thinking" and block.get("thinking"):
            parts.append(block["thinking"])
    return " ".join(parts)


def iter_tool_uses(transcript_path: str):
    """
    Yield (tool_name, input_dict) for every tool_use block across the
    transcript, in order. Only assistant entries carry tool_use blocks.
    """
    for entry in iter_entries(transcript_path):
        if message_role(entry) != "assistant":
            continue
        for block in _blocks(entry):
            if isinstance(block, dict) and block.get("type") == "tool_use":
                yield block.get("name", ""), block.get("input", {}) or {}


def edited_file_paths(transcript_path: str) -> list[str]:
    """
    Ordered list of file paths touched by edit/write tools across the
    transcript (oldest first). Empty inputs are skipped.
    """
    paths = []
    for name, inp in iter_tool_uses(transcript_path):
        if name not in EDIT_TOOLS:
            continue
        file_path = inp.get("file_path") or inp.get("path") or ""
        if file_path:
            paths.append(file_path)
    return paths


def iter_role_text(transcript_path: str):
    """
    Yield (role, text) for user/assistant entries that carry text, in order.
    Used by the pre-compaction extractor.
    """
    for entry in iter_entries(transcript_path):
        role = message_role(entry)
        if role not in ("user", "assistant"):
            continue
        text = message_text(entry)
        if text:
            yield role, text
