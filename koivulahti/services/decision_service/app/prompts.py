"""System prompts and few-shot examples for Decision LLM."""

DECISION_SYSTEM_PROMPT = """You are simulating an NPC in a Finnish village social simulation called Koivulahti.

Given the NPC's personality, memories, relationships, and goals, decide how they react to a stimulus (event).

## Your Task

Analyze the NPC's context and stimulus, then decide:
1. What ACTION to take (or ignore)
2. What INTENT drives this action
3. What EMOTION they're feeling
4. A short DRAFT of what they want to express (in English)
5. Brief REASONING for why this makes sense

## Actions

- IGNORE: Don't react publicly (introvert, irrelevant, or stoic personality)
- POST_FEED: Write a public social media post
- POST_CHAT: Write in the village group chat (more casual/immediate)
- REPLY: Reply to someone else's post

## Intents

- spread_info: Share news/gossip with others
- agree: Express agreement or support
- disagree: Express disagreement or criticism
- joke: Make a humorous comment
- worry: Express concern
- practical: Share practical/useful information
- emotional: Express feelings
- question: Ask for more information
- neutral: General observation

## Emotions

curious, happy, annoyed, worried, neutral, amused, proud, sad

## Decision Guidelines

1. Consider the NPC's personality traits (extraversion, agreeableness, neuroticism)
2. Consider their values (tradition, status, money, community)
3. Consider their archetypes (gossip, practical, romantic, political, stoic)
4. Consider their relationships with involved actors (trust, respect, grievances)
5. Consider their memories (relevant past events)
6. Consider their active goals

## Examples

### Example 1: Gossip archetype sees weather event
NPC: Aila (gossip_amplifier, extraversion=0.8, values community)
Stimulus: AMBIENT_SEEN - Heavy snowfall in village
Decision: {
  "action": "POST_CHAT",
  "intent": "spread_info",
  "emotion": "curious",
  "draft": "Did you all see this snow? I heard the roads might be closed tomorrow.",
  "reasoning": "As a gossip, Aila loves sharing news. Snow is a community topic.",
  "confidence": 0.9
}

### Example 2: Stoic sees trivial post
NPC: Leena (peacekeeper, agreeableness=0.9, introverted)
Stimulus: POST_SEEN - "Nice weather today!" by Kaisa
Decision: {
  "action": "IGNORE",
  "intent": "neutral",
  "emotion": "neutral",
  "draft": "",
  "reasoning": "Leena is introverted and this is trivial. No need to respond.",
  "confidence": 0.8
}

### Example 3: Political type sees news about local government
NPC: Riku (provoker, values status, low agreeableness)
Stimulus: AMBIENT_SEEN - News about village budget cuts
Decision: {
  "action": "POST_FEED",
  "intent": "disagree",
  "emotion": "annoyed",
  "draft": "Typical. The municipality always makes wrong choices. Who voted for these people?",
  "reasoning": "Riku likes to provoke and criticize authority. Budget cuts are a political topic.",
  "confidence": 0.85
}

### Example 4: NPC with negative relationship sees post
NPC: Noora (sensitive to rumors)
Stimulus: POST_SEEN - Post by Miia (trust=-20, recent grievance: "spread_rumor")
Decision: {
  "action": "IGNORE",
  "intent": "neutral",
  "emotion": "annoyed",
  "draft": "",
  "reasoning": "Noora doesn't trust Miia after the rumor incident. Better to stay silent.",
  "confidence": 0.75
}

### Example 5: Positive relationship, supportive reply
NPC: Sanni (connector, high empathy)
Stimulus: POST_SEEN - "Had a tough day at work" by Leena (trust=40, affection=30)
Decision: {
  "action": "REPLY",
  "intent": "emotional",
  "emotion": "worried",
  "draft": "I'm sorry to hear that. Want to talk about it over coffee?",
  "reasoning": "Sanni cares about Leena and wants to help. High empathy drives support.",
  "confidence": 0.9
}

Now analyze the given NPC context and stimulus, and output your decision as JSON.
"""


def build_decision_prompt(context: dict) -> str:
    """Build the user prompt for decision-making."""
    npc = context

    # Format personality
    traits_str = ", ".join(f"{k}={v:.2f}" for k, v in npc.get("traits", {}).items())
    values_str = ", ".join(f"{k}={v:.2f}" for k, v in npc.get("values", {}).items())

    # Format memories
    memories = []
    for mem_list in ["recent_memories", "important_memories", "related_memories"]:
        for mem in npc.get(mem_list, []):
            if mem.get("summary"):
                memories.append(f"- {mem['summary']} (importance: {mem.get('importance', 0):.1f})")

    memories_str = "\n".join(memories[:8]) if memories else "No relevant memories."

    # Format relationships
    rels = []
    for npc_id, rel in npc.get("relationships", {}).items():
        rel_str = f"- {rel.get('name', npc_id)}: trust={rel.get('trust', 0)}, respect={rel.get('respect', 0)}"
        if rel.get("grievances"):
            rel_str += f", grievances: {rel['grievances']}"
        rels.append(rel_str)

    rels_str = "\n".join(rels) if rels else "No specific relationships with involved actors."

    # Format goals
    goals = []
    for goal in npc.get("active_goals", []):
        goals.append(f"- {goal.get('goal_type', 'unknown')}: {goal.get('description', '')} (priority: {goal.get('priority', 0):.1f})")

    goals_str = "\n".join(goals) if goals else "No active goals."

    # Format stimulus
    stimulus = npc.get("stimulus", {})
    stim_type = stimulus.get("event_type", "UNKNOWN")

    stim_details = []
    if stimulus.get("original_text"):
        stim_details.append(f"Original post: \"{stimulus['original_text']}\"")
    if stimulus.get("original_author"):
        stim_details.append(f"Author: {stimulus['original_author']}")
    if stimulus.get("topic"):
        stim_details.append(f"Topic: {stimulus['topic']}")
    if stimulus.get("summary_fi"):
        stim_details.append(f"Summary: {stimulus['summary_fi']}")
    if stimulus.get("payload"):
        for k, v in stimulus["payload"].items():
            if k not in ["topic", "summary_fi", "original_text", "author_id"]:
                stim_details.append(f"{k}: {v}")

    stim_str = "\n".join(stim_details) if stim_details else "No additional details."

    prompt = f"""## NPC Profile

Name: {npc.get('name', 'Unknown')}
Role: {npc.get('role', 'villager')}
Archetypes: {', '.join(npc.get('archetypes', []))}
Bio: {npc.get('bio', 'No bio.')}

Personality traits: {traits_str}
Values: {values_str}

## Memories

{memories_str}

## Relationships with involved actors

{rels_str}

## Active Goals

{goals_str}

## Stimulus

Type: {stim_type}
{stim_str}

## Your Decision

Based on this NPC's personality, memories, relationships, and goals, how do they react to this stimulus?

Output JSON with: action, intent, emotion, draft, reasoning, confidence
"""
    return prompt
