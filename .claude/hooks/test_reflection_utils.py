#!/usr/bin/env python3
"""
Tests for reflection_utils.py

Coverage:
- ADAPTATION_CHECKS: List of 6 check names
- CHECK_IMPROVEMENTS: Dictionary of improvement suggestions per check
- analyze_score_patterns: Score analysis from archive entries
- get_recurring_failures: Finding repeatedly failed checks
- get_improvement_suggestion: Getting suggestions for weak checks
- generate_reflection_summary: Human-readable summary
- generate_improvement_challenges: Brainstorm challenges from failures
"""

import unittest

import reflection_utils


class TestConstants(unittest.TestCase):
    """Tests for module constants."""

    def test_adaptation_checks_is_list(self):
        """ADAPTATION_CHECKS should be a list."""
        self.assertIsInstance(reflection_utils.ADAPTATION_CHECKS, list)

    def test_adaptation_checks_has_six_items(self):
        """ADAPTATION_CHECKS should have exactly 6 checks."""
        self.assertEqual(len(reflection_utils.ADAPTATION_CHECKS), 6)

    def test_adaptation_checks_contains_expected(self):
        """ADAPTATION_CHECKS should contain all expected check names."""
        expected = [
            "mismatch_detection",
            "plan_revision",
            "tool_switching",
            "memory_update",
            "proof_generation",
            "stop_condition"
        ]
        for check in expected:
            self.assertIn(check, reflection_utils.ADAPTATION_CHECKS)

    def test_check_improvements_is_dict(self):
        """CHECK_IMPROVEMENTS should be a dictionary."""
        self.assertIsInstance(reflection_utils.CHECK_IMPROVEMENTS, dict)

    def test_check_improvements_has_all_checks(self):
        """CHECK_IMPROVEMENTS should have entries for all adaptation checks."""
        for check in reflection_utils.ADAPTATION_CHECKS:
            self.assertIn(check, reflection_utils.CHECK_IMPROVEMENTS)

    def test_check_improvements_structure(self):
        """Each CHECK_IMPROVEMENTS entry should have required fields."""
        for check, data in reflection_utils.CHECK_IMPROVEMENTS.items():
            self.assertIn("description", data, f"{check} missing description")
            self.assertIn("improvements", data, f"{check} missing improvements")
            self.assertIn("brainstorm_challenge", data, f"{check} missing brainstorm_challenge")
            self.assertIsInstance(data["improvements"], list)
            self.assertGreater(len(data["improvements"]), 0)


