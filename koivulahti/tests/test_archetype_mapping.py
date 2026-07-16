"""
Regression tests for archetype mapping.

Ensures that:
1. Every catalog archetype maps to an appraisal archetype
2. Every mapped archetype exists in APPRAISAL_MATRIX
3. Unknown archetypes fall back to "default"
"""
import sys
from pathlib import Path

# Add packages to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from packages.shared.archetype_mapping import (
    ARCHETYPE_MAPPING,
    APPRAISAL_ARCHETYPES,
    CATALOG_ARCHETYPES,
    get_appraisal_archetype,
)


class TestArchetypeMappingComplete:
    """Test that every catalog archetype is mapped."""

    def test_all_catalog_archetypes_mapped(self):
        """Every catalog archetype must have a mapping."""
        unmapped = []
        for arch in CATALOG_ARCHETYPES:
            if arch not in ARCHETYPE_MAPPING:
                unmapped.append(arch)

        assert not unmapped, f"Unmapped catalog archetypes: {unmapped}"

    def test_mapping_covers_all_catalog_archetypes(self):
        """ARCHETYPE_MAPPING keys should include all catalog archetypes."""
        missing = set(CATALOG_ARCHETYPES) - set(ARCHETYPE_MAPPING.keys())
        assert not missing, f"Missing from ARCHETYPE_MAPPING: {missing}"


class TestArchetypeMappingTargets:
    """Test that mapped archetypes exist in APPRAISAL_ARCHETYPES."""

    def test_all_mapped_archetypes_valid(self):
        """Every mapped archetype must be a valid appraisal archetype."""
        invalid = []
        for catalog_arch, mapped_arch in ARCHETYPE_MAPPING.items():
            if mapped_arch not in APPRAISAL_ARCHETYPES:
                invalid.append((catalog_arch, mapped_arch))

        assert not invalid, f"Invalid mapped archetypes: {invalid}"

    def test_all_appraisal_archetypes_used(self):
        """Every appraisal archetype must be used by at least one catalog archetype."""
        mapped_targets = set(ARCHETYPE_MAPPING.values())
        unused = set(APPRAISAL_ARCHETYPES) - mapped_targets

        assert not unused, f"Unused appraisal archetypes: {unused}"


class TestArchetypeFallback:
    """Test fallback behavior for unknown archetypes."""

    def test_unknown_archetype_returns_default(self):
        """Unknown archetypes should return 'default'."""
        result = get_appraisal_archetype(["unknown_archetype", "another_unknown"])
        assert result == "default"

    def test_empty_archetypes_returns_default(self):
        """Empty archetypes list should return 'default'."""
        result = get_appraisal_archetype([])
        assert result == "default"

    def test_known_archetype_returns_mapped(self):
        """Known archetype should return its mapped value."""
        result = get_appraisal_archetype(["gossip_amplifier"])
        assert result == "gossip"

    def test_first_known_archetype_wins(self):
        """First known archetype in list should be used."""
        result = get_appraisal_archetype(["unknown", "provoker", "gossip_amplifier"])
        assert result == "political"  # provoker maps to political


class TestArchetypeMappingConsistency:
    """Test consistency of the mapping."""

    def test_all_appraisal_archetypes_have_mappings(self):
        """Verify all appraisal archetypes are reachable from catalog archetypes."""
        target_counts = {}
        for mapped in ARCHETYPE_MAPPING.values():
            target_counts[mapped] = target_counts.get(mapped, 0) + 1

        for arch in APPRAISAL_ARCHETYPES:
            assert arch in target_counts, f"Appraisal archetype '{arch}' has no catalog mappings"

    def test_case_insensitive_matching(self):
        """Archetype matching should be case-insensitive."""
        result = get_appraisal_archetype(["GOSSIP_AMPLIFIER"])
        assert result == "gossip"

        result2 = get_appraisal_archetype(["Gossip_Amplifier"])
        assert result2 == "gossip"
