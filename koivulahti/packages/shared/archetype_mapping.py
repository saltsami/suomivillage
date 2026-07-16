"""
Archetype mapping constants.

Maps catalog archetypes (from NPC profiles) to appraisal archetypes
(used in APPRAISAL_MATRIX for ambient event reactions).
"""
from typing import Dict

# Map catalog archetypes to appraisal archetypes
ARCHETYPE_MAPPING: Dict[str, str] = {
    # Gossip types - curious, spread information
    "gossip_amplifier": "gossip",
    "network_hub": "gossip",
    "borrow_drama_engine": "gossip",
    # Romantic/aesthetic types - emotional, appreciative
    "aesthetic_poster": "romantic",
    "connector": "romantic",
    "micro_influencer": "romantic",
    # Practical types - matter-of-fact, solution-oriented
    "gatekeeper": "practical",
    "organizer": "practical",
    "hustler": "practical",
    "fixer": "practical",
    "norm_enforcer": "practical",
    # Anxious types - worried, cautious
    "sensitive_to_rumors": "anxious",
    "brand_manager": "anxious",
    # Stoic types - calm, often ignore trivial events
    "private_soul": "stoic",
    "peacekeeper": "stoic",
    "truth_anchor": "stoic",
    "editor": "stoic",
    "narrator": "stoic",
    # Social types - outgoing, invite others
    "catalyst": "social",
    "outsider_insider": "social",
    "trend_hunter": "social",
    # Political types - opinionated, blame/criticize
    "provoker": "political",
    "status_seeker": "political",
    "investigator": "political",
}

# Valid appraisal archetypes (targets)
APPRAISAL_ARCHETYPES = ["romantic", "practical", "anxious", "stoic", "gossip", "social", "political"]

# All known catalog archetypes
CATALOG_ARCHETYPES = [
    "aesthetic_poster",
    "borrow_drama_engine",
    "brand_manager",
    "catalyst",
    "connector",
    "editor",
    "fixer",
    "gatekeeper",
    "gossip_amplifier",
    "hustler",
    "investigator",
    "micro_influencer",
    "narrator",
    "network_hub",
    "norm_enforcer",
    "organizer",
    "outsider_insider",
    "peacekeeper",
    "private_soul",
    "provoker",
    "sensitive_to_rumors",
    "status_seeker",
    "trend_hunter",
    "truth_anchor",
]

# Logged unknown archetypes (to avoid spam)
_logged_unknown_archetypes: set = set()


def get_appraisal_archetype(archetypes: list, npc_id: str = "?") -> str:
    """
    Map catalog archetypes to appraisal archetype.

    Args:
        archetypes: List of catalog archetypes from NPC profile
        npc_id: NPC identifier for logging

    Returns:
        Appraisal archetype string (or "default" if no match)
    """
    for arch in archetypes:
        arch_lower = arch.lower()
        if arch_lower in ARCHETYPE_MAPPING:
            return ARCHETYPE_MAPPING[arch_lower]

        # Log unknown archetype once
        if arch_lower not in _logged_unknown_archetypes:
            _logged_unknown_archetypes.add(arch_lower)
            print(f"[archetype] unknown catalog archetype '{arch}' for {npc_id}, using default")

    return "default"