class TestAnalyzeScorePatterns(unittest.TestCase):
    """Tests for analyze_score_patterns function."""

    def test_empty_entries_returns_defaults(self):
        """Should return default values for empty entries."""
        result = reflection_utils.analyze_score_patterns([])

        self.assertEqual(result["total_objectives"], 0)
        self.assertEqual(result["avg_score"], 0)
        self.assertEqual(result["level_distribution"], {})
        self.assertEqual(result["check_failures"], {})
        self.assertEqual(result["weakest_checks"], [])
        self.assertEqual(result["score_trend"], "unknown")

    def test_filters_only_completed_objectives(self):
        """Should only count completed_objective type entries."""
        entries = [
            {"type": "resolved_mismatch"},
            {"type": "completed_step"},
            {"type": "completed_objective", "score": {"total": 5, "level": "real_agent"}}
        ]
        result = reflection_utils.analyze_score_patterns(entries)

        self.assertEqual(result["total_objectives"], 1)

    def test_calculates_average_score(self):
        """Should calculate average score correctly."""
        entries = [
            {"type": "completed_objective", "score": {"total": 4, "level": "promising"}},
            {"type": "completed_objective", "score": {"total": 6, "level": "real_agent"}},
            {"type": "completed_objective", "score": {"total": 5, "level": "real_agent"}}
        ]
        result = reflection_utils.analyze_score_patterns(entries)

        self.assertEqual(result["avg_score"], 5.0)

    def test_supports_self_score_key(self):
        """Should support both 'score' and 'self_score' keys."""
        entries = [
            {"type": "completed_objective", "self_score": {"total": 4, "level": "promising"}}
        ]
        result = reflection_utils.analyze_score_patterns(entries)

        self.assertEqual(result["avg_score"], 4.0)

    def test_level_distribution(self):
        """Should count level distribution correctly."""
        entries = [
            {"type": "completed_objective", "score": {"total": 5, "level": "real_agent"}},
            {"type": "completed_objective", "score": {"total": 5, "level": "real_agent"}},
            {"type": "completed_objective", "score": {"total": 3, "level": "promising"}}
        ]
        result = reflection_utils.analyze_score_patterns(entries)

        self.assertEqual(result["level_distribution"]["real_agent"], 2)
        self.assertEqual(result["level_distribution"]["promising"], 1)

    def test_unknown_level_for_missing_score(self):
        """Should count as unknown when no score data."""
        entries = [
            {"type": "completed_objective"},  # No score
            {"type": "completed_objective", "score": {}}  # Empty score
        ]
        result = reflection_utils.analyze_score_patterns(entries)

        self.assertEqual(result["level_distribution"].get("unknown", 0), 2)

    def test_counts_check_failures(self):
        """Should count failed checks correctly."""
        entries = [
            {
                "type": "completed_objective",
                "score": {
                    "total": 4,
                    "level": "promising",
                    "checks": {
                        "mismatch_detection": {"met": True},
                        "plan_revision": {"met": False},
                        "tool_switching": {"met": False}
                    }
                }
            },
            {
                "type": "completed_objective",
                "score": {
                    "total": 5,
                    "level": "real_agent",
                    "checks": {
                        "plan_revision": {"met": False}  # Another failure
                    }
                }
            }
        ]
        result = reflection_utils.analyze_score_patterns(entries)

        self.assertEqual(result["check_failures"]["plan_revision"], 2)
        self.assertEqual(result["check_failures"]["tool_switching"], 1)
        self.assertEqual(result["check_failures"]["mismatch_detection"], 0)

    def test_weakest_checks_require_two_failures(self):
        """Should only include checks that failed 2+ times as weakest."""
        entries = [
            {
                "type": "completed_objective",
                "score": {
                    "total": 4,
                    "checks": {
                        "plan_revision": {"met": False},
                        "tool_switching": {"met": False}
                    }
                }
            },
            {
                "type": "completed_objective",
                "score": {
                    "total": 5,
                    "checks": {
                        "plan_revision": {"met": False}
                    }
                }
            }
        ]
        result = reflection_utils.analyze_score_patterns(entries)

        self.assertIn("plan_revision", result["weakest_checks"])
        self.assertNotIn("tool_switching", result["weakest_checks"])

    def test_weakest_checks_sorted_by_count(self):
        """Weakest checks should be sorted by failure count (descending)."""
        entries = [
            {"type": "completed_objective", "score": {"total": 4, "checks": {"plan_revision": {"met": False}, "memory_update": {"met": False}}}},
            {"type": "completed_objective", "score": {"total": 4, "checks": {"plan_revision": {"met": False}, "memory_update": {"met": False}}}},
            {"type": "completed_objective", "score": {"total": 4, "checks": {"memory_update": {"met": False}}}}
        ]
        result = reflection_utils.analyze_score_patterns(entries)

        # memory_update has 3 failures, plan_revision has 2
        self.assertEqual(result["weakest_checks"][0], "memory_update")

    def test_trend_unknown_with_few_scores(self):
        """Should return unknown trend with fewer than 3 scores."""
        entries = [
            {"type": "completed_objective", "score": {"total": 5, "level": "real_agent"}},
            {"type": "completed_objective", "score": {"total": 4, "level": "promising"}}
        ]
        result = reflection_utils.analyze_score_patterns(entries)

        self.assertEqual(result["score_trend"], "unknown")

    def test_trend_improving(self):
        """Should detect improving trend when recent scores are higher."""
        entries = [
            {"type": "completed_objective", "score": {"total": 3, "level": "promising"}},
            {"type": "completed_objective", "score": {"total": 3, "level": "promising"}},
            {"type": "completed_objective", "score": {"total": 5, "level": "real_agent"}},
            {"type": "completed_objective", "score": {"total": 5, "level": "real_agent"}},
            {"type": "completed_objective", "score": {"total": 6, "level": "real_agent"}}
        ]
        result = reflection_utils.analyze_score_patterns(entries)

        self.assertEqual(result["score_trend"], "improving")

    def test_trend_declining(self):
        """Should detect declining trend when recent scores are lower."""
        entries = [
            {"type": "completed_objective", "score": {"total": 6, "level": "real_agent"}},
            {"type": "completed_objective", "score": {"total": 6, "level": "real_agent"}},
            {"type": "completed_objective", "score": {"total": 3, "level": "promising"}},
            {"type": "completed_objective", "score": {"total": 3, "level": "promising"}},
            {"type": "completed_objective", "score": {"total": 2, "level": "promising"}}
        ]
        result = reflection_utils.analyze_score_patterns(entries)

        self.assertEqual(result["score_trend"], "declining")

    def test_trend_stable(self):
        """Should detect stable trend when scores are consistent."""
        entries = [
            {"type": "completed_objective", "score": {"total": 5, "level": "real_agent"}},
            {"type": "completed_objective", "score": {"total": 5, "level": "real_agent"}},
            {"type": "completed_objective", "score": {"total": 5, "level": "real_agent"}},
            {"type": "completed_objective", "score": {"total": 5, "level": "real_agent"}}
        ]
        result = reflection_utils.analyze_score_patterns(entries)

        self.assertEqual(result["score_trend"], "stable")


