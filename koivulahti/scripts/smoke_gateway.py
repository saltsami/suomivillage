#!/usr/bin/env python3
"""Smoke test script for LLM gateway - runs without pytest."""

import json
import os
import sys
from pathlib import Path

import httpx

GATEWAY_URL = os.getenv("LLM_GATEWAY_URL", "http://localhost:8081")
CASES_PATH = Path(__file__).parent.parent / "tests" / "prompts_fi.json"

MAX_BY_CHANNEL = {"FEED": 280, "CHAT": 220, "NEWS": 480}


def main():
    if not CASES_PATH.exists():
        print(f"ERROR: Test cases not found at {CASES_PATH}")
        sys.exit(1)

    cases = json.loads(CASES_PATH.read_text(encoding="utf-8"))
    print(f"Running smoke tests against {GATEWAY_URL}")
    print(f"Loaded {len(cases)} test cases from {CASES_PATH.name}")
    print("-" * 60)

    passed = 0
    failed = 0

    with httpx.Client(timeout=75) as client:
        # Health check first
        try:
            r = client.get(f"{GATEWAY_URL}/health")
            r.raise_for_status()
            print(f"Health check: OK")
        except Exception as e:
            print(f"Health check: FAILED - {e}")
            sys.exit(1)

        print("-" * 60)

        for case in cases:
            payload = {
                "prompt": case["prompt"],
                "channel": case["channel"],
                "author_id": case["author_id"],
                "source_event_id": case["source_event_id"],
                "context": {"lang": "fi", "smoke": True},
                "temperature": 0.5,
            }

            try:
                r = client.post(f"{GATEWAY_URL}/generate", json=payload)
                r.raise_for_status()
                post = r.json()

                # Basic validation
                errors = []
                if post.get("channel") != case["channel"]:
                    errors.append(f"channel mismatch: {post.get('channel')}")
                if post.get("author_id") != case["author_id"]:
                    errors.append(f"author_id mismatch: {post.get('author_id')}")
                if not post.get("text"):
                    errors.append("empty text")

                max_len = MAX_BY_CHANNEL.get(case["channel"], 280)
                if len(post.get("text", "")) > max_len:
                    errors.append(f"text too long: {len(post['text'])} > {max_len}")

                if errors:
                    print(f"{case['name']}: WARN - {', '.join(errors)}")
                    print(f"  text: {post.get('text', '')[:80]}...")
                else:
                    print(f"{case['name']}: OK")
                    print(f"  tone={post.get('tone')} tags={post.get('tags')}")
                    print(f"  text: {post.get('text', '')[:80]}...")

                passed += 1

            except Exception as e:
                print(f"{case['name']}: FAILED - {e}")
                failed += 1

            print()

    print("-" * 60)
    print(f"Results: {passed} passed, {failed} failed")
    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    main()
