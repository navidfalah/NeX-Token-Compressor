"""
Firma-KI — NEX Pipeline Utility
Three-stage pipeline for every AI interaction:

  [Stage 1] DeepSeek Compressor  : human text    → NEX bytecode  (always DeepSeek)
  [Stage 2] Configured Provider  : NEX input     → NEX output    (DeepSeek OR OpenAI etc.)
  [Stage 3] DeepSeek Translator  : NEX bytecode  → human text    (always DeepSeek)

Stages 1 and 3 are internal Firma-KI optimization steps and always route via
the system DeepSeek key, regardless of the user's chosen Stage 2 provider.
"""

import json
import os
import httpx
import asyncio
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select


# ---------------------------------------------------------------------------
# Shared DeepSeek endpoint helpers
# ---------------------------------------------------------------------------

_DEEPSEEK_URL = "https://api.deepseek.com/chat/completions"

# Cached NEX rules content
_nex_rules_cache: str | None = None


def _load_nex_rules() -> str:
    global _nex_rules_cache
    if _nex_rules_cache is None:
        try:
            from core.config import settings
            rules_path = os.path.join(settings.BASE_DIR, "COMPRESSION_RULES.md")
            if os.path.exists(rules_path):
                with open(rules_path, "r", encoding="utf-8") as f:
                    _nex_rules_cache = f.read()
            else:
                _nex_rules_cache = ""
        except Exception:
            _nex_rules_cache = ""
    return _nex_rules_cache


async def _get_system_deepseek_key(db: AsyncSession = None) -> str:
    """
    Resolve the system/global DeepSeek API key from the DB or environment.
    """
    # 1. Try env variable first
    env_key = os.environ.get("DEEPSEEK_API_KEY", "")
    if env_key:
        return env_key

    # 2. Fall back to the system-level DeepSeek provider in the DB
    if db:
        try:
            from models.dashboard import AIProvider
            stmt = select(AIProvider).where(
                AIProvider.provider_type == "deepseek",
                AIProvider.is_system == True,
                AIProvider.is_active == True
            ).limit(1)
            result = await db.execute(stmt)
            provider = result.scalar_one_or_none()
            if provider and provider.api_key:
                return provider.api_key
        except Exception:
            pass

    return ""


async def _deepseek_call_async(messages: list, api_key: str, temperature: float = 0.3) -> str:
    """
    Fire a single async DeepSeek API call.
    """
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }
    payload = {
        "model": "deepseek-chat",
        "messages": messages,
        "temperature": temperature,
    }
    
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.post(_DEEPSEEK_URL, json=payload, headers=headers, timeout=60.0)
            resp.raise_for_status()
            body = resp.json()
            return body["choices"][0]["message"]["content"]
        except Exception as e:
            print(f"[NEX Pipeline] DeepSeek call failed: {e}")
            return ""


# ---------------------------------------------------------------------------
# Stage 1 — Compress human text → NEX bytecode  (always DeepSeek)
# ---------------------------------------------------------------------------

_STAGE1_SYSTEM = """\
You are the Firma-KI NEX Context Synthesizer (Stage 1).
Your ONLY purpose is EXTREME TOKEN COMPRESSION. You receive bloated human text, chat history, and document context, and you must transpile the entire semantic meaning into ultra-dense "NEX Bytecode" for the downstream logic engine.

CRITICAL COMPRESSION RULES:
1. NEVER USE FULL SENTENCES OR GRAMMAR. Discard all articles (a, an, the), prepositions, and pleasantries.
2. USE MATHEMATICAL SHORTHAND. Replace words with symbols (e.g., "increases to" -> "->", "and" -> "&", "user wants" -> "USR_REQ:").
3. CONDENSE CONTEXT. Extract only the hard facts required to answer the query. Drop all fluff.
4. USE BRACKET SYNTAX. Format logic like: `[FACT:x=y][REQ:do_z]`
5. TARGET 80% COMPRESSION. Your output must be a fraction of the input length, looking like pure machine code or API arguments.

Example Output Format:
`[CTX:server_down_3pm,db_timeout][USR_REQ:root_cause,fix_steps]`

OUTPUT ONLY THE NEX STRING. No explanations. No greetings.\
"""

async def compress_to_nex_async(db: AsyncSession, human_text: str, context_text: str = "", messages_history: list = None) -> str:
    api_key = await _get_system_deepseek_key(db)
    if not api_key:
        return human_text

    sys_content = _STAGE1_SYSTEM
    if context_text:
        sys_content += f"\n\nDOCUMENT CONTEXT:\n{context_text}"
        
    messages = [{"role": "system", "content": sys_content}]
    if messages_history:
        for msg in messages_history:
            if msg.get('role') in ('user', 'assistant'):
                messages.append({"role": msg['role'], "content": msg['content']})
                
    messages.append({"role": "user", "content": f"LATEST QUERY:\n{human_text}"})

    result = await _deepseek_call_async(messages, api_key, temperature=0.1)
    if not result or not result.strip():
        return human_text
    return result.strip()


# ---------------------------------------------------------------------------
# Stage 2 — Core AI logic: NEX input → NEX output  (user's chosen provider)
# ---------------------------------------------------------------------------