class TestGetRecurringFailures(unittest.TestCase):
    """Tests for get_recurring_failures function."""

    def test_empty_entries_returns_empty(self):
        """Should return empty list for empty entries."""
        result = reflection_utils.get_recurring_failures([])
        self.assertEqual(result, [])

    def test_filters_by_threshold(self):
        """Should only include failures meeting threshold."""
        entries = [
            {"type": "completed_objective", "score": {"total": 4, "checks": {"plan_revision": {"met": False}}}},
            {"type": "completed_objective", "score": {"total": 4, "checks": {"plan_revision": {"met": False}}}},
            {"type": "completed_objective", "score": {"total": 4, "checks": {"tool_switching": {"met": False}}}}
        ]

        result = reflection_utils.get_recurring_failures(entries, threshold=2)

        check_names = [r["check"] for r in result]
        self.assertIn("plan_revision", check_names)
        self.assertNotIn("tool_switching", check_names)

    def test_custom_threshold(self):
        """Should respect custom threshold parameter."""
        entries = [
            {"type": "completed_objective", "score": {"total": 4, "checks": {"plan_revision": {"met": False}}}},
            {"type": "completed_objective", "score": {"total": 4, "checks": {"plan_revision": {"met": False}}}},
            {"type": "completed_objective", "score": {"total": 4, "checks": {"plan_revision": {"met": False}}}}
        ]

        result = reflection_utils.get_recurring_failures(entries, threshold=3)

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["check"], "plan_revision")

    def test_includes_failure_count(self):
        """Should include failure count in results."""
        entries = [
            {"type": "completed_objective", "score": {"total": 4, "checks": {"memory_update": {"met": False}}}},
            {"type": "completed_objective", "score": {"total": 4, "checks": {"memory_update": {"met": False}}}},
            {"type": "completed_objective", "score": {"total": 4, "checks": {"memory_update": {"met": False}}}}
        ]

        result = reflection_utils.get_recurring_failures(entries, threshold=2)

        self.assertEqual(result[0]["failure_count"], 3)

    def test_includes_description(self):
        """Should include description from CHECK_IMPROVEMENTS."""
        entries = [
            {"type": "completed_objective", "score": {"total": 4, "checks": {"plan_revision": {"met": False}}}},
            {"type": "completed_objective", "score": {"total": 4, "checks": {"plan_revision": {"met": False}}}}
        ]

        result = reflection_utils.get_recurring_failures(entries, threshold=2)

        self.assertIn("description", result[0])
        self.assertIsInstance(result[0]["description"], str)

    def test_includes_improvements(self):
        """Should include improvement suggestions from CHECK_IMPROVEMENTS."""
        entries = [
            {"type": "completed_objective", "score": {"total": 4, "checks": {"tool_switching": {"met": False}}}},
            {"type": "completed_objective", "score": {"total": 4, "checks": {"tool_switching": {"met": False}}}}
        ]

        result = reflection_utils.get_recurring_failures(entries, threshold=2)

        self.assertIn("improvements", result[0])
        self.assertIsInstance(result[0]["improvements"], list)

    def test_includes_brainstorm_challenge(self):
        """Should include brainstorm challenge from CHECK_IMPROVEMENTS."""
        entries = [
            {"type": "completed_objective", "score": {"total": 4, "checks": {"proof_generation": {"met": False}}}},
            {"type": "completed_objective", "score": {"total": 4, "checks": {"proof_generation": {"met": False}}}}
        ]

        result = reflection_utils.get_recurring_failures(entries, threshold=2)

        self.assertIn("brainstorm_challenge", result[0])

    def test_sorted_by_failure_count(self):
        """Should sort results by failure count descending."""
        entries = [
            {"type": "completed_objective", "score": {"total": 4, "checks": {"plan_revision": {"met": False}, "memory_update": {"met": False}}}},
            {"type": "completed_objective", "score": {"total": 4, "checks": {"plan_revision": {"met": False}, "memory_update": {"met": False}}}},
            {"type": "completed_objective", "score": {"total": 4, "checks": {"memory_update": {"met": False}}}}
        ]

        result = reflection_utils.get_recurring_failures(entries, threshold=2)

        self.assertEqual(result[0]["check"], "memory_update")
        self.assertEqual(result[1]["check"], "plan_revision")


