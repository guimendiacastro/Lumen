# lumen/api/app/llm/clients.py
import os
import time
import asyncio
import logging
from openai import AsyncOpenAI, AsyncAzureOpenAI
from anthropic import AsyncAnthropic

log = logging.getLogger("lumen.llm")

# Legacy environment variables (kept for backward compatibility)
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4")
XAI_API_KEY = os.getenv("XAI_API_KEY")
XAI_MODEL = os.getenv("XAI_MODEL", "grok-1")

# Azure environment variables
AZURE_OPENAI_ENDPOINT = os.getenv("AZURE_OPENAI_ENDPOINT")
AZURE_OPENAI_KEY = os.getenv("AZURE_OPENAI_KEY")
AZURE_OPENAI_GPT_DEPLOYMENT = os.getenv("AZURE_OPENAI_GPT_DEPLOYMENT", "gpt-5-chat")
AZURE_OPENAI_API_VERSION = os.getenv("AZURE_OPENAI_API_VERSION", "2025-01-01-preview")

AZURE_AI_FOUNDRY_ENDPOINT = os.getenv("AZURE_AI_FOUNDRY_ENDPOINT")
AZURE_AI_FOUNDRY_KEY = os.getenv("AZURE_AI_FOUNDRY_KEY")
AZURE_GROK_DEPLOYMENT = os.getenv("AZURE_GROK_DEPLOYMENT", "grok-4-fast-reasoning")
AZURE_AI_FOUNDRY_API_VERSION = os.getenv("AZURE_AI_FOUNDRY_API_VERSION", "2024-05-01-preview")

# Anthropic (unchanged)
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-3-sonnet-20240229")

# Feature flag for Azure migration
USE_AZURE = os.getenv("USE_AZURE", "false").lower() == "true"

# Initialize clients based on configuration
if USE_AZURE:
    # Azure OpenAI for GPT
    openai_client = AsyncAzureOpenAI(
        api_key=AZURE_OPENAI_KEY,
        azure_endpoint=AZURE_OPENAI_ENDPOINT,
        api_version=AZURE_OPENAI_API_VERSION
    ) if AZURE_OPENAI_ENDPOINT and AZURE_OPENAI_KEY else None

    # Azure AI Foundry for Grok (uses OpenAI-compatible API)
    xai_client = AsyncOpenAI(
        api_key=AZURE_AI_FOUNDRY_KEY,
        base_url=AZURE_AI_FOUNDRY_ENDPOINT
    ) if AZURE_AI_FOUNDRY_ENDPOINT and AZURE_AI_FOUNDRY_KEY else None
else:
    # Legacy direct API clients
    openai_client = AsyncOpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None
    xai_client = AsyncOpenAI(
        api_key=XAI_API_KEY,
        base_url="https://api.x.ai/v1"
    ) if XAI_API_KEY else None

# Anthropic always uses direct API
anthropic_client = AsyncAnthropic(api_key=ANTHROPIC_API_KEY) if ANTHROPIC_API_KEY else None


async def call_openai(messages: list[dict], model: str = None, json_mode: bool = False) -> dict:
    """Call OpenAI API with optional JSON mode."""
    if not openai_client:
        return {"provider": "openai", "text": "", "ok": False, "error": "OpenAI API key not configured"}

    # Use deployment name for Azure, model name for direct API
    if USE_AZURE:
        model = model or AZURE_OPENAI_GPT_DEPLOYMENT
    else:
        model = model or OPENAI_MODEL

    # Log input to ChatGPT
    log.info("=" * 80)
    log.info("🤖 CHATGPT INPUT (model: %s)", model)
    log.info("=" * 80)
    for i, msg in enumerate(messages, 1):
        role = msg.get("role", "?").upper()
        content = msg.get("content", "")
        log.info("[%d] %s:", i, role)
        log.info("%s", content)
        log.info("-" * 80)

    start = time.time()
    try:
        kwargs = {
            "model": model,
            "messages": messages,
        }

        # GPT-5-mini only supports temperature=1 (default), other models can use 0.3
        if "gpt-5-mini" not in model.lower():
            kwargs["temperature"] = 0.3

        # Enable JSON mode if requested
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}

        response = await openai_client.chat.completions.create(**kwargs)
        elapsed_ms = int((time.time() - start) * 1000)

        response_text = response.choices[0].message.content or ""

        # Log output from ChatGPT
        log.info("=" * 80)
        log.info("🤖 CHATGPT OUTPUT (latency: %dms, tokens: %d in / %d out)",
                 elapsed_ms,
                 response.usage.prompt_tokens if response.usage else 0,
                 response.usage.completion_tokens if response.usage else 0)
        log.info("=" * 80)
        log.info("%s", response_text)
        log.info("=" * 80)
        log.info("")

        return {
            "provider": "openai",
            "text": response_text,
            "input_tokens": response.usage.prompt_tokens if response.usage else None,
            "output_tokens": response.usage.completion_tokens if response.usage else None,
            "latency_ms": elapsed_ms,
            "ok": True,
        }
    except Exception as e:
        elapsed_ms = int((time.time() - start) * 1000)
        log.error("❌ CHATGPT ERROR: %s", str(e))
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
    """Call xAI/Grok API via Azure AI Foundry or direct API."""
    if not xai_client:
        return {"provider": "xai", "text": "", "ok": False, "error": "xAI API key not configured"}

    # Use deployment name for Azure Foundry, model name for direct API
    if USE_AZURE:
        model = model or AZURE_GROK_DEPLOYMENT
    else:
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