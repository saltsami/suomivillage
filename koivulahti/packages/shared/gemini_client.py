"""Gemini 2.0 Flash API client for Decision Service."""

import json
import os
from typing import Any, Dict, Optional

import httpx

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = "gemini-2.0-flash-exp"
GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta"

# Default generation config
DEFAULT_CONFIG = {
    "temperature": 0.2,
    "topP": 0.8,
    "topK": 40,
    "maxOutputTokens": 512,
    "responseMimeType": "application/json",
}


class GeminiClient:
    """Async client for Gemini 2.0 Flash API."""

    def __init__(self, api_key: Optional[str] = None, timeout: float = 30.0):
        self.api_key = api_key or GEMINI_API_KEY
        self.timeout = timeout
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=self.timeout)
        return self._client

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def generate(
        self,
        prompt: str,
        system_instruction: Optional[str] = None,
        json_schema: Optional[Dict[str, Any]] = None,
        temperature: float = 0.2,
        max_retries: int = 3,
    ) -> Dict[str, Any]:
        """
        Generate a response from Gemini 2.0 Flash.

        Args:
            prompt: The user prompt
            system_instruction: Optional system instruction
            json_schema: Optional JSON schema for structured output
            temperature: Sampling temperature (0-1)
            max_retries: Number of retries on failure

        Returns:
            Parsed JSON response from the model
        """
        if not self.api_key:
            raise ValueError("GEMINI_API_KEY not set")

        client = await self._get_client()
        url = f"{GEMINI_BASE_URL}/models/{GEMINI_MODEL}:generateContent?key={self.api_key}"

        # Build request body
        contents = [{"role": "user", "parts": [{"text": prompt}]}]

        generation_config = {
            **DEFAULT_CONFIG,
            "temperature": temperature,
        }

        # Add JSON schema if provided
        if json_schema:
            generation_config["responseSchema"] = json_schema

        body: Dict[str, Any] = {
            "contents": contents,
            "generationConfig": generation_config,
        }

        # Add system instruction if provided
        if system_instruction:
            body["systemInstruction"] = {
                "parts": [{"text": system_instruction}]
            }

        # Retry loop
        last_error: Optional[Exception] = None
        for attempt in range(max_retries):
            try:
                response = await client.post(url, json=body)
                response.raise_for_status()

                data = response.json()

                # Extract text from response
                candidates = data.get("candidates", [])
                if not candidates:
                    raise ValueError("No candidates in response")

                content = candidates[0].get("content", {})
                parts = content.get("parts", [])
                if not parts:
                    raise ValueError("No parts in response")

                text = parts[0].get("text", "")

                # Parse JSON response
                try:
                    return json.loads(text)
                except json.JSONDecodeError:
                    # Try to extract JSON from text
                    import re
                    match = re.search(r"\{.*\}", text, re.DOTALL)
                    if match:
                        return json.loads(match.group(0))
                    raise ValueError(f"Could not parse JSON from response: {text[:200]}")

            except httpx.HTTPStatusError as e:
                last_error = e
                if e.response.status_code == 429:
                    # Rate limited, wait and retry
                    import asyncio
                    await asyncio.sleep(2 ** attempt)
                    continue
                elif e.response.status_code >= 500:
                    # Server error, retry
                    import asyncio
                    await asyncio.sleep(1)
                    continue
                else:
                    raise

            except (httpx.RequestError, ValueError) as e:
                last_error = e
                import asyncio
                await asyncio.sleep(1)
                continue

        raise last_error or RuntimeError("Max retries exceeded")


# JSON schema for decision output
DECISION_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "action": {
            "type": "string",
            "enum": ["IGNORE", "POST_FEED", "POST_CHAT", "REPLY"],
            "description": "What action the NPC takes"
        },
        "intent": {
            "type": "string",
            "enum": ["spread_info", "agree", "disagree", "joke", "worry", "practical", "emotional", "question", "neutral"],
            "description": "The intent behind the action"
        },
        "emotion": {
            "type": "string",
            "enum": ["curious", "happy", "annoyed", "worried", "neutral", "amused", "proud", "sad"],
            "description": "The NPC's emotional state"
        },
        "draft": {
            "type": "string",
            "description": "Short English draft of what they want to say (1-2 sentences)"
        },
        "reasoning": {
            "type": "string",
            "description": "Brief explanation of why this action makes sense"
        },
        "confidence": {
            "type": "number",
            "minimum": 0,
            "maximum": 1,
            "description": "How confident the NPC is in this decision"
        }
    },
    "required": ["action", "intent", "emotion", "draft", "reasoning", "confidence"]
}


# Singleton client
_client: Optional[GeminiClient] = None


def get_gemini_client() -> GeminiClient:
    """Get or create singleton Gemini client."""
    global _client
    if _client is None:
        _client = GeminiClient()
    return _client


async def generate_decision(
    prompt: str,
    system_instruction: str,
    temperature: float = 0.2,
) -> Dict[str, Any]:
    """
    Convenience function to generate a decision.

    Returns dict with: action, intent, emotion, draft, reasoning, confidence
    """
    client = get_gemini_client()
    return await client.generate(
        prompt=prompt,
        system_instruction=system_instruction,
        json_schema=DECISION_OUTPUT_SCHEMA,
        temperature=temperature,
    )
