from __future__ import annotations

import os
import time
import asyncio
from typing import Dict, Any, List
import httpx
from tenacity import retry, stop_after_attempt, wait_exponential
from dotenv import load_dotenv
from ..utils.debug import dump_messages


load_dotenv()

OPENAI_API_KEY   = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL     = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
ANTHROPIC_MODEL   = os.getenv("ANTHROPIC_MODEL", "claude-3-5-sonnet-20240620")
ANTHROPIC_VERSION = os.getenv("ANTHROPIC_VERSION", "2023-06-01")

XAI_API_KEY   = os.getenv("XAI_API_KEY")
XAI_MODEL     = os.getenv("XAI_MODEL", "grok-2-latest")
XAI_BASE_URL  = os.getenv("XAI_BASE_URL", "https://api.x.ai/v1")

ProviderResult = Dict[str, Any]
TIMEOUT_SECS = 45.0

def _stub(provider: str, reason: str) -> ProviderResult:
    return {
        "provider": provider,
        "text": f"[{provider} not configured: {reason}]",
        "latency_ms": 0,
        "input_tokens": None,
        "output_tokens": None,
        "ok": False,
    }

@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=6))
async def _call_openai(messages: List[Dict[str, str]]) -> ProviderResult:
    if not OPENAI_API_KEY:
        return _stub("openai", "missing OPENAI_API_KEY")
    # NEW: debug log
    dump_messages(label="provider_call", provider="openai", model=OPENAI_MODEL, messages=messages)
    start = time.perf_counter()
    headers = {"Authorization": f"Bearer {OPENAI_API_KEY}"}
    payload = { "model": OPENAI_MODEL, "messages": messages, "temperature": 0.2 }
    async with httpx.AsyncClient(timeout=TIMEOUT_SECS) as client:
        r = await client.post("https://api.openai.com/v1/chat/completions", headers=headers, json=payload)
        r.raise_for_status()
        data = r.json()
    text = data["choices"][0]["message"]["content"]
    usage = data.get("usage", {})
    latency = int((time.perf_counter() - start) * 1000)
    return {
        "provider": "openai",
        "text": text,
        "latency_ms": latency,
        "input_tokens": usage.get("prompt_tokens"),
        "output_tokens": usage.get("completion_tokens"),
        "ok": True,
    }

@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=6))
async def _call_anthropic(messages: List[Dict[str, str]]) -> ProviderResult:
    if not ANTHROPIC_API_KEY:
        return _stub("anthropic", "missing ANTHROPIC_API_KEY")

    # Anthropic expects messages without a separate system role in some cases; we’ll convert:
    system = ""
    conv: List[Dict[str, str]] = []
    for m in messages:
        if m["role"] == "system":
            system += (m["content"] + "\n")
        else:
            conv.append(m)

    anthro_msgs = ([{"role": "system", "content": system.strip()}] if system.strip() else []) + conv
    dump_messages(label="provider_call", provider="anthropic", model=ANTHROPIC_MODEL, messages=anthro_msgs)
    
    start = time.perf_counter()
    headers = {
        "x-api-key": ANTHROPIC_API_KEY,
        "anthropic-version": ANTHROPIC_VERSION,
        "content-type": "application/json",
    }
    payload: Dict[str, Any] = {
        "model": ANTHROPIC_MODEL,
        "max_tokens": 1024,
        "temperature": 0.2,
        "messages": [{"role": m["role"], "content": m["content"]} for m in conv],
    }
    if system.strip():
        payload["system"] = system.strip()

    async with httpx.AsyncClient(timeout=TIMEOUT_SECS) as client:
        r = await client.post("https://api.anthropic.com/v1/messages", headers=headers, json=payload)
        r.raise_for_status()
        data = r.json()
    parts = [blk.get("text", "") for blk in data.get("content", []) if blk.get("type") == "text"]
    text = "\n".join([p for p in parts if p])
    usage = data.get("usage", {})
    latency = int((time.perf_counter() - start) * 1000)
    return {
        "provider": "anthropic",
        "text": text,
        "latency_ms": latency,
        "input_tokens": usage.get("input_tokens"),
        "output_tokens": usage.get("output_tokens"),
        "ok": True,
    }

@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=6))
async def _call_xai(messages: List[Dict[str, str]]) -> ProviderResult:
    if not XAI_API_KEY:
        return _stub("xai", "missing XAI_API_KEY")

    start = time.perf_counter()
    headers = {"Authorization": f"Bearer {XAI_API_KEY}", "content-type": "application/json"}
    payload = { "model": XAI_MODEL, "messages": messages, "temperature": 0.2 }
    async with httpx.AsyncClient(timeout=TIMEOUT_SECS) as client:
        r = await client.post(f"{XAI_BASE_URL}/chat/completions", headers=headers, json=payload)
        r.raise_for_status()
        data = r.json()
    if "choices" in data and data["choices"]:
        text = data["choices"][0]["message"].get("content") or data["choices"][0].get("text", "")
    else:
        text = data.get("output_text") or ""
    usage = data.get("usage", {})
    latency = int((time.perf_counter() - start) * 1000)
    return {
        "provider": "xai",
        "text": text,
        "latency_ms": latency,
        "input_tokens": usage.get("prompt_tokens"),
        "output_tokens": usage.get("completion_tokens"),
        "ok": True,
    }

async def fanout_with_history(messages: List[Dict[str, str]]) -> List[ProviderResult]:
    results = await asyncio.gather(
        _call_openai(messages),
        _call_anthropic(messages),
        _call_xai(messages),
        return_exceptions=True,
    )
    out: List[ProviderResult] = []
    for res, name in zip(results, ["openai", "anthropic", "xai"]):
        if isinstance(res, Exception):
            out.append(_stub(name, f"error: {type(res).__name__}"))
        else:
            out.append(res)
    return out
