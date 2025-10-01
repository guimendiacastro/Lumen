# lumen/api/app/utils/diff.py
from __future__ import annotations
import difflib
import re
from typing import List

_HEADING = re.compile(r'^\s{0,3}(#{1,6}|[0-9]+\.)\s+(.*)$')  # markdown or numbered headings

def _section_for_index(text: str, idx: int) -> str:
    """
    Find the nearest preceding heading for a character index.
    Returns a short label like '2. Obligations' or '## Term'.
    """
    start = max(0, idx - 2000)  # search back a bit
    snippet = text[start:idx]
    lines = snippet.splitlines()[::-1]
    for ln in lines:
        m = _HEADING.match(ln.strip())
        if m:
            return m.group(0)[:80]
    return "(no heading)"

def summarize_diff(old: str, new: str, max_bullets: int = 5, max_chars: int = 600) -> List[str]:
    """
    Produce a few human-readable bullets of what changed between old and new.
    Section-aware (best-effort). Trimmed to keep small.
    """
    s = difflib.SequenceMatcher(None, old, new, autojunk=True)
    bullets: List[str] = []
    for tag, i1, i2, j1, j2 in s.get_opcodes():
        if tag == "equal": 
            continue
        section = _section_for_index(old, i1) if tag in ("delete", "replace") else _section_for_index(new, j1)
        if tag == "insert":
            excerpt = new[j1:j2].strip()
            kind = "added"
        elif tag == "delete":
            excerpt = old[i1:i2].strip()
            kind = "removed"
        else:
            # replace
            excerpt = new[j1:j2].strip()
            kind = "updated"
        # compact excerpt
        excerpt = ' '.join(excerpt.split())
        if len(excerpt) > max_chars:
            excerpt = excerpt[:max_chars] + "…"
        bullets.append(f"{kind} in {section}: {excerpt}")
        if len(bullets) >= max_bullets:
            break
    if not bullets:
        bullets = ["no material changes detected"]
    return bullets
