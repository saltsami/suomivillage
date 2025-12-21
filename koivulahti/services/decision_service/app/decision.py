"""Decision module - calls LLM and validates results."""

import json
import time
from datetime import datetime
from typing import Any, Dict, Optional, Tuple
from uuid import uuid4

import asyncpg

from packages.shared.gemini_client import generate_decision, DECISION_OUTPUT_SCHEMA
from .prompts import DECISION_SYSTEM_PROMPT, build_decision_prompt


# Valid actions
VALID_ACTIONS = {"IGNORE", "POST_FEED", "POST_CHAT", "REPLY"}

# Valid intents
VALID_INTENTS = {"spread_info", "agree", "disagree", "joke", "worry", "practical", "emotional", "question", "neutral"}

# Valid emotions
VALID_EMOTIONS = {"curious", "happy", "annoyed", "worried", "neutral", "amused", "proud", "sad"}


def validate_decision(decision: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
    """
    Validate decision output from LLM.

    Returns:
        (is_valid, error_message)
    """
    action = decision.get("action")
    if action not in VALID_ACTIONS:
        return False, f"Invalid action: {action}"

    intent = decision.get("intent", "neutral")
    if intent not in VALID_INTENTS:
        decision["intent"] = "neutral"  # Fix invalid intent

    emotion = decision.get("emotion", "neutral")
    if emotion not in VALID_EMOTIONS:
        decision["emotion"] = "neutral"  # Fix invalid emotion

    # Confidence should be 0-1
    confidence = decision.get("confidence", 0.5)
    if not isinstance(confidence, (int, float)):
        decision["confidence"] = 0.5
    else:
        decision["confidence"] = max(0, min(1, confidence))

    # Draft should be string
    if not isinstance(decision.get("draft"), str):
        decision["draft"] = ""

    # Reasoning should be string
    if not isinstance(decision.get("reasoning"), str):
        decision["reasoning"] = ""

    return True, None


async def make_decision(
    context: Dict[str, Any],
    temperature: float = 0.2
) -> Dict[str, Any]:
    """
    Make a decision for an NPC given their context.

    Args:
        context: Full decision context (from build_decision_context)
        temperature: LLM temperature

    Returns:
        Decision dict with: action, intent, emotion, draft, reasoning, confidence
    """
    # Build prompt
    prompt = build_decision_prompt(context)

    # Call Gemini
    start_time = time.time()
    try:
        decision = await generate_decision(
            prompt=prompt,
            system_instruction=DECISION_SYSTEM_PROMPT,
            temperature=temperature
        )
    except Exception as e:
        # Fallback to IGNORE on error
        return {
            "action": "IGNORE",
            "intent": "neutral",
            "emotion": "neutral",
            "draft": "",
            "reasoning": f"Error: {str(e)}",
            "confidence": 0.0,
            "error": str(e),
            "latency_ms": int((time.time() - start_time) * 1000),
        }

    latency_ms = int((time.time() - start_time) * 1000)

    # Validate
    is_valid, error = validate_decision(decision)
    if not is_valid:
        decision = {
            "action": "IGNORE",
            "intent": "neutral",
            "emotion": "neutral",
            "draft": "",
            "reasoning": f"Validation error: {error}",
            "confidence": 0.0,
            "error": error,
        }

    decision["latency_ms"] = latency_ms
    return decision


async def log_decision(
    conn: asyncpg.Connection,
    job_id: str,
    npc_id: str,
    stimulus_event_id: Optional[str],
    stimulus_type: str,
    context: Dict[str, Any],
    llm_input: str,
    decision: Dict[str, Any],
    llm_provider: str = "gemini"
) -> None:
    """Log decision to database for audit."""
    await conn.execute(
        """
        INSERT INTO decisions (
            job_id, npc_id, stimulus_event_id, stimulus_type,
            context_snapshot, llm_input, llm_output,
            action, intent, emotion,
            latency_ms, llm_provider, error
        ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13)
        """,
        job_id,
        npc_id,
        stimulus_event_id,
        stimulus_type,
        json.dumps(context),
        json.dumps({"prompt": llm_input, "system": DECISION_SYSTEM_PROMPT[:200]}),
        json.dumps(decision),
        decision.get("action", "IGNORE"),
        decision.get("intent", "neutral"),
        decision.get("emotion", "neutral"),
        decision.get("latency_ms"),
        llm_provider,
        decision.get("error"),
    )


def decision_to_render_job(
    decision_job_id: str,
    npc_id: str,
    stimulus: Dict[str, Any],
    decision: Dict[str, Any]
) -> Optional[Dict[str, Any]]:
    """
    Convert a decision to a render job if action requires rendering.

    Returns:
        Render job dict or None if action is IGNORE
    """
    action = decision.get("action", "IGNORE")

    if action == "IGNORE":
        return None

    # Determine channel
    if action == "POST_FEED":
        channel = "FEED"
    elif action == "POST_CHAT":
        channel = "CHAT"
    elif action == "REPLY":
        channel = stimulus.get("channel", "CHAT")
    else:
        return None

    render_job = {
        "job_id": f"render_{uuid4().hex[:8]}",
        "decision_job_id": decision_job_id,
        "author_id": npc_id,
        "channel": channel,
        "source_event_id": stimulus.get("event_id", "unknown"),
        "decision": {
            "action": action,
            "intent": decision.get("intent", "neutral"),
            "emotion": decision.get("emotion", "neutral"),
            "draft": decision.get("draft", ""),
            "reasoning": decision.get("reasoning", ""),
            "confidence": decision.get("confidence", 0.5),
        },
    }

    # Add reply-specific fields
    if action == "REPLY":
        # Extract parent post info from stimulus
        payload = stimulus.get("payload", {})
        render_job["parent_post_id"] = payload.get("post_id")
        render_job["reply_type"] = decision.get("intent", "neutral")

    return render_job