class TestGetImprovementSuggestion(unittest.TestCase):
    """Tests for get_improvement_suggestion function."""

    def test_returns_dict(self):
        """Should return a dictionary."""
        result = reflection_utils.get_improvement_suggestion("plan_revision")
        self.assertIsInstance(result, dict)

    def test_includes_check_name(self):
        """Should include the check name."""
        result = reflection_utils.get_improvement_suggestion("tool_switching")
        self.assertEqual(result["check"], "tool_switching")

    def test_includes_description(self):
        """Should include description for known check."""
        result = reflection_utils.get_improvement_suggestion("memory_update")
        self.assertIn("description", result)
        self.assertIsInstance(result["description"], str)

    def test_includes_suggestion(self):
        """Should include a suggestion string."""
        result = reflection_utils.get_improvement_suggestion("proof_generation")
        self.assertIn("suggestion", result)
        self.assertIn("proof_generation", result["suggestion"])

    def test_includes_actions(self):
        """Should include actions list."""
        result = reflection_utils.get_improvement_suggestion("stop_condition")
        self.assertIn("actions", result)
        self.assertIsInstance(result["actions"], list)

    def test_includes_brainstorm(self):
        """Should include brainstorm challenge."""
        result = reflection_utils.get_improvement_suggestion("mismatch_detection")
        self.assertIn("brainstorm", result)

    def test_unknown_check_returns_defaults(self):
        """Should return default values for unknown check."""
        result = reflection_utils.get_improvement_suggestion("unknown_check")

        self.assertEqual(result["check"], "unknown_check")
        self.assertIn("suggestion", result)
        self.assertIn("actions", result)
        self.assertIsInstance(result["actions"], list)


