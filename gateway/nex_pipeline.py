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
import urllib.request
import urllib.error


# ---------------------------------------------------------------------------
# Shared DeepSeek endpoint helpers
# ---------------------------------------------------------------------------

_DEEPSEEK_URL = "https://api.deepseek.com/chat/completions"

# Cached NEX rules content (loaded once on first call)
_nex_rules_cache: str | None = None


def _load_nex_rules() -> str:
    global _nex_rules_cache
    if _nex_rules_cache is None:
        try:
            from django.conf import settings
            rules_path = os.path.join(settings.BASE_DIR, "COMPRESSION_RULES.md")
            with open(rules_path, "r", encoding="utf-8") as f:
                _nex_rules_cache = f.read()
        except Exception:
            _nex_rules_cache = ""
    return _nex_rules_cache


def _get_system_deepseek_key() -> str:
    """
    Resolve the system/global DeepSeek API key from the DB or environment.
    Stage 1 and 3 always use this key regardless of the user-selected provider.
    """
    # 1. Try env variable first (fastest)
    env_key = os.environ.get("DEEPSEEK_API_KEY", "")
    if env_key:
        return env_key

    # 2. Fall back to the system-level DeepSeek provider in the DB
    try:
        from dashboard.models import AIProvider
        provider = AIProvider.objects.filter(
            provider_type=AIProvider.PROVIDER_DEEPSEEK,
            is_system=True,
            is_active=True
        ).first()
        if provider and provider.api_key:
            return provider.api_key
    except Exception:
        pass

    return ""


