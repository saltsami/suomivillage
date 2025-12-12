from typing import Any, Dict, Optional

import httpx
from fastapi import FastAPI
from pydantic import BaseModel, Field

from packages.shared.settings import Settings

settings = Settings()
client = httpx.AsyncClient(timeout=30.0)
app = FastAPI(title="Koivulahti LLM Gateway", version="0.1.0")


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


@app.post("/generate", response_model=GenerateResponse)
async def generate(request: GenerateRequest) -> GenerateResponse:
    # Placeholder adapter: echoes deterministic JSON instead of calling a real model.
    tone = "neutral"
    text = f"[stub] channel={request.channel} event={request.source_event_id} prompt={request.prompt[:80]}"
    return GenerateResponse(
        channel=request.channel,
        author_id=request.author_id,
        source_event_id=request.source_event_id,
        tone=tone,
        text=text,
        tags=["stub"],
    )
