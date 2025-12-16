"""Soft tests for LLM gateway - validates style rules (may flake)."""

import re

import pytest

from conftest import call_generate

# Finnish bad openers that indicate meta-text or explanations
BAD_OPENERS = [
    "tässä",
    "tässä on",
    "alla",
    "seuraavassa",
    "tietysti",
    "varmasti",
    "katsaus",
    "kirjoitan",
    "teen",
]


def sentence_count(text: str) -> int:
    """Count sentences (rough: split by .!? and count non-empty parts)."""
    parts = re.split(r"[.!?]+", text.strip())
    parts = [p.strip() for p in parts if p.strip()]
    return len(parts)


@pytest.mark.parametrize("case_name", ["feed_simple", "chat_snarky", "feed_rumor", "chat_friendly"])
@pytest.mark.xfail(reason="Soft test - LLM may occasionally exceed 2 sentences", strict=False)
def test_max_two_sentences_feed_chat(case_name, client, gateway_url, prompt_cases):
    """Test that FEED/CHAT posts have max 2 sentences (soft test)."""
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
    sc = sentence_count(post["text"])

    assert sc <= 2, f"Too many sentences ({sc}): {post['text']}"


@pytest.mark.parametrize("case_name", ["feed_simple", "chat_snarky", "feed_rumor"])
def test_no_bad_openers(case_name, client, gateway_url, prompt_cases):
    """Test that posts don't start with meta-text openers (soft test)."""
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
    lower = post["text"].strip().lower()

    for opener in BAD_OPENERS:
        assert not lower.startswith(opener), f"Bad opener '{opener}' in: {post['text']}"


@pytest.mark.parametrize("case_name", ["feed_simple", "chat_snarky"])
def test_no_newlines_in_feed_chat(case_name, client, gateway_url, prompt_cases):
    """Test that FEED/CHAT posts don't contain newlines (soft test)."""
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

    assert "\n" not in post["text"], f"Newline found in text: {post['text']}"


def test_news_can_be_longer(client, gateway_url, prompt_cases):
    """Test that NEWS channel allows up to 4 sentences."""
    case = next(x for x in prompt_cases if x["name"] == "news_verified")

    payload = {
        "prompt": case["prompt"],
        "channel": case["channel"],
        "author_id": case["author_id"],
        "source_event_id": case["source_event_id"],
        "context": {"lang": "fi", "test": True},
        "temperature": 0.5,
    }

    post = call_generate(client, gateway_url, payload)
    sc = sentence_count(post["text"])

    # NEWS can be 1-4 sentences
    assert 1 <= sc <= 4, f"NEWS sentence count out of range ({sc}): {post['text']}"


@pytest.mark.parametrize("case_name", ["feed_simple", "chat_snarky"])
def test_text_is_finnish(case_name, client, gateway_url, prompt_cases):
    """Basic check that text contains Finnish characters/patterns."""
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
    text = post["text"].lower()

    # Very basic Finnish indicator: contains ä, ö, or common Finnish words
    finnish_indicators = ["ä", "ö", "ja", "on", "ei", "että", "mutta", "niin", "oli", "kun"]
    has_finnish = any(ind in text for ind in finnish_indicators)

    assert has_finnish, f"Text doesn't appear to be Finnish: {post['text']}"
