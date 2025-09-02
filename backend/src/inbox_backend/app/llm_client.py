from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional, Tuple

import httpx

from .config import settings


def _get_ollama_base() -> str:
    return getattr(settings, "ollama_url", "http://localhost:11434")


def _get_timeout() -> float:
    """
    Backward-compat single-number timeout (kept for env compatibility).
    If provided, we apply it to read/write/pool. Otherwise we use defaults.
    """
    return float(getattr(settings, "llm_timeout_seconds", 300))  # default 5 minutes


def _get_httpx_timeout() -> "httpx.Timeout":
    """
    Build a granular httpx.Timeout:
    - short connect timeout (10s)
    - long read/write/pool timeouts (from _get_timeout())
    """
    t = _get_timeout()
    try:
        return httpx.Timeout(connect=10.0, read=t, write=t, pool=t)
    except Exception:
        # Fallback if httpx changes; float means total timeout
        return httpx.Timeout(t)


def _default_model() -> str:
    return getattr(settings, "llm_model_summary", "deepseek-r1:32b")


def _json_only(content: str) -> str:
    """
    Try to coerce model output to strict JSON:
    - If pure JSON parse works, return as-is.
    - Else strip non-JSON text by taking the first {...} block.
    """
    content = content.strip()
    try:
        json.loads(content)
        return content
    except Exception:
        pass

    # Find first plausible JSON object
    m = re.search(r"\{[\s\S]*\}", content)
    if m:
        candidate = m.group(0)
        # Remove trailing commas (common model mistake)
        candidate = re.sub(r",\s*([}\]])", r"\1", candidate)
        return candidate
    return content


async def chat_json(
    system_prompt: str,
    user_prompt: str,
    model: Optional[str] = None,
    temperature: float = 0.2,
    num_ctx: int = 8192,
) -> Tuple[Optional[Dict[str, Any]], Dict[str, int], Optional[str]]:
    """
    Call Ollama /api/chat with format=json and return (json_obj, token_usage, error_msg).
    """
    base = _get_ollama_base()
    timeout = _get_timeout()
    model = model or _default_model()

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "stream": False,
        "format": "json",
        "options": {
            "temperature": temperature,
            "num_ctx": num_ctx,
        },
    }

    async with httpx.AsyncClient(timeout=_get_httpx_timeout()) as client:
        try:
            r = await client.post(f"{base}/api/chat", json=payload)
            # Keep raw text for better error reporting
            raw_text = r.text
            r.raise_for_status()
            data = r.json()
        except httpx.TimeoutException:
            return None, {"prompt": 0, "completion": 0}, "Ollama request failed: timeout"
        except httpx.HTTPStatusError as e:
            try:
                msg = e.response.text
            except Exception:
                msg = str(e)
            return None, {"prompt": 0, "completion": 0}, f"Ollama HTTP {e.response.status_code}: {msg}"
        except Exception as e:
            return None, {"prompt": 0, "completion": 0}, f"Ollama request failed: {e}"

    # Ollama chat response shape
    content = ""
    try:
        content = data.get("message", {}).get("content", "") or data.get("response", "")
    except Exception:
        content = ""

    if not content:
        # Model might not be available or failed silently
        return None, {
            "prompt": int(data.get("prompt_eval_count", 0)),
            "completion": int(data.get("eval_count", 0)),
        }, "Empty response from model"

    content = _json_only(content)
    try:
        obj = json.loads(content)
    except Exception as e:
        return None, {
            "prompt": int(data.get("prompt_eval_count", 0)),
            "completion": int(data.get("eval_count", 0)),
        }, f"Invalid JSON from model: {e}"

    usage = {
        "prompt": int(data.get("prompt_eval_count", 0)),
        "completion": int(data.get("eval_count", 0)),
    }
    return obj, usage, None


def compose_memory_block(memory_items: List[Dict[str, str]], max_chars: int = 3000) -> str:
    """
    Render memory items into a compact, headed block. Items are expected to be dicts with
    kind, key, value (already filtered/sorted by server). We keep it tiny.
    """
    if not memory_items:
        return ""
    lines: List[str] = []
    current_kind = None
    used = 0
    for it in memory_items:
        kind = it.get("kind", "fact")
        key = it.get("key", "")
        value = it.get("value", "")
        if kind != current_kind:
            lines.append(f"[{kind.upper()}]")
            current_kind = kind
        val = value.strip().replace("\n", " ")
        line = f"- {key}: {val}"
        if used + len(line) > max_chars:
            break
        lines.append(line)
        used += len(line) + 1
    return "\n".join(lines)


SYSTEM_SUMMARY_PROMPT = """You are a precise, privacy-preserving email triage assistant for Rutger.
Your task: read an email and output STRICT JSON with this schema:
version, lang, bullets (≤3), key_actions (imperatives, ≤3),
urgency (integer 0..5), importance (integer 0..5), priority (ignored; backend derives),
labels (≤3, choose only from ALLOWED_LABELS), confidence (0..1), truncated (bool),
model (string), token_usage {{prompt, completion}}, notes (string, optional).

DEFINITIONS
- Urgency: time pressure. 0 = none; 5 = same-day or immediate risk.
- Importance: relevance/impact to Rutger’s goals, VIPs, finance/legal, or prior commitments.
- Key actions: 1–3 concrete steps for Rutger (e.g., "Reply: send availability Tue/Wed", "Schedule 30m").
- Labels: pick ONLY from ALLOWED_LABELS. If no match, use "uncategorized".
- Language: detect primary language code like "nl" or "en".

CONSTRAINTS
- Do NOT include any reasoning or extra text. Return ONLY JSON.
- Do NOT echo the email body.
- If newsletter/marketing and no action needed, importance ≤ 1 unless memory explicitly says otherwise.
- If the sender asks for information/decisions from Rutger, importance ≥ 3.

Return ONLY JSON. No prose, no markdown, no angle-bracket thoughts.
"""


def build_summary_user_prompt(
    allowed_labels: List[str],
    memory_block: str,
    subject: str,
    from_name: str,
    from_email: str,
    date: str,
    body_text: str,
    truncated: bool,
) -> str:
    schema_hint = (
        '{"version":2,"lang":"en","bullets":[],"key_actions":[],"urgency":0,'
        '"importance":0,"priority":0,"labels":[],"confidence":0,"truncated":false,'
        '"model":"deepseek-r1:32b","token_usage":{"prompt":0,"completion":0},"notes":""}'
    )
    mem = f"\nMEMORY:\n<<<\n{memory_block}\n>>>\n" if memory_block else ""
    trunc_line = "NOTE: The body text was clipped." if truncated else ""
    return (
        f"ALLOWED_LABELS: {allowed_labels}\n"
        f"{mem}"
        f"EMAIL:\n<<<\n"
        f"Subject: {subject}\n"
        f"From: {from_name} <{from_email}>\n"
        f"Date: {date}\n"
        f"Body:\n{body_text}\n"
        f">>>\n"
        f"{trunc_line}\n"
        f"Schema reminder: {schema_hint}"
    )


async def ping_models() -> tuple[bool, list[str], Optional[str]]:
    """
    Return (ok, model_names, error) for /api/llm/ping.
    """
    base = _get_ollama_base()
    timeout = _get_timeout()
    async with httpx.AsyncClient(timeout=timeout) as client:
        try:
            r = await client.get(f"{base}/api/tags")
            r.raise_for_status()
            data = r.json()
            models = [m.get("name", "") for m in data.get("models", []) if isinstance(m, dict)]
            return True, models, None
        except Exception as e:
            return False, [], f"Ollama ping failed: {e}"

