"""Pytest configuration and shared fixtures for LLM gateway tests."""

import json
import os
from pathlib import Path

import httpx
import pytest

GATEWAY_URL = os.getenv("LLM_GATEWAY_URL", "http://localhost:8081")


@pytest.fixture(scope="session")
def gateway_url() -> str:
    return GATEWAY_URL


@pytest.fixture(scope="session")
def client():
    with httpx.Client(timeout=75) as c:
        yield c


@pytest.fixture(scope="session")
def prompt_cases() -> list[dict]:
    path = Path(__file__).parent / "prompts_fi.json"
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def call_generate(client: httpx.Client, gateway_url: str, payload: dict) -> dict:
    """Call the /generate endpoint and return parsed JSON response."""
    r = client.post(f"{gateway_url}/generate", json=payload)
    r.raise_for_status()
    return r.json()
