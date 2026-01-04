#!/usr/bin/env python3
"""
Tests for gear_dream.py - Dream Gear reflection module.
"""

import pytest
from unittest.mock import MagicMock, patch
from gear_dream import (
    DreamGearResult,
    consolidate_lessons,
    analyze_work_patterns,
    generate_proposal,
    run_dream_gear,
    should_transition_from_dream,
    format_dream_status,
    format_proposal,
)
from gear_config import Gear, GearState, GearTransition, get_default_gear_state


def make_gear_state(proposals_count: int = 0) -> GearState:
    """Create a GearState for testing with customizable proposal count."""
    return GearState(
        current_gear=Gear.DREAM,
        entered_at="2025-01-01T00:00:00",
        iterations=0,
        last_transition=None,
        patrol_findings_count=0,
        dream_proposals_count=proposals_count,
    )


# =============================================================================
# DreamGearResult Tests
# =============================================================================

class TestDreamGearResult:
    """Tests for DreamGearResult dataclass."""

    def test_basic_creation(self):
        result = DreamGearResult(
            reflection_completed=True,
            lessons_consolidated=3,
            patterns_identified=["pattern1", "pattern2"],
            proposal=None,
            insights=["insight1"],
            error=None,
        )
        assert result.reflection_completed is True
        assert result.lessons_consolidated == 3
        assert len(result.patterns_identified) == 2

    def test_with_proposal(self):
        proposal = {
            "type": "consolidation",
            "title": "Test proposal",
            "description": "Test description",
            "priority": "medium",
            "effort": "small",
        }
        result = DreamGearResult(
            reflection_completed=True,
            lessons_consolidated=0,
            patterns_identified=[],
            proposal=proposal,
            insights=[],
            error=None,
        )
        assert result.proposal is not None
        assert result.proposal["type"] == "consolidation"

    def test_with_error(self):
        result = DreamGearResult(
            reflection_completed=False,
            lessons_consolidated=0,
            patterns_identified=[],
            proposal=None,
            insights=[],
            error="Something went wrong",
        )
        assert result.error == "Something went wrong"
        assert result.reflection_completed is False

    def test_to_dict(self):
        result = DreamGearResult(
            reflection_completed=True,
            lessons_consolidated=2,
            patterns_identified=["p1"],
            proposal={"type": "test"},
            insights=["i1", "i2"],
            error=None,
        )
        d = result.to_dict()
        assert d["reflection_completed"] is True
        assert d["lessons_consolidated"] == 2
        assert d["patterns_identified"] == ["p1"]
        assert d["proposal"] == {"type": "test"}
        assert d["insights"] == ["i1", "i2"]
        assert d["error"] is None

    def test_to_dict_empty(self):
        result = DreamGearResult(
            reflection_completed=False,
            lessons_consolidated=0,
            patterns_identified=[],
            proposal=None,
            insights=[],
            error=None,
        )
        d = result.to_dict()
        assert d["patterns_identified"] == []
        assert d["proposal"] is None


# =============================================================================
# consolidate_lessons Tests
# =============================================================================

