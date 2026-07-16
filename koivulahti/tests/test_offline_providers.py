"""Offline tests for deterministic and external-provider adapters."""

import asyncio
import json

import httpx
import pytest

from packages.shared.gemini_client import GeminiClient
from services.llm_gateway.app.main import GenerateRequest, generate_fake_response


@pytest.mark.parametrize("channel", ["FEED", "CHAT", "NEWS"])
def test_fake_provider_is_deterministic_and_contract_safe(channel: str) -> None:
    request = GenerateRequest(
        prompt="Testitilanne",
        channel=channel,
        author_id="npc_sanni",
        source_event_id="evt_001",
    )

    first = generate_fake_response(request)
    second = generate_fake_response(request)

    assert first == second
    assert first.channel == channel
    assert first.author_id == "npc_sanni"
    assert first.source_event_id == "evt_001"
    assert first.text
    assert 1 <= len(first.tags) <= 5
    assert first.safety_notes == "fake_provider"


def test_gemini_key_is_sent_in_header_not_url() -> None:
    api_key = "test-key-not-a-secret"

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params.get("key") is None
        assert api_key not in str(request.url)
        assert request.headers["x-goog-api-key"] == api_key
        assert request.url.path.endswith("/models/gemini-test:generateContent")
        content = json.dumps(
            {
                "action": "IGNORE",
                "intent": "neutral",
                "emotion": "neutral",
                "draft": "",
                "reasoning": "test",
                "confidence": 1.0,
            }
        )
        return httpx.Response(
            200,
            json={"candidates": [{"content": {"parts": [{"text": content}]}}]},
        )

    async def run() -> None:
        client = GeminiClient(
            api_key=api_key,
            model="gemini-test",
            transport=httpx.MockTransport(handler),
        )
        try:
            result = await client.generate("test")
        finally:
            await client.close()
        assert result["action"] == "IGNORE"

    asyncio.run(run())
