import json
import re
from typing import Any, Dict, Optional, Tuple

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from packages.shared.settings import Settings

settings = Settings()
client = httpx.AsyncClient(timeout=30.0)
app = FastAPI(title="Koivulahti LLM Gateway", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

SYSTEM_JSON_INSTRUCTION = (
    "Vastaa VAIN valid JSON-objektina ilman ylimääräistä tekstiä, selityksiä tai Markdown-koodia.\n\n"
    "Vaaditut JSON-kentät:\n"
    "- channel: kanavän nimi (FEED/CHAT/NEWS)\n"
    "- author_id: kirjoittajan ID\n"
    "- source_event_id: tapahtuman ID\n"
    "- tone: sävy, yksi näistä: friendly, neutral, defensive, snarky, concerned, formal, hyped\n"
    "- text: varsinainen tekstisisältö suomeksi (max 280 merkkiä FEED, 220 CHAT, 480 NEWS)\n"
    "- tags: lista 1-5 lyhyttä asiasanaa suomeksi\n"
    "- safety_notes: null tai huomio ongelmallisesta sisällöstä\n\n"
    "Kirjoita text-kenttään VAIN itse postaus/viesti/uutinen - ei metatietoja tai selityksiä."
)


class GenerateRequest(BaseModel):
    prompt: str
    channel: str
    author_id: str
    source_event_id: str
    context: Dict[str, Any] = Field(default_factory=dict)
    temperature: Optional[float] = None


class GenerateResponse(BaseModel):
    channel: str
    author_id: str
    source_event_id: str
    tone: str
    text: str
    tags: list[str] = Field(default_factory=list)
    safety_notes: Optional[str] = None


@app.on_event("shutdown")
async def shutdown_client() -> None:
    await client.aclose()


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "env": settings.env}


def build_messages(request: GenerateRequest) -> list[dict[str, str]]:
    return [
        {"role": "system", "content": SYSTEM_JSON_INSTRUCTION},
        {"role": "user", "content": request.prompt},
    ]


def merge_system_into_user(messages: list[dict[str, str]]) -> list[dict[str, str]]:
    parts: list[str] = []
    for message in messages:
        role = message.get("role")
        content = message.get("content")
        if role in {"system", "user"} and content:
            parts.append(str(content))
    merged = "\n\n".join(parts).strip()
    return [{"role": "user", "content": merged}]


async def call_llama_cpp(
    request: GenerateRequest, temperature: float, messages: list[dict[str, str]]
) -> Tuple[Dict[str, Any], str]:
    base = settings.llm_server_url.rstrip("/")

    # Define JSON schema to constrain output format
    json_schema = {
        "type": "object",
        "properties": {
            "channel": {"type": "string"},
            "author_id": {"type": "string"},
            "source_event_id": {"type": "string"},
            "tone": {
                "type": "string",
                "enum": ["friendly", "neutral", "defensive", "snarky", "concerned", "formal", "hyped"]
            },
            "text": {"type": "string", "maxLength": 400},
            "tags": {"type": "array", "items": {"type": "string"}, "maxItems": 5},
            "safety_notes": {"type": ["string", "null"]}
        },
        "required": ["channel", "author_id", "source_event_id", "tone", "text", "tags"],
        "additionalProperties": False
    }

    # Try chat completions with JSON schema first (Qwen2.5 supports this)
    payload: Dict[str, Any] = {
        "model": "local-model",
        "messages": messages,
        "temperature": temperature,
        "max_tokens": settings.llm_max_tokens,
        "stream": False,
        "response_format": {
            "type": "json_object",
            "schema": json_schema
        }
    }

    try:
        resp = await client.post(f"{base}/v1/chat/completions", json=payload)
        if resp.status_code == 400:
            err_text = resp.text or ""
            # Fallback: try without schema if not supported
            if "schema" in err_text.lower() or "not supported" in err_text.lower():
                payload["response_format"] = {"type": "json_object"}
                resp = await client.post(f"{base}/v1/chat/completions", json=payload)
        resp.raise_for_status()
        return resp.json(), "chat"
    except Exception:
        # Final fallback: completion mode without schema
        full_prompt = merge_system_into_user(messages)[0]["content"]
        completion_payload = {
            "prompt": full_prompt,
            "temperature": temperature,
            "n_predict": settings.llm_max_tokens,
            "stream": False,
        }
        resp = await client.post(f"{base}/completion", json=completion_payload)
        resp.raise_for_status()
        return resp.json(), "completion"