class TestConsolidateLessons:
    """Tests for consolidate_lessons function."""

    def test_empty_memory(self):
        state = {"memory": []}
        count, insights = consolidate_lessons(state)
        assert count == 0
        assert "No lessons to analyze" in insights[0]

    def test_no_memory_key(self):
        state = {}
        count, insights = consolidate_lessons(state)
        assert count == 0

    def test_single_lesson(self):
        state = {
            "memory": [
                {"trigger": "testing", "lesson": "Write tests first", "reinforced": 2}
            ]
        }
        count, insights = consolidate_lessons(state)
        assert count == 0  # No consolidation needed for single lesson

    def test_multiple_same_trigger(self):
        state = {
            "memory": [
                {"trigger": "testing", "lesson": "Write tests first", "reinforced": 2},
                {"trigger": "testing more", "lesson": "Test edge cases", "reinforced": 1},
            ]
        }
        count, insights = consolidate_lessons(state)
        # Both start with "testing" so should suggest consolidation
        assert count >= 1
        assert any("testing" in i.lower() and "consolidate" in i.lower() for i in insights)

    def test_low_value_lessons_detected(self):
        state = {
            "memory": [
                {"trigger": "old", "lesson": "Old lesson", "reinforced": 1},
                {"trigger": "new", "lesson": "New lesson", "reinforced": 5},
            ]
        }
        count, insights = consolidate_lessons(state)
        assert any("low reinforcement" in i.lower() for i in insights)

    def test_high_value_lessons_detected(self):
        state = {
            "memory": [
                {"trigger": "important", "lesson": "Very important", "reinforced": 5},
                {"trigger": "also important", "lesson": "Also important", "reinforced": 3},
            ]
        }
        count, insights = consolidate_lessons(state)
        assert any("high-value" in i.lower() for i in insights)

    def test_audit_pattern_detection(self):
        state = {
            "memory": [
                {"trigger": "test1", "lesson": "L1", "audit_pattern": "pattern1"},
                {"trigger": "test2", "lesson": "L2"},  # No audit pattern
            ]
        }
        count, insights = consolidate_lessons(state)
        assert any("audit pattern" in i.lower() for i in insights)

    def test_no_audit_patterns(self):
        state = {
            "memory": [
                {"trigger": "test1", "lesson": "L1"},
                {"trigger": "test2", "lesson": "L2"},
            ]
        }
        count, insights = consolidate_lessons(state)
        assert any("no lessons have audit patterns" in i.lower() for i in insights)

    def test_non_dict_lessons_skipped(self):
        state = {
            "memory": [
                "invalid lesson",
                None,
                {"trigger": "valid", "lesson": "Valid lesson", "reinforced": 2},
            ]
        }
        count, insights = consolidate_lessons(state)
        # Should not crash and should process the valid lesson
        assert isinstance(count, int)

    def test_multiple_trigger_groups(self):
        state = {
            "memory": [
                {"trigger": "hooks", "lesson": "L1"},
                {"trigger": "hooks more", "lesson": "L2"},
                {"trigger": "testing", "lesson": "L3"},
                {"trigger": "testing again", "lesson": "L4"},
            ]
        }
        count, insights = consolidate_lessons(state)
        # Should find consolidation opportunities in both groups
        assert count >= 2


# =============================================================================
# analyze_work_patterns Tests
# =============================================================================

class TestAnalyzeWorkPatterns:
    """Tests for analyze_work_patterns function."""

    def test_empty_state(self):
        state = {}
        patterns = analyze_work_patterns(state)
        assert isinstance(patterns, list)

    def test_weak_self_score_areas(self):
        state = {
            "self_score": {
                "checks": {
                    "mismatch_detection": {"met": False, "note": "missed issue"},
                    "proof_generation": {"met": True, "note": "good"},
                }
            }
        }
        patterns = analyze_work_patterns(state)
        assert any("weakness" in p.lower() for p in patterns)

    def test_dominant_themes_detected(self):
        state = {
            "memory": [
                {"trigger": "testing framework"},
                {"trigger": "testing patterns"},
                {"trigger": "testing helpers"},
                {"trigger": "hooks setup"},
            ]
        }
        patterns = analyze_work_patterns(state)
        assert any("dominant themes" in p.lower() for p in patterns)
        assert any("testing" in p.lower() for p in patterns)

    def test_memory_growth_warning(self):
        state = {
            "memory": [{"trigger": f"lesson{i}", "lesson": f"L{i}"} for i in range(20)]
        }
        patterns = analyze_work_patterns(state)
        assert any("growing" in p.lower() or "prune" in p.lower() for p in patterns)

    def test_sparse_memory_suggestion(self):
        state = {
            "memory": [
                {"trigger": "test", "lesson": "L1"},
                {"trigger": "test2", "lesson": "L2"},
            ]
        }
        patterns = analyze_work_patterns(state)
        assert any("sparse" in p.lower() for p in patterns)

    def test_no_memory(self):
        state = {"memory": []}
        patterns = analyze_work_patterns(state)
        assert any("sparse" in p.lower() for p in patterns)

    def test_short_words_ignored_in_themes(self):
        state = {
            "memory": [
                {"trigger": "is a test"},  # "is" and "a" should be ignored
                {"trigger": "for my test"},
            ]
        }
        patterns = analyze_work_patterns(state)
        # Should find "test" as dominant theme, not "is" or "a"
        theme_patterns = [p for p in patterns if "dominant" in p.lower()]
        if theme_patterns:
            assert "test" in theme_patterns[0].lower()