def _deepseek_call_blocking(messages: list, api_key: str, temperature: float = 0.3) -> str:
    """
    Fire a single blocking (non-streaming) DeepSeek API call.
    Returns the assistant's reply text, or empty string on error.
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
    req = urllib.request.Request(
        _DEEPSEEK_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=45) as resp:
            body = json.loads(resp.read().decode("utf-8"))
            return body["choices"][0]["message"]["content"]
    except Exception as e:
        print(f"[NEX Pipeline] DeepSeek blocking call failed: {e}")
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

def compress_to_nex(human_text: str, context_text: str = "", messages_history: list = None) -> str:
    """
    Stage 1: Context Synthesizer (Cheap AI).
    Absorbs the heavy payload (document context + chat history + user query) 
    and outputs a tiny, dense 'Logic Mission' for Stage 2.
    """
    api_key = _get_system_deepseek_key()
    if not api_key:
        return human_text  # Degrade gracefully

    # Build the massive prompt for Stage 1
    sys_content = _STAGE1_SYSTEM
    if context_text:
        sys_content += f"\n\nDOCUMENT CONTEXT (Use exact facts from this if relevant):\n{context_text}"
        
    messages = [{"role": "system", "content": sys_content}]
    
    if messages_history:
        for msg in messages_history:
            # Only include user/ai roles to save tokens from nested system prompts
            if msg.get('role') in ('user', 'ai', 'assistant'):
                messages.append({"role": msg['role'], "content": msg['content']})
                
    messages.append({"role": "user", "content": f"LATEST QUERY:\n{human_text}"})

    try:
        result = _deepseek_call_blocking(messages, api_key, temperature=0.1)
        if not result or not result.strip():
            return human_text
        return result.strip()
    except Exception as e:
        print(f"[NEX Stage 1] Context Synthesize failed: {e}")
        return human_text



# ---------------------------------------------------------------------------
# Stage 2 — Core AI logic: NEX input → NEX output  (user's chosen provider)
# ---------------------------------------------------------------------------

def _get_provider_url_and_headers(provider) -> tuple[str, dict]:
    """Return (url, headers) for the configured provider."""
    provider_type = getattr(provider, "provider_type", "deepseek")
    api_key = provider.api_key or ""

    if provider_type == "openai":
        base = getattr(provider, "api_base_url", "") or "https://api.openai.com"
        base = base.rstrip("/")
        url = f"{base}/v1/chat/completions"
    elif provider_type == "deepseek":
        url = _DEEPSEEK_URL
    else:
        # Generic OpenAI-compatible endpoint
        base = getattr(provider, "api_base_url", "") or _DEEPSEEK_URL
        url = base if "/chat/completions" in base else base.rstrip("/") + "/chat/completions"

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }
    return url, headers


def call_logic_provider_blocking(provider, nex_messages: list) -> tuple[str, int, int]:
    """
    Stage 2 (blocking): Send NEX messages to the configured provider.
    Returns (nex_response_text, prompt_tokens, completion_tokens).
    """
    url, headers = _get_provider_url_and_headers(provider)
    model = getattr(provider, "model_name", "") or (
        "deepseek-chat" if provider.provider_type == "deepseek" else "gpt-4o"
    )
    payload = {
        "model": model,
        "messages": nex_messages,
        "temperature": getattr(provider, "temperature", 0.7),
    }
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=90) as resp:
            body = json.loads(resp.read().decode("utf-8"))
            content = body["choices"][0]["message"]["content"]
            usage = body.get("usage", {})
            return content, usage.get("prompt_tokens", 0), usage.get("completion_tokens", 0)
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8", errors="replace")
        print(f"[NEX Stage 2] HTTPError {e.code}: {err_body[:300]}")
        return "", 0, 0
    except Exception as e:
        print(f"[NEX Stage 2] {type(e).__name__}: {e}")
        return "", 0, 0


def stream_logic_provider(provider, nex_messages: list):
    """
    Stage 2 (streaming): Send NEX messages to the configured provider.
    Yields (content_chunk, is_usage_chunk, usage_dict) tuples.
    For internal NEX pipeline use when subsequent Stage 3 is streaming separately.
    This version is blocking — accumulates full response then yields it once.
    """
    text, pt, ct = call_logic_provider_blocking(provider, nex_messages)
    return text, pt, ct


# ---------------------------------------------------------------------------
# Stage 3 — Translate NEX bytecode → Human text  (always DeepSeek, streaming)
# ---------------------------------------------------------------------------

_STAGE3_SYSTEM = (
    "You are the Firma-KI Output Expander (Stage 3). "
    "You are receiving ultra-dense 'NEX Bytecode' (e.g., `[FACT:x=y]`, symbols, shorthand) generated by a core reasoning engine. "
    "Your EXACT job is to completely De-compress this logic into a beautiful, comprehensive, and natural-sounding human response. "
    "CRITICAL RULES: \n"
    "1. Do NOT leak any brackets, tags, or NEX syntax to the user.\n"
    "2. Be polite, professional, and use Markdown formatting (bolding, lists) to make the answer easy to read.\n"
    "3. Expand the terse logic into full, articulate sentences.\n"
    "4. VERY IMPORTANT: If the core engine returns structured data (like a programming code block, a script, or JSON), output it EXACTLY AS-IS. Do NOT wrap it in a long narrative or explain how the code works unless the user specifically asked for an explanation. We want to save tokens, so just give the user the script."
)


def stream_translate_from_nex(nex_text: str, api_key: str = ""):
    """
    Stage 3: Stream a DeepSeek translation of NEX bytecode → Human text.
    Yields decoded text chunk strings.
    The caller is responsible for urllib session/streaming setup.
    Returns a generator.
    """
    if not api_key:
        api_key = _get_system_deepseek_key()

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

    req = urllib.request.Request(
        _DEEPSEEK_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            for raw_line in resp:
                line = raw_line.decode("utf-8").strip()
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
        print(f"[NEX Pipeline] Stage 3 DeepSeek stream failed: {e}")
        yield nex_text  # degrade: return raw NEX if translation fails


def translate_from_nex_blocking(nex_text: str) -> str:
    """
    Stage 3 (blocking): DeepSeek translation of NEX → Human text.
    Used in non-streaming endpoints like api_chat_update.
    """
    api_key = _get_system_deepseek_key()
    if not api_key:
        return nex_text

    messages = [
        {"role": "system", "content": _STAGE3_SYSTEM},
        {"role": "user", "content": f"Translate this NEX to Human:\n{nex_text}"},
    ]
    result = _deepseek_call_blocking(messages, api_key, temperature=0.4)
    return result if result else nex_text