def extract_text(llama_data: Dict[str, Any]) -> str:
    choices = llama_data.get("choices")
    if isinstance(choices, list) and choices:
        first = choices[0] or {}
        if isinstance(first, dict):
            message = first.get("message")
            if isinstance(message, dict) and "content" in message:
                return str(message.get("content") or "")
            if "text" in first:
                return str(first.get("text") or "")
    if "content" in llama_data:
        return str(llama_data.get("content") or "")
    if "completion" in llama_data:
        return str(llama_data.get("completion") or "")
    return ""


def extract_json(text: str) -> Dict[str, Any] | None:
    candidate = text.strip()
    if not candidate:
        return None
    try:
        parsed = json.loads(candidate)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass
    match = re.search(r"\{.*\}", candidate, re.DOTALL)
    if not match:
        return None
    try:
        parsed = json.loads(match.group(0))
        return parsed if isinstance(parsed, dict) else None
    except json.JSONDecodeError:
        return None


def normalize_response(raw: Dict[str, Any], request: GenerateRequest, fallback_text: str) -> GenerateResponse:
    channel = str(raw.get("channel") or request.channel)
    author_id = str(raw.get("author_id") or request.author_id)
    source_event_id = str(raw.get("source_event_id") or request.source_event_id)
    tone = str(raw.get("tone") or "neutral")
    text = str(raw.get("text") or fallback_text or "")

    tags_val = raw.get("tags") or []
    tags: list[str]
    if isinstance(tags_val, str):
        try:
            parsed = json.loads(tags_val)
            tags = [str(t) for t in parsed] if isinstance(parsed, list) else [tags_val]
        except json.JSONDecodeError:
            tags = [tags_val]
    elif isinstance(tags_val, list):
        tags = [str(t) for t in tags_val if t is not None]
    else:
        tags = []

    safety_notes_val = raw.get("safety_notes")
    safety_notes = str(safety_notes_val) if safety_notes_val is not None else None
    return GenerateResponse(
        channel=channel,
        author_id=author_id,
        source_event_id=source_event_id,
        tone=tone,
        text=text,
        tags=tags,
        safety_notes=safety_notes,
    )


@app.post("/generate", response_model=GenerateResponse)
async def generate(request: GenerateRequest) -> GenerateResponse:
    if settings.llm_provider != "llama_cpp":
        raise HTTPException(status_code=501, detail=f"Unsupported LLM_PROVIDER: {settings.llm_provider}")

    temperature = request.temperature if request.temperature is not None else settings.llm_temperature
    messages = build_messages(request)
    try:
        llama_data, mode = await call_llama_cpp(request, temperature, messages)
    except Exception as e:
        print(f"[llm-gateway] LLM call failed: {e}")
        raise HTTPException(status_code=502, detail="LLM server error")

    raw_text = extract_text(llama_data)
    raw_json = extract_json(raw_text)

    if not raw_json:
        return GenerateResponse(
            channel=request.channel,
            author_id=request.author_id,
            source_event_id=request.source_event_id,
            tone="neutral",
            text=raw_text or request.prompt[:200],
            tags=[],
            safety_notes=f"model_output_not_json (mode={mode})",
        )

    try:
        return normalize_response(raw_json, request, raw_text)
    except Exception as e:
        print(f"[llm-gateway] normalize failed: {e}")
        return GenerateResponse(
            channel=request.channel,
            author_id=request.author_id,
            source_event_id=request.source_event_id,
            tone=str(raw_json.get("tone") or "neutral"),
            text=str(raw_json.get("text") or raw_text or request.prompt[:200]),
            tags=[],
            safety_notes="schema_validation_failed",
        )