async def call_logic_provider_async(provider, nex_messages: list, model: str = None, temperature: float = None) -> tuple[str, int, int]:
    provider_type = getattr(provider, "provider_type", "deepseek")
    api_key = provider.api_key or ""
    resolved_model = model or getattr(provider, "model_name", "")

    if provider_type == "gemini":
        resolved_model = resolved_model or "gemini-1.5-pro"
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{resolved_model}:generateContent?key={api_key}"
        headers = {"Content-Type": "application/json"}
        
        contents = []
        system_instruction = None
        for msg in nex_messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if role == "system":
                system_instruction = {"parts": [{"text": content}]}
            else:
                gemini_role = "model" if role == "assistant" else "user"
                contents.append({"role": gemini_role, "parts": [{"text": content}]})
                
        payload = {
            "contents": contents,
            "generationConfig": {
                "temperature": temperature if temperature is not None else getattr(provider, "temperature", 0.7)
            }
        }
        if system_instruction:
            payload["systemInstruction"] = system_instruction
            
        async with httpx.AsyncClient() as client:
            try:
                resp = await client.post(url, json=payload, headers=headers, timeout=90.0)
                resp.raise_for_status()
                body = resp.json()
                content = body["candidates"][0]["content"]["parts"][0]["text"]
                usage = body.get("usageMetadata", {})
                return content, usage.get("promptTokenCount", 0), usage.get("candidatesTokenCount", 0)
            except Exception as e:
                print(f"[NEX Stage 2 Gemini] Error: {e}")
                return "", 0, 0
    else:
        # OpenAI/DeepSeek
        if provider_type == "openai":
            base = getattr(provider, "api_base_url", "") or "https://api.openai.com"
            url = f"{base.rstrip('/')}/v1/chat/completions"
        else:
            url = _DEEPSEEK_URL
            
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        }
        payload = {
            "model": resolved_model or ("deepseek-chat" if provider_type == "deepseek" else "gpt-4o"),
            "messages": nex_messages,
            "temperature": temperature if temperature is not None else getattr(provider, "temperature", 0.7),
        }
        
        async with httpx.AsyncClient() as client:
            try:
                resp = await client.post(url, json=payload, headers=headers, timeout=90.0)
                resp.raise_for_status()
                body = resp.json()
                content = body["choices"][0]["message"]["content"]
                usage = body.get("usage", {})
                return content, usage.get("prompt_tokens", 0), usage.get("completion_tokens", 0)
            except Exception as e:
                print(f"[NEX Stage 2] Error: {e}")
                return "", 0, 0


# ---------------------------------------------------------------------------
# Stage 3 — Translate NEX bytecode → Human text  (always DeepSeek, streaming)
# ---------------------------------------------------------------------------

_STAGE3_SYSTEM = (
    "You are the Firma-KI Output Expander (Stage 3). "
    "You are receiving ultra-dense 'NEX Bytecode' generated by a core reasoning engine. "
    "Your EXACT job is to completely De-compress this logic into a beautiful, comprehensive, and natural-sounding human response. "
    "CRITICAL RULES: \n"
    "1. Do NOT leak any brackets, tags, or NEX syntax to the user.\n"
    "2. Be polite, professional, and use Markdown formatting.\n"
    "3. Expand the terse logic into full, articulate sentences.\n"
    "4. VERY IMPORTANT: If the core engine returns structured data (code blocks, JSON, etc.), output it EXACTLY AS-IS."
)

async def stream_translate_from_nex_async(nex_text: str, api_key: str = ""):
    if not api_key:
        api_key = await _get_system_deepseek_key()

    messages = [
        {"role": "system", "content": _STAGE3_SYSTEM},
        {"role": "user", "content": f"Translate this NEX to Human:\n{nex_text}"},
    ]
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }
    payload = {
        "model": "deepseek-chat",
        "messages": messages,
        "temperature": 0.4,
        "stream": True,
    }

    async with httpx.AsyncClient() as client:
        try:
            async with client.stream("POST", _DEEPSEEK_URL, json=payload, headers=headers, timeout=60.0) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if not line or not line.startswith("data: "):
                        continue
                    data_str = line[6:]
                    if data_str == "[DONE]":
                        break
                    try:
                        chunk = json.loads(data_str)
                        delta = chunk.get("choices", [{}])[0].get("delta", {})
                        if delta.get("content"):
                            yield delta["content"]
                    except json.JSONDecodeError:
                        pass
        except Exception as e:
            print(f"[NEX Pipeline] Stage 3 failed: {e}")
            yield nex_text


async def translate_from_nex_blocking_async(db: AsyncSession, nex_text: str) -> tuple[str, int, int]:
    api_key = await _get_system_deepseek_key(db)
    if not api_key:
        return nex_text, 0, 0

    messages = [
        {"role": "system", "content": _STAGE3_SYSTEM},
        {"role": "user", "content": f"Translate this NEX to Human:\n{nex_text}"},
    ]
    result = await _deepseek_call_async(messages, api_key, temperature=0.4)
    if result:
        prompt_tokens = max(1, len(nex_text) // 4)
        completion_tokens = max(1, len(result) // 4)
        return result, prompt_tokens, completion_tokens
    return nex_text, 0, 0
