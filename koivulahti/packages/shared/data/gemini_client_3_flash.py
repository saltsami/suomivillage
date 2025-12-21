import os
import json
import asyncio
from typing import Any, Dict, Optional

# New SDK import
from google import genai
from google.genai import types

# Configuration for Gemini 3 Flash
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "AIzaSyAC2Z7e3n-vNyw2GgtesTVhdY4fngfnmWQ")
GEMINI_MODEL = "gemini-3-flash-preview"

# Default generation parameters
DEFAULT_CONFIG = {
    "temperature": 0.2,
    "top_p": 0.8,
    "top_k": 40,
    "max_output_tokens": 1024,
    "response_mime_type": "application/json",
}

class GeminiClient:
    """Async client for Gemini 3 Flash API using google-genai SDK."""

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or GEMINI_API_KEY
        if not self.api_key:
            raise ValueError("GEMINI_API_KEY not set")
        
        # Initialize the synchronous client, access async via .aio
        self._client = genai.Client(api_key=self.api_key)

    async def close(self) -> None:
        # The new SDK manages connections efficiently, but we can explicitly close
        # the internal async http client if accessible/needed.
        # Currently, the SDK's .aio property manages its own lifecycle.
        pass

    async def generate(
        self,
        prompt: str,
        system_instruction: Optional[str] = None,
        json_schema: Optional[Dict[str, Any]] = None,
        temperature: float = 0.2,
        max_retries: int = 3,
    ) -> Dict[str, Any]:
        """
        Generate a response from Gemini 3 Flash.
        """
        
        # Build configuration object
        config_params = {
            **DEFAULT_CONFIG,
            "temperature": temperature,
        }
        
        # Add JSON schema if provided
        if json_schema:
            config_params["response_schema"] = json_schema

        # Add system instruction if provided
        if system_instruction:
            config_params["system_instruction"] = system_instruction

        config = types.GenerateContentConfig(**config_params)

        # Retry loop
        last_error: Optional[Exception] = None
        for attempt in range(max_retries):
            try:
                # Use .aio for async calls
                response = await self._client.aio.models.generate_content(
                    model=GEMINI_MODEL,
                    contents=prompt,
                    config=config
                )
                
                # Verify we have text output
                if not response.text:
                    raise ValueError("Empty response from model")

                # The SDK automatically handles JSON parsing if response_mime_type is JSON,
                # but depending on the exact SDK version, response.parsed might be available 
                # or we parse response.text manually.
                try:
                    # Try automatic parsing if supported/populated
                    if hasattr(response, 'parsed') and response.parsed:
                        return response.parsed
                    return json.loads(response.text)
                except json.JSONDecodeError:
                    # Fallback for minor formatting issues
                    import re
                    match = re.search(r"\{.*\}", response.text, re.DOTALL)
                    if match:
                        return json.loads(match.group(0))
                    raise ValueError(f"Could not parse JSON: {response.text[:200]}")

            except Exception as e:
                # The SDK raises specific GoogleGenAI errors, but we catch generic for safety
                last_error = e
                # Simple exponential backoff
                await asyncio.sleep(2 ** attempt)
                continue

        raise last_error or RuntimeError("Max retries exceeded")


# JSON schema for decision output
# (Unchanged, but ensures strict typing for the model)
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
            "description": "How confident the NPC is in this decision (0.0 to 1.0)"
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
    Convenience function to generate a decision using Gemini 3 Flash.
    """
    client = get_gemini_client()
    return await client.generate(
        prompt=prompt,
        system_instruction=system_instruction,
        json_schema=DECISION_OUTPUT_SCHEMA,
        temperature=temperature,
    )