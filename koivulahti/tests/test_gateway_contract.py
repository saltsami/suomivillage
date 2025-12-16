"""Contract tests for LLM gateway - validates schema compliance and const locks."""

import pytest

from conftest import call_generate

MAX_BY_CHANNEL = {"FEED": 280, "CHAT": 220, "NEWS": 480}
REQUIRED_KEYS = ["channel", "author_id", "source_event_id", "tone", "text", "tags"]
VALID_TONES = ["friendly", "neutral", "defensive", "snarky", "concerned", "formal", "hyped"]


@pytest.mark.parametrize(
    "case_name",
    ["feed_simple", "chat_snarky", "news_verified", "feed_rumor", "chat_friendly", "feed_event"],
)
def test_generate_returns_required_keys(case_name, client, gateway_url, prompt_cases):
    """Test that /generate returns all required keys."""
    case = next(x for x in prompt_cases if x["name"] == case_name)

    payload = {
        "prompt": case["prompt"],
        "channel": case["channel"],
        "author_id": case["author_id"],
        "source_event_id": case["source_event_id"],
        "context": {"lang": "fi", "test": True},
        "temperature": 0.5,
    }

    post = call_generate(client, gateway_url, payload)

    for key in REQUIRED_KEYS:
        assert key in post, f"Missing required key: {key}"


@pytest.mark.parametrize(
    "case_name",
    ["feed_simple", "chat_snarky", "news_verified", "feed_rumor"],
)
def test_const_locks_respected(case_name, client, gateway_url, prompt_cases):
    """Test that channel, author_id, source_event_id are locked to request values."""
    case = next(x for x in prompt_cases if x["name"] == case_name)

    payload = {
        "prompt": case["prompt"],
        "channel": case["channel"],
        "author_id": case["author_id"],
        "source_event_id": case["source_event_id"],
        "context": {"lang": "fi", "test": True},
        "temperature": 0.5,
    }

    post = call_generate(client, gateway_url, payload)

    assert post["channel"] == case["channel"], f"Channel mismatch: {post['channel']} != {case['channel']}"
    assert post["author_id"] == case["author_id"], f"Author mismatch: {post['author_id']} != {case['author_id']}"
    assert post["source_event_id"] == case["source_event_id"], f"Event ID mismatch"


@pytest.mark.parametrize("case_name", ["feed_simple", "chat_snarky", "news_verified"])
def test_text_length_within_channel_limit(case_name, client, gateway_url, prompt_cases):
    """Test that text length respects channel-specific limits."""
    case = next(x for x in prompt_cases if x["name"] == case_name)

    payload = {
        "prompt": case["prompt"],
        "channel": case["channel"],
        "author_id": case["author_id"],
        "source_event_id": case["source_event_id"],
        "context": {"lang": "fi", "test": True},
        "temperature": 0.5,
    }

    post = call_generate(client, gateway_url, payload)
    max_len = MAX_BY_CHANNEL[case["channel"]]

    assert len(post["text"]) <= max_len, f"Text too long ({len(post['text'])} > {max_len}): {post['text'][:100]}..."


@pytest.mark.parametrize("case_name", ["feed_simple", "chat_snarky"])
def test_tags_constraints(case_name, client, gateway_url, prompt_cases):
    """Test that tags is a list with 1-5 items."""
    case = next(x for x in prompt_cases if x["name"] == case_name)

    payload = {
        "prompt": case["prompt"],
        "channel": case["channel"],
        "author_id": case["author_id"],
        "source_event_id": case["source_event_id"],
        "context": {"lang": "fi", "test": True},
        "temperature": 0.5,
    }

    post = call_generate(client, gateway_url, payload)

    assert isinstance(post["tags"], list), f"Tags is not a list: {type(post['tags'])}"
    assert 1 <= len(post["tags"]) <= 5, f"Tags count out of range: {len(post['tags'])}"


@pytest.mark.parametrize("case_name", ["feed_simple", "chat_snarky"])
def test_tone_is_valid(case_name, client, gateway_url, prompt_cases):
    """Test that tone is one of the valid values."""
    case = next(x for x in prompt_cases if x["name"] == case_name)

    payload = {
        "prompt": case["prompt"],
        "channel": case["channel"],
        "author_id": case["author_id"],
        "source_event_id": case["source_event_id"],
        "context": {"lang": "fi", "test": True},
        "temperature": 0.5,
    }

    post = call_generate(client, gateway_url, payload)

    assert post["tone"] in VALID_TONES, f"Invalid tone: {post['tone']}"