class TestGenerateReflectionSummary(unittest.TestCase):
    """Tests for generate_reflection_summary function."""

    def test_returns_none_for_empty(self):
        """Should return None when no objectives."""
        result = reflection_utils.generate_reflection_summary([])
        self.assertIsNone(result)

    def test_returns_string(self):
        """Should return a string when objectives exist."""
        entries = [
            {"type": "completed_objective", "score": {"total": 5, "level": "real_agent"}}
        ]
        result = reflection_utils.generate_reflection_summary(entries)

        self.assertIsInstance(result, str)

    def test_includes_sessions_count(self):
        """Should include number of sessions scored."""
        entries = [
            {"type": "completed_objective", "score": {"total": 5, "level": "real_agent"}},
            {"type": "completed_objective", "score": {"total": 4, "level": "promising"}}
        ]
        result = reflection_utils.generate_reflection_summary(entries)

        self.assertIn("Sessions scored:", result)

    def test_includes_average_score(self):
        """Should include average score."""
        entries = [
            {"type": "completed_objective", "score": {"total": 5, "level": "real_agent"}}
        ]
        result = reflection_utils.generate_reflection_summary(entries)

        self.assertIn("Average score:", result)
        self.assertIn("/6", result)

    def test_includes_level_distribution(self):
        """Should include level distribution."""
        entries = [
            {"type": "completed_objective", "score": {"total": 5, "level": "real_agent"}}
        ]
        result = reflection_utils.generate_reflection_summary(entries)

        self.assertIn("Levels:", result)

    def test_includes_trend_emoji(self):
        """Should include trend with emoji when available."""
        entries = [
            {"type": "completed_objective", "score": {"total": 3, "level": "promising"}},
            {"type": "completed_objective", "score": {"total": 4, "level": "promising"}},
            {"type": "completed_objective", "score": {"total": 5, "level": "real_agent"}},
            {"type": "completed_objective", "score": {"total": 6, "level": "real_agent"}}
        ]
        result = reflection_utils.generate_reflection_summary(entries)

        self.assertIn("Trend:", result)

    def test_includes_recurring_failures(self):
        """Should include recurring weak checks when present."""
        entries = [
            {"type": "completed_objective", "score": {"total": 4, "checks": {"plan_revision": {"met": False}}}},
            {"type": "completed_objective", "score": {"total": 4, "checks": {"plan_revision": {"met": False}}}}
        ]
        result = reflection_utils.generate_reflection_summary(entries)

        self.assertIn("RECURRING WEAK CHECKS", result)
        self.assertIn("plan_revision", result)

    def test_shows_improvement_for_weak_check(self):
        """Should show improvement suggestion for weak checks."""
        entries = [
            {"type": "completed_objective", "score": {"total": 4, "checks": {"memory_update": {"met": False}}}},
            {"type": "completed_objective", "score": {"total": 4, "checks": {"memory_update": {"met": False}}}}
        ]
        result = reflection_utils.generate_reflection_summary(entries)

        self.assertIn("Try:", result)

    def test_limits_recurring_failures_to_two(self):
        """Should show at most 2 recurring failures."""
        entries = [
            {"type": "completed_objective", "score": {"total": 2, "checks": {
                "plan_revision": {"met": False},
                "tool_switching": {"met": False},
                "memory_update": {"met": False}
            }}},
            {"type": "completed_objective", "score": {"total": 2, "checks": {
                "plan_revision": {"met": False},
                "tool_switching": {"met": False},
                "memory_update": {"met": False}
            }}}
        ]
        result = reflection_utils.generate_reflection_summary(entries)

        # Count bullet points for failures (• character)
        lines = result.split("\n")
        failure_lines = [l for l in lines if "failed" in l]
        self.assertLessEqual(len(failure_lines), 2)


class TestGenerateImprovementChallenges(unittest.TestCase):
    """Tests for generate_improvement_challenges function."""

    def test_empty_entries_returns_empty(self):
        """Should return empty list for empty entries."""
        result = reflection_utils.generate_improvement_challenges([])
        self.assertEqual(result, [])

    def test_returns_list(self):
        """Should return a list."""
        entries = [
            {"type": "completed_objective", "score": {"total": 4, "checks": {"plan_revision": {"met": False}}}},
            {"type": "completed_objective", "score": {"total": 4, "checks": {"plan_revision": {"met": False}}}}
        ]
        result = reflection_utils.generate_improvement_challenges(entries)

        self.assertIsInstance(result, list)

    def test_returns_brainstorm_challenges(self):
        """Should return brainstorm challenges for recurring failures."""
        entries = [
            {"type": "completed_objective", "score": {"total": 4, "checks": {"mismatch_detection": {"met": False}}}},
            {"type": "completed_objective", "score": {"total": 4, "checks": {"mismatch_detection": {"met": False}}}}
        ]
        result = reflection_utils.generate_improvement_challenges(entries)

        self.assertGreater(len(result), 0)
        # All challenges should be "How might we..." style
        for challenge in result:
            self.assertIn("How might we", challenge)

    def test_no_challenges_without_recurring_failures(self):
        """Should return empty list when no recurring failures."""
        entries = [
            {"type": "completed_objective", "score": {"total": 6, "checks": {}}}
        ]
        result = reflection_utils.generate_improvement_challenges(entries)

        self.assertEqual(result, [])


if __name__ == "__main__":
    unittest.main()
