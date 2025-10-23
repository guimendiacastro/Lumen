# lumen/api/app/llm/clients.py
import os
import time
import asyncio
from openai import AsyncOpenAI
from anthropic import AsyncAnthropic

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-3-sonnet-20240229")
XAI_API_KEY = os.getenv("XAI_API_KEY")
XAI_MODEL = os.getenv("XAI_MODEL", "grok-1")

openai_client = AsyncOpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None
anthropic_client = AsyncAnthropic(api_key=ANTHROPIC_API_KEY) if ANTHROPIC_API_KEY else None
xai_client = AsyncOpenAI(
    api_key=XAI_API_KEY,
    base_url="https://api.x.ai/v1"
) if XAI_API_KEY else None


async def call_openai(messages: list[dict], model: str = None, json_mode: bool = False) -> dict:
    """Call OpenAI API with optional JSON mode."""
    if not openai_client:
        return {"provider": "openai", "text": "", "ok": False, "error": "OpenAI API key not configured"}
    
    # Use environment variable model if none specified
    model = model or OPENAI_MODEL
    
    start = time.time()
    try:
        kwargs = {
            "model": model,
            "messages": messages,
            "temperature": 0.3,
        }
        
        # Enable JSON mode if requested
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}
        
        response = await openai_client.chat.completions.create(**kwargs)
        elapsed_ms = int((time.time() - start) * 1000)
        
        return {
            "provider": "openai",
            "text": response.choices[0].message.content or "",
            "input_tokens": response.usage.prompt_tokens if response.usage else None,
            "output_tokens": response.usage.completion_tokens if response.usage else None,
            "latency_ms": elapsed_ms,
            "ok": True,
        }
    except Exception as e:
        elapsed_ms = int((time.time() - start) * 1000)
        return {
            "provider": "openai",
            "text": "",
            "ok": False,
            "error": str(e),
            "latency_ms": elapsed_ms,
        }


async def call_anthropic(messages: list[dict], model: str = None, json_mode: bool = False) -> dict:
    """Call Anthropic API."""
    if not anthropic_client:
        return {"provider": "anthropic", "text": "", "ok": False, "error": "Anthropic API key not configured"}
    
    # Use environment variable model if none specified
    model = model or ANTHROPIC_MODEL
    
    start = time.time()
    try:
        # Extract system message if present
        system_msg = None
        chat_messages = []
        for msg in messages:
            if msg["role"] == "system":
                system_msg = msg["content"] if not system_msg else f"{system_msg}\n\n{msg['content']}"
            else:
                chat_messages.append(msg)
        
        kwargs = {
            "model": model,
            "max_tokens": 8192,
            "messages": chat_messages,
            "temperature": 0.3,
        }
        
        if system_msg:
            kwargs["system"] = system_msg
        
        response = await anthropic_client.messages.create(**kwargs)
        elapsed_ms = int((time.time() - start) * 1000)
        
        content = response.content[0].text if response.content else ""
        
        return {
            "provider": "anthropic",
            "text": content,
            "input_tokens": response.usage.input_tokens if response.usage else None,
            "output_tokens": response.usage.output_tokens if response.usage else None,
            "latency_ms": elapsed_ms,
            "ok": True,
        }
    except Exception as e:
        elapsed_ms = int((time.time() - start) * 1000)
        return {
            "provider": "anthropic",
            "text": "",
            "ok": False,
            "error": str(e),
            "latency_ms": elapsed_ms,
        }


async def call_xai(messages: list[dict], model: str = None, json_mode: bool = False) -> dict:
    """Call xAI/Grok API (JSON mode not supported yet)."""
    if not xai_client:
        return {"provider": "xai", "text": "", "ok": False, "error": "xAI API key not configured"}
    
    # Use environment variable model if none specified
    model = model or XAI_MODEL
    
    start = time.time()
    try:
        kwargs = {
            "model": model,
            "messages": messages,
            "temperature": 0.3,
        }
        
        # Note: xAI/Grok doesn't support JSON mode yet as of Oct 2025
        # So we don't add response_format even if json_mode=True
        
        response = await xai_client.chat.completions.create(**kwargs)
        elapsed_ms = int((time.time() - start) * 1000)
        
        return {
            "provider": "xai",
            "text": response.choices[0].message.content or "",
            "input_tokens": response.usage.prompt_tokens if response.usage else None,
            "output_tokens": response.usage.completion_tokens if response.usage else None,
            "latency_ms": elapsed_ms,
            "ok": True,
        }
    except Exception as e:
        elapsed_ms = int((time.time() - start) * 1000)
        return {
            "provider": "xai",
            "text": "",
            "ok": False,
            "error": str(e),
            "latency_ms": elapsed_ms,
        }


async def fanout_with_history(messages: list[dict]) -> list[dict]:
    """
    Fan out to all configured providers in parallel.
    Detects if JSON mode should be used based on system prompt.
    """
    # Check if system prompt requests JSON output
    json_mode = False
    for msg in messages:
        if msg["role"] == "system" and "JSON" in msg["content"]:
            json_mode = True
            break
    
    tasks = []
    if openai_client:
        tasks.append(call_openai(messages, json_mode=json_mode))
    if anthropic_client:
        tasks.append(call_anthropic(messages, json_mode=json_mode))
    if xai_client:
        tasks.append(call_xai(messages, json_mode=json_mode))
    
    if not tasks:
        return [{
            "provider": "none",
            "text": "No AI providers configured",
            "ok": False,
        }]
    
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    # Handle exceptions
    output = []
    for r in results:
        if isinstance(r, Exception):
            output.append({
                "provider": "unknown",
                "text": "",
                "ok": False,
                "error": str(r),
            })
        else:
            output.append(r)
    
    return output