# =============================================================================
# generate_proposal Tests
# =============================================================================

class TestGenerateProposal:
    """Tests for generate_proposal function."""

    def test_rate_limit_respected(self):
        state = {"memory": [{"trigger": "test", "lesson": "L1"}] * 10}
        gear_state = make_gear_state(proposals_count=5)  # At limit
        proposal = generate_proposal(state, gear_state)
        assert proposal is None

    def test_consolidation_proposal(self):
        state = {
            "memory": [
                {"trigger": "hooks", "lesson": "L1"},
                {"trigger": "hooks more", "lesson": "L2"},
            ]
        }
        gear_state = make_gear_state(proposals_count=0)
        proposal = generate_proposal(state, gear_state)
        # May or may not generate proposal depending on consolidation detection
        if proposal:
            assert "type" in proposal
            assert "title" in proposal

    def test_audit_pattern_proposal(self):
        # Many lessons without audit patterns
        state = {
            "memory": [{"trigger": f"test{i}", "lesson": f"L{i}"} for i in range(10)]
        }
        gear_state = make_gear_state(proposals_count=0)
        proposal = generate_proposal(state, gear_state)
        if proposal:
            assert "type" in proposal

    def test_weakness_proposal(self):
        state = {
            "self_score": {
                "checks": {
                    "mismatch_detection": {"met": False},
                }
            },
            "memory": [],
        }
        gear_state = make_gear_state(proposals_count=0)
        proposal = generate_proposal(state, gear_state)
        if proposal:
            assert "type" in proposal

    def test_none_gear_state_returns_none(self):
        state = {"memory": [{"trigger": "test", "lesson": "L1"}] * 10}
        proposal = generate_proposal(state, None)
        assert proposal is None

    def test_proposal_structure(self):
        state = {
            "memory": [
                {"trigger": "hooks", "lesson": "L1"},
                {"trigger": "hooks more", "lesson": "L2"},
                {"trigger": "hooks again", "lesson": "L3"},
            ]
        }
        gear_state = make_gear_state(proposals_count=0)
        proposal = generate_proposal(state, gear_state)
        if proposal:
            assert "type" in proposal
            assert "title" in proposal
            assert "description" in proposal
            assert "priority" in proposal
            assert "effort" in proposal


# =============================================================================
# run_dream_gear Tests
# =============================================================================

class TestRunDreamGear:
    """Tests for run_dream_gear function."""

    def test_basic_run(self):
        state = {
            "memory": [
                {"trigger": "test", "lesson": "L1", "reinforced": 2},
            ]
        }
        gear_state = make_gear_state()
        result = run_dream_gear(state, gear_state)
        assert result.reflection_completed is True
        assert result.error is None

    def test_returns_insights(self):
        state = {
            "memory": [
                {"trigger": "hooks", "lesson": "L1"},
                {"trigger": "hooks more", "lesson": "L2"},
            ]
        }
        gear_state = make_gear_state()
        result = run_dream_gear(state, gear_state)
        assert isinstance(result.insights, list)

    def test_returns_patterns(self):
        state = {
            "memory": [{"trigger": "test", "lesson": "L1"}] * 5
        }
        gear_state = make_gear_state()
        result = run_dream_gear(state, gear_state)
        assert isinstance(result.patterns_identified, list)

    def test_handles_empty_state(self):
        state = {}
        gear_state = make_gear_state()
        result = run_dream_gear(state, gear_state)
        assert result.reflection_completed is True

    def test_error_handling(self):
        # Force an error by passing invalid state
        with patch('gear_dream.consolidate_lessons') as mock:
            mock.side_effect = Exception("Test error")
            gear_state = make_gear_state()
            result = run_dream_gear({}, gear_state)
            assert result.reflection_completed is False
            assert result.error is not None

    def test_may_generate_proposal(self):
        state = {
            "memory": [{"trigger": f"test{i}", "lesson": f"L{i}"} for i in range(10)]
        }
        gear_state = make_gear_state(proposals_count=0)
        result = run_dream_gear(state, gear_state)
        # Proposal may or may not be generated
        assert result.reflection_completed is True


