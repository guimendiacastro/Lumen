# lumen/api/app/utils/debug.py
from __future__ import annotations

import os
import json
import logging
from typing import List, Dict, Any

# Basic logger config (only once)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("lumen.debug")

def debug_enabled() -> bool:
    return os.getenv("DEBUG_LOG_PROMPTS", "false").lower() in ("1", "true", "yes", "on")

def format_messages(messages: List[Dict[str, Any]]) -> str:
    """
    Pretty string with roles and content as the model receives them.
    """
    parts = []
    for i, m in enumerate(messages, start=1):
        role = m.get("role", "?")
        content = m.get("content", "")
        parts.append(f"[{i:02d}] role={role}\n{content}")
    return "\n" + ("\n" + "-"*80 + "\n").join(parts) + "\n"

def dump_messages(label: str, provider: str | None, model: str | None, messages: List[Dict[str, Any]]):
    if not debug_enabled():
        return
    header = f"=== LLM REQUEST :: {label} :: provider={provider or '-'} model={model or '-'} ==="
    log.info("%s%s", header, format_messages(messages))
