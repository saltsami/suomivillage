import json
import re
from typing import Any, Dict, Optional, Tuple

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from packages.shared.settings import Settings

settings = Settings()
client = httpx.AsyncClient(timeout=60.0)
app = FastAPI(title="Koivulahti LLM Gateway", version="0.1.0")

# Channel-specific character limits
MAX_CHARS_BY_CHANNEL = {"FEED": 280, "CHAT": 220, "NEWS": 480}
TONES = ["friendly", "neutral", "defensive", "snarky", "concerned", "formal", "hyped"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

SYSTEM_JSON_INSTRUCTION = (
    "Vastaa VAIN valid JSON-objektina.\n\n"
    "EHDOTTOMAT SÄÄNNÖT:\n"
    "- FEED/CHAT: Kirjoita AINA 1. persoonassa (minä/mä/oon) - kuin kirjoittaisit omaan someesi\n"
    "- NEWS: Neutraali 3. persoona, uutistyyli\n"
    "- Max 2 lyhyttä lausetta, ei rivinvaihtoja\n"
    "- Ei meta-puhetta: 'Kuvittele', 'Tilannekuva', 'Taustaksi', 'Seuraamme'\n"
    "- Ei johdantoja: 'Tässä on', 'Kirjoitan', 'Haluan kertoa'\n"
    "- Ei kolmatta persoonaa itsestä (jos olet Kaisa, ÄLÄ kirjoita 'Kaisa meni')\n"
    "- Ei emojitulvaa (max 1 emoji)\n"
    "- Suora, arkinen suomi - kuin tekstiviesti kaverille\n\n"
    "ESIMERKKEJÄ (FEED/CHAT):\n"
    "✓ 'Kävin kahviolla. Tilaukset meni taas sekaisin mut ei se mitään.'\n"
    "✓ 'Saunassa oli hyvä fiilis. Nähään illalla!'\n"
    "✓ 'Pajalla taas. Asiakkaita riittää tänään.'\n"
    "✗ 'Kuvittele tilanne jossa Kaisa menee kahviolle...' (meta-puhetta)\n"
    "✗ 'Tilannekuva: Saunassa oli hieno tunnelma.' (kertoja-tyyli)\n"
    "✗ 'Kaisa kävi saunassa ja nautti.' (3. persoona itsestä)\n\n"
    "JSON-kentät:\n"
    "- channel, author_id, source_event_id: annetut arvot\n"
    "- tone: friendly/neutral/defensive/snarky/concerned/formal/hyped\n"
    "- text: postaus suomeksi (FEED max 280, CHAT max 220, NEWS max 480)\n"
    "- tags: 1-3 asiasanaa\n"
    "- safety_notes: null"
)

# Banned phrases that indicate narrator/meta style
BANNED_PHRASES = [
    "kuvittele", "tilannekuva", "taustaksi", "seuraamme", "tässä on",
    "kirjoitan", "haluan kertoa", "kertomuksessa", "tarinassa", "novellissa",
    "päähenkilö", "hahmo tekee", "tilanne jossa",
]


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


def build_json_schema(req: GenerateRequest) -> Dict[str, Any]:
    """Build JSON schema with locked values and channel-specific limits."""
    max_len = MAX_CHARS_BY_CHANNEL.get(req.channel, 280)
    return {
        "type": "object",
        "properties": {
            "channel": {"type": "string", "const": req.channel},
            "author_id": {"type": "string", "const": req.author_id},
            "source_event_id": {"type": "string", "const": req.source_event_id},
            "tone": {"type": "string", "enum": TONES},
            "text": {"type": "string", "minLength": 1, "maxLength": max_len},
            "tags": {
                "type": "array",
                "items": {"type": "string"},
                "minItems": 1,
                "maxItems": 5,
            },
            "safety_notes": {"type": ["string", "null"]},
        },
        "required": ["channel", "author_id", "source_event_id", "tone", "text", "tags"],
        "additionalProperties": False,
    }


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
    """Call llama.cpp with 3-level fallback for JSON schema support."""
    base = settings.llm_server_url.rstrip("/")
    schema = build_json_schema(request)

    # Base payload for chat completions
    payload: Dict[str, Any] = {
        "model": "local-model",
        "messages": messages,
        "temperature": temperature,
        "max_tokens": settings.llm_max_tokens,
        "stream": False,
    }

    # Level 1: Try json_schema mode (strictest)
    payload["response_format"] = {"type": "json_schema", "schema": schema}
    try:
        resp = await client.post(f"{base}/v1/chat/completions", json=payload)
        if resp.status_code == 200:
            return resp.json(), "chat_json_schema"

        # Level 2: Try json_object + schema (alternative format)
        if resp.status_code == 400:
            payload["response_format"] = {"type": "json_object", "schema": schema}
            resp = await client.post(f"{base}/v1/chat/completions", json=payload)
            if resp.status_code == 200:
                return resp.json(), "chat_json_object_schema"

            # Level 3: Try plain json_object (no schema constraint)
            if resp.status_code == 400:
                payload["response_format"] = {"type": "json_object"}
                resp = await client.post(f"{base}/v1/chat/completions", json=payload)
                if resp.status_code == 200:
                    return resp.json(), "chat_json_object"

        resp.raise_for_status()
        return resp.json(), "chat"
    except Exception as e:
        print(f"[llm-gateway] Chat completions failed: {e}")

    # Fallback: OpenAI-compatible /v1/completions endpoint
    full_prompt = merge_system_into_user(messages)[0]["content"]
    completion_payload = {
        "model": "local-model",
        "prompt": full_prompt,
        "temperature": temperature,
        "max_tokens": settings.llm_max_tokens,
        "stream": False,
    }
    try:
        resp = await client.post(f"{base}/v1/completions", json=completion_payload)
        resp.raise_for_status()
        return resp.json(), "v1_completions"
    except Exception as e:
        print(f"[llm-gateway] v1/completions failed: {e}")

    # Final fallback: legacy llama.cpp /completion endpoint
    legacy_payload = {
        "prompt": full_prompt,
        "temperature": temperature,
        "n_predict": settings.llm_max_tokens,
        "stream": False,
    }
    resp = await client.post(f"{base}/completion", json=legacy_payload)
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


def has_banned_phrases(text: str) -> bool:
    """Check if text contains banned narrator/meta phrases."""
    text_lower = text.lower()
    return any(phrase in text_lower for phrase in BANNED_PHRASES)


def has_third_person_self(text: str, author_id: str) -> bool:
    """Check if author refers to themselves in 3rd person."""
    # Extract name from author_id (e.g., npc_kaisa -> Kaisa)
    name = author_id.replace("npc_", "").replace("NPC_", "").capitalize()
    # Check if name appears as a subject (followed by verb-like patterns)
    patterns = [
        f"{name} meni", f"{name} oli", f"{name} kävi", f"{name} teki",
        f"{name} sanoi", f"{name} ajatteli", f"{name} tunsi",
    ]
    text_lower = text.lower()
    name_lower = name.lower()
    return any(p.lower() in text_lower for p in patterns) or f"{name_lower} " in text_lower[:50]


def normalize_response(raw: Dict[str, Any], request: GenerateRequest, fallback_text: str) -> GenerateResponse:
    # Always use request values for locked fields (LLM schema const not reliable)
    channel = request.channel
    author_id = request.author_id
    source_event_id = request.source_event_id
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

    # Repair loop: if JSON parsing failed, try to fix it with a second LLM call
    if not raw_json and raw_text:
        print(f"[llm-gateway] JSON parse failed, attempting repair (mode={mode})")
        repair_prompt = (
            "Korjaa seuraava mallitulos VALIDIKSI JSON-OBJEKTIKSI. "
            "Älä lisää mitään muuta, vain korjattu JSON.\n\n"
            f"TARGET: channel={request.channel}, author_id={request.author_id}, "
            f"source_event_id={request.source_event_id}\n\n"
            f"BROKEN OUTPUT:\n{raw_text[:1000]}"
        )
        repair_messages = [
            {"role": "system", "content": SYSTEM_JSON_INSTRUCTION},
            {"role": "user", "content": repair_prompt},
        ]
        try:
            llama_data2, mode2 = await call_llama_cpp(
                request, min(0.3, temperature), repair_messages
            )
            raw_text2 = extract_text(llama_data2)
            raw_json = extract_json(raw_text2)
            if raw_json:
                print(f"[llm-gateway] Repair successful (mode={mode2})")
                return normalize_response(raw_json, request, raw_text2)
        except Exception as e:
            print(f"[llm-gateway] Repair attempt failed: {e}")

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
        response = normalize_response(raw_json, request, raw_text)
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

    # Quality check: polish if banned phrases or third-person-self detected
    needs_polish = False
    if request.channel in ("FEED", "CHAT"):
        if has_banned_phrases(response.text):
            print(f"[llm-gateway] Banned phrase detected, polishing")
            needs_polish = True
        elif has_third_person_self(response.text, request.author_id):
            print(f"[llm-gateway] Third-person-self detected, polishing")
            needs_polish = True

    if needs_polish:
        polish_prompt = (
            f"Korjaa tämä teksti. Kirjoita 1. persoonassa (minä/mä), "
            f"max 2 lausetta, arkinen suomi, ei meta-puhetta.\n\n"
            f"ALKUPERÄINEN: {response.text}\n\n"
            f"KORJATTU (vain teksti, ei JSON):"
        )
        polish_messages = [{"role": "user", "content": polish_prompt}]
        try:
            polish_data, _ = await call_llama_cpp(request, 0.2, polish_messages)
            polished_text = extract_text(polish_data).strip()
            # Clean up: remove quotes if LLM wrapped it
            polished_text = polished_text.strip('"\'')
            if polished_text and len(polished_text) < 300 and not has_banned_phrases(polished_text):
                response.text = polished_text
                print(f"[llm-gateway] Polish successful")
        except Exception as e:
            print(f"[llm-gateway] Polish failed: {e}")

    return response