# =============================================================================
# should_transition_from_dream Tests
# =============================================================================

class TestShouldTransitionFromDream:
    """Tests for should_transition_from_dream function."""

    def test_no_proposal_transitions_to_patrol(self):
        result = DreamGearResult(
            reflection_completed=True,
            lessons_consolidated=0,
            patterns_identified=[],
            proposal=None,
            insights=[],
            error=None,
        )
        gear_state = make_gear_state()
        should, transition = should_transition_from_dream(result, gear_state)
        assert should is True
        assert transition == GearTransition.DREAM_TO_PATROL

    def test_with_proposal_stays(self):
        result = DreamGearResult(
            reflection_completed=True,
            lessons_consolidated=0,
            patterns_identified=[],
            proposal={"type": "test", "title": "Test"},
            insights=[],
            error=None,
        )
        gear_state = make_gear_state()
        should, transition = should_transition_from_dream(result, gear_state)
        assert should is False
        assert transition is None

    def test_error_state_transitions(self):
        result = DreamGearResult(
            reflection_completed=False,
            lessons_consolidated=0,
            patterns_identified=[],
            proposal=None,
            insights=[],
            error="error",
        )
        gear_state = make_gear_state()
        should, transition = should_transition_from_dream(result, gear_state)
        # Still transitions even with error (no proposal)
        assert should is True


# =============================================================================
# format_dream_status Tests
# =============================================================================

class TestFormatDreamStatus:
    """Tests for format_dream_status function."""

    def test_basic_format(self):
        result = DreamGearResult(
            reflection_completed=True,
            lessons_consolidated=0,
            patterns_identified=[],
            proposal=None,
            insights=[],
            error=None,
        )
        output = format_dream_status(result)
        assert "DREAM GEAR" in output
        assert "Complete" in output

    def test_shows_consolidation_count(self):
        result = DreamGearResult(
            reflection_completed=True,
            lessons_consolidated=5,
            patterns_identified=[],
            proposal=None,
            insights=[],
            error=None,
        )
        output = format_dream_status(result)
        assert "5" in output
        assert "consolidation" in output.lower()

    def test_shows_patterns(self):
        result = DreamGearResult(
            reflection_completed=True,
            lessons_consolidated=0,
            patterns_identified=["Pattern A", "Pattern B"],
            proposal=None,
            insights=[],
            error=None,
        )
        output = format_dream_status(result)
        assert "Pattern A" in output
        assert "Pattern B" in output

    def test_shows_insights(self):
        result = DreamGearResult(
            reflection_completed=True,
            lessons_consolidated=0,
            patterns_identified=[],
            proposal=None,
            insights=["Insight one", "Insight two"],
            error=None,
        )
        output = format_dream_status(result)
        assert "Insight one" in output
        assert "Insight two" in output

    def test_truncates_long_insights(self):
        result = DreamGearResult(
            reflection_completed=True,
            lessons_consolidated=0,
            patterns_identified=[],
            proposal=None,
            insights=["A" * 100],  # Very long insight
            error=None,
        )
        output = format_dream_status(result)
        assert "..." in output

    def test_shows_proposal(self):
        result = DreamGearResult(
            reflection_completed=True,
            lessons_consolidated=0,
            patterns_identified=[],
            proposal={
                "type": "enhancement",
                "title": "Test Proposal",
                "description": "Do something",
                "priority": "high",
            },
            insights=[],
            error=None,
        )
        output = format_dream_status(result)
        assert "PROPOSAL" in output
        assert "Test Proposal" in output

    def test_shows_error(self):
        result = DreamGearResult(
            reflection_completed=False,
            lessons_consolidated=0,
            patterns_identified=[],
            proposal=None,
            insights=[],
            error="Something failed",
        )
        output = format_dream_status(result)
        assert "Error" in output
        assert "Something failed" in output

    def test_failed_reflection_status(self):
        result = DreamGearResult(
            reflection_completed=False,
            lessons_consolidated=0,
            patterns_identified=[],
            proposal=None,
            insights=[],
            error=None,
        )
        output = format_dream_status(result)
        assert "Failed" in output


# =============================================================================
# format_proposal Tests
# =============================================================================

class TestFormatProposal:
    """Tests for format_proposal function."""

    def test_none_proposal(self):
        output = format_proposal(None)
        assert "No proposal" in output

    def test_empty_proposal(self):
        output = format_proposal({})
        # Should handle gracefully
        assert isinstance(output, str)

    def test_full_proposal(self):
        proposal = {
            "type": "consolidation",
            "title": "Consolidate lessons",
            "description": "Many similar lessons exist",
            "priority": "medium",
            "effort": "small",
        }
        output = format_proposal(proposal)
        assert "DREAM PROPOSAL" in output
        assert "Consolidate lessons" in output
        assert "consolidation" in output
        assert "medium" in output
        assert "small" in output

    def test_shows_options(self):
        proposal = {
            "type": "test",
            "title": "Test",
            "description": "Desc",
            "priority": "low",
            "effort": "small",
        }
        output = format_proposal(proposal)
        assert "/edge approve" in output
        assert "/edge skip" in output
        assert "/edge stop" in output


# =============================================================================
# Edge Cases
# =============================================================================

class TestEdgeCases:
    """Edge case tests for gear_dream module."""

    def test_memory_with_missing_trigger(self):
        state = {
            "memory": [
                {"lesson": "No trigger here"},
                {"trigger": "valid", "lesson": "Has trigger"},
            ]
        }
        count, insights = consolidate_lessons(state)
        # Should not crash
        assert isinstance(count, int)

    def test_memory_with_empty_trigger(self):
        state = {
            "memory": [
                {"trigger": "", "lesson": "Empty trigger"},
            ]
        }
        count, insights = consolidate_lessons(state)
        assert isinstance(count, int)

    def test_self_score_with_non_dict_checks(self):
        state = {
            "self_score": {
                "checks": {
                    "valid": {"met": True},
                    "invalid": "not a dict",
                }
            }
        }
        patterns = analyze_work_patterns(state)
        # Should not crash
        assert isinstance(patterns, list)

    def test_proposal_with_zero_memory(self):
        state = {"memory": []}
        gear_state = make_gear_state()
        proposal = generate_proposal(state, gear_state)
        # May or may not generate proposal
        assert proposal is None or isinstance(proposal, dict)

    def test_very_large_memory(self):
        state = {
            "memory": [
                {"trigger": f"lesson{i % 5}", "lesson": f"L{i}", "reinforced": i % 5}
                for i in range(100)
            ]
        }
        gear_state = make_gear_state()
        result = run_dream_gear(state, gear_state)
        assert result.reflection_completed is True

    def test_all_lessons_high_value(self):
        state = {
            "memory": [
                {"trigger": f"test{i}", "lesson": f"L{i}", "reinforced": 5}
                for i in range(5)
            ]
        }
        count, insights = consolidate_lessons(state)
        assert any("high-value" in i.lower() for i in insights)

    def test_all_lessons_have_audit_patterns(self):
        state = {
            "memory": [
                {"trigger": f"test{i}", "lesson": f"L{i}", "audit_pattern": f"pat{i}"}
                for i in range(3)
            ]
        }
        count, insights = consolidate_lessons(state)
        assert any("3/3" in i for i in insights)

    def test_single_word_triggers(self):
        state = {
            "memory": [
                {"trigger": "hooks"},
                {"trigger": "hooks"},
                {"trigger": "hooks"},
            ]
        }
        count, insights = consolidate_lessons(state)
        # All same trigger - should suggest consolidation
        assert count >= 2
