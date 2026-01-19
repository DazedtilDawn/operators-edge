#!/usr/bin/env python3
"""
Tests for effectiveness_analyzer.py

Testing the brain of v8.0 metrics.
"""
import json
import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

# Add hooks directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from effectiveness_analyzer import (
    EffectivenessMetric,
    EffectivenessReport,
    SessionAnalysis,
    calculate_confidence,
    analyze_drift_effectiveness,
    analyze_fix_effectiveness,
    analyze_handoff_effectiveness,
    analyze_context_efficiency,
    generate_recommendations,
    analyze_session,
    load_session_entries,
    format_compact_report,
    format_detailed_report,
)


class TestEffectivenessMetric(unittest.TestCase):
    """Tests for EffectivenessMetric dataclass."""

    def test_display_value(self):
        """Test percentage display formatting."""
        metric = EffectivenessMetric(value=0.75, sample_size=10, confidence=0.8)
        self.assertEqual(metric.display_value, "75%")

    def test_display_value_zero(self):
        """Test zero value display."""
        metric = EffectivenessMetric(value=0.0, sample_size=0, confidence=0.0)
        self.assertEqual(metric.display_value, "0%")

    def test_bar_full(self):
        """Test full bar display."""
        metric = EffectivenessMetric(value=1.0, sample_size=10, confidence=0.9)
        self.assertEqual(metric.bar, "██████████")

    def test_bar_partial(self):
        """Test partial bar display."""
        metric = EffectivenessMetric(value=0.5, sample_size=10, confidence=0.5)
        self.assertEqual(metric.bar, "█████░░░░░")

    def test_bar_empty(self):
        """Test empty bar display."""
        metric = EffectivenessMetric(value=0.0, sample_size=0, confidence=0.0)
        self.assertEqual(metric.bar, "░░░░░░░░░░")


class TestConfidenceCalculation(unittest.TestCase):
    """Tests for confidence calculation."""

    def test_below_minimum(self):
        """Test confidence below minimum samples."""
        conf = calculate_confidence(2)
        self.assertEqual(conf, 0.3)

    def test_at_minimum(self):
        """Test confidence at minimum samples."""
        conf = calculate_confidence(5)
        self.assertEqual(conf, 0.3)

    def test_interpolation(self):
        """Test confidence interpolation."""
        conf = calculate_confidence(17)  # Halfway between 5 and 30
        self.assertGreater(conf, 0.5)
        self.assertLess(conf, 0.8)

    def test_at_ideal(self):
        """Test confidence at ideal samples."""
        conf = calculate_confidence(30)
        self.assertEqual(conf, 0.95)

    def test_above_ideal(self):
        """Test confidence above ideal samples."""
        conf = calculate_confidence(100)
        self.assertEqual(conf, 0.95)


class TestDriftEffectivenessAnalysis(unittest.TestCase):
    """Tests for drift effectiveness analysis."""

    def test_no_signals(self):
        """Test with no signals fired."""
        analyses = [
            SessionAnalysis(
                session_id="test-1",
                started_at=datetime.now(),
                duration_minutes=30,
                drift_signals_fired=0,
                drift_corrections_detected=0
            )
        ]
        metric = analyze_drift_effectiveness(analyses)
        self.assertEqual(metric.value, 0.0)
        self.assertEqual(metric.sample_size, 0)

    def test_perfect_correction(self):
        """Test 100% correction rate."""
        analyses = [
            SessionAnalysis(
                session_id="test-1",
                started_at=datetime.now(),
                duration_minutes=30,
                drift_signals_fired=5,
                drift_corrections_detected=5
            )
        ]
        metric = analyze_drift_effectiveness(analyses)
        self.assertEqual(metric.value, 1.0)
        self.assertEqual(metric.sample_size, 5)

    def test_partial_correction(self):
        """Test partial correction rate."""
        analyses = [
            SessionAnalysis(
                session_id="test-1",
                started_at=datetime.now(),
                duration_minutes=30,
                drift_signals_fired=10,
                drift_corrections_detected=3
            )
        ]
        metric = analyze_drift_effectiveness(analyses)
        self.assertEqual(metric.value, 0.3)
        self.assertEqual(metric.sample_size, 10)

    def test_aggregation_across_sessions(self):
        """Test aggregation across multiple sessions."""
        analyses = [
            SessionAnalysis(
                session_id="test-1",
                started_at=datetime.now(),
                duration_minutes=30,
                drift_signals_fired=4,
                drift_corrections_detected=2
            ),
            SessionAnalysis(
                session_id="test-2",
                started_at=datetime.now(),
                duration_minutes=30,
                drift_signals_fired=6,
                drift_corrections_detected=3
            )
        ]
        metric = analyze_drift_effectiveness(analyses)
        self.assertEqual(metric.value, 0.5)  # 5/10
        self.assertEqual(metric.sample_size, 10)


class TestFixEffectivenessAnalysis(unittest.TestCase):
    """Tests for fix effectiveness analysis."""

    def test_no_fixes(self):
        """Test with no fixes surfaced."""
        analyses = [
            SessionAnalysis(
                session_id="test-1",
                started_at=datetime.now(),
                duration_minutes=30,
                fixes_surfaced=0,
                fixes_followed=0
            )
        ]
        metric = analyze_fix_effectiveness(analyses)
        self.assertEqual(metric.value, 0.0)
        self.assertEqual(metric.sample_size, 0)

    def test_all_fixes_followed(self):
        """Test 100% follow rate."""
        analyses = [
            SessionAnalysis(
                session_id="test-1",
                started_at=datetime.now(),
                duration_minutes=30,
                fixes_surfaced=5,
                fixes_followed=5
            )
        ]
        metric = analyze_fix_effectiveness(analyses)
        self.assertEqual(metric.value, 1.0)


class TestHandoffEffectivenessAnalysis(unittest.TestCase):
    """Tests for handoff effectiveness analysis."""

    def test_no_handoffs_available(self):
        """Test with no handoffs available."""
        analyses = [
            SessionAnalysis(
                session_id="test-1",
                started_at=datetime.now(),
                duration_minutes=30,
                handoff_available=False,
                handoff_used=False
            )
        ]
        metric = analyze_handoff_effectiveness(analyses)
        self.assertEqual(metric.value, 0.0)
        self.assertEqual(metric.sample_size, 0)

    def test_handoff_used(self):
        """Test handoff adoption."""
        analyses = [
            SessionAnalysis(
                session_id="test-1",
                started_at=datetime.now(),
                duration_minutes=30,
                handoff_available=True,
                handoff_used=True
            ),
            SessionAnalysis(
                session_id="test-2",
                started_at=datetime.now(),
                duration_minutes=30,
                handoff_available=True,
                handoff_used=False
            )
        ]
        metric = analyze_handoff_effectiveness(analyses)
        self.assertEqual(metric.value, 0.5)
        self.assertEqual(metric.sample_size, 2)


class TestContextEfficiencyAnalysis(unittest.TestCase):
    """Tests for context efficiency analysis."""

    def test_empty_sessions(self):
        """Test with no sessions."""
        metric = analyze_context_efficiency([])
        self.assertEqual(metric.value, 0.0)

    def test_efficient_context_use(self):
        """Test efficient context usage."""
        analyses = [
            SessionAnalysis(
                session_id="test-1",
                started_at=datetime.now(),
                duration_minutes=30,
                peak_context_usage=0.3,  # Low usage
                tool_calls=50,
                files_modified=15  # High work output
            )
        ]
        metric = analyze_context_efficiency(analyses)
        self.assertGreater(metric.value, 0.5)  # Should be efficient


class TestRecommendations(unittest.TestCase):
    """Tests for recommendation generation."""

    def test_no_recommendations_with_low_confidence(self):
        """Test that low confidence leads to data warning."""
        drift = EffectivenessMetric(value=0.5, sample_size=2, confidence=0.3)
        fix = EffectivenessMetric(value=0.5, sample_size=2, confidence=0.3)
        handoff = EffectivenessMetric(value=0.5, sample_size=2, confidence=0.3)
        context = EffectivenessMetric(value=0.5, sample_size=2, confidence=0.3)

        recs, adj = generate_recommendations(drift, fix, handoff, context, {})
        self.assertTrue(any("Not enough data" in r for r in recs))

    def test_drift_working_well(self):
        """Test positive drift recommendation."""
        drift = EffectivenessMetric(value=0.85, sample_size=30, confidence=0.9)
        fix = EffectivenessMetric(value=0.0, sample_size=0, confidence=0.0)
        handoff = EffectivenessMetric(value=0.0, sample_size=0, confidence=0.0)
        context = EffectivenessMetric(value=0.0, sample_size=0, confidence=0.0)

        recs, adj = generate_recommendations(drift, fix, handoff, context, {"file_churn": 3})
        self.assertTrue(any("working well" in r for r in recs))

    def test_threshold_adjustment_suggested(self):
        """Test that threshold adjustment is suggested when appropriate."""
        drift = EffectivenessMetric(value=0.2, sample_size=30, confidence=0.9)
        fix = EffectivenessMetric(value=0.0, sample_size=0, confidence=0.0)
        handoff = EffectivenessMetric(value=0.0, sample_size=0, confidence=0.0)
        context = EffectivenessMetric(value=0.0, sample_size=0, confidence=0.0)

        recs, adj = generate_recommendations(drift, fix, handoff, context, {"file_churn": 3})
        self.assertIn("file_churn", adj)


class TestSessionLogAnalysis(unittest.TestCase):
    """Tests for session log analysis."""

    def test_empty_log(self):
        """Test analysis of empty log."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.jsonl', delete=False) as f:
            f.write("")
            temp_path = Path(f.name)

        try:
            analysis = analyze_session(temp_path)
            self.assertIsNone(analysis)
        finally:
            temp_path.unlink()

    def test_basic_session(self):
        """Test analysis of basic session."""
        entries = [
            {"timestamp": "2026-01-18T10:00:00", "tool": "Read", "input_preview": {"file": "/app/main.py"}, "success": True},
            {"timestamp": "2026-01-18T10:05:00", "tool": "Edit", "input_preview": {"file_path": "/app/main.py"}, "success": True},
            {"timestamp": "2026-01-18T10:10:00", "tool": "Bash", "input_preview": {"command": "pytest"}, "success": True},
        ]

        with tempfile.NamedTemporaryFile(mode='w', suffix='.jsonl', delete=False) as f:
            for entry in entries:
                f.write(json.dumps(entry) + '\n')
            temp_path = Path(f.name)

        try:
            analysis = analyze_session(temp_path)
            self.assertIsNotNone(analysis)
            self.assertEqual(analysis.tool_calls, 3)
            self.assertEqual(analysis.files_modified, 1)
        finally:
            temp_path.unlink()

    def test_file_churn_detection(self):
        """Test that file churn triggers drift signal."""
        entries = [
            {"timestamp": "2026-01-18T10:00:00", "tool": "Edit", "input_preview": {"file_path": "/app/utils.py"}, "success": True},
            {"timestamp": "2026-01-18T10:02:00", "tool": "Edit", "input_preview": {"file_path": "/app/utils.py"}, "success": True},
            {"timestamp": "2026-01-18T10:04:00", "tool": "Edit", "input_preview": {"file_path": "/app/utils.py"}, "success": True},
            # 4th edit after 5 minutes (correction detected)
            {"timestamp": "2026-01-18T10:15:00", "tool": "Edit", "input_preview": {"file_path": "/app/utils.py"}, "success": True},
        ]

        with tempfile.NamedTemporaryFile(mode='w', suffix='.jsonl', delete=False) as f:
            for entry in entries:
                f.write(json.dumps(entry) + '\n')
            temp_path = Path(f.name)

        try:
            analysis = analyze_session(temp_path)
            self.assertIsNotNone(analysis)
            self.assertGreater(analysis.drift_signals_fired, 0)
            self.assertGreater(analysis.drift_corrections_detected, 0)
        finally:
            temp_path.unlink()


class TestReportFormatting(unittest.TestCase):
    """Tests for report formatting."""

    def test_compact_report_format(self):
        """Test compact report contains key elements."""
        drift = EffectivenessMetric(value=0.8, sample_size=10, confidence=0.9)
        fix = EffectivenessMetric(value=0.5, sample_size=5, confidence=0.5)
        handoff = EffectivenessMetric(value=0.9, sample_size=8, confidence=0.8)
        context = EffectivenessMetric(value=0.7, sample_size=10, confidence=0.9)

        report = EffectivenessReport(
            drift_effectiveness=drift,
            fix_hit_rate=fix,
            handoff_adoption=handoff,
            context_efficiency=context,
            sessions_analyzed=10,
            time_range_days=7,
            avg_session_duration_min=30,
            avg_drift_signals_per_session=2.5,
            recommendations=["Test recommendation"],
        )

        output = format_compact_report(report)
        self.assertIn("EFFECTIVENESS", output)
        self.assertIn("DRIFT", output)
        self.assertIn("sessions", output)

    def test_detailed_report_format(self):
        """Test detailed report contains all sections."""
        drift = EffectivenessMetric(value=0.8, sample_size=10, confidence=0.9)
        fix = EffectivenessMetric(value=0.5, sample_size=5, confidence=0.5)
        handoff = EffectivenessMetric(value=0.9, sample_size=8, confidence=0.8)
        context = EffectivenessMetric(value=0.7, sample_size=10, confidence=0.9)

        report = EffectivenessReport(
            drift_effectiveness=drift,
            fix_hit_rate=fix,
            handoff_adoption=handoff,
            context_efficiency=context,
            sessions_analyzed=10,
            time_range_days=7,
            avg_session_duration_min=30,
            avg_drift_signals_per_session=2.5,
            recommendations=["Test recommendation"],
            threshold_adjustments={"file_churn": 2},
        )

        output = format_detailed_report(report)
        self.assertIn("DETAILED", output)
        self.assertIn("Confidence", output)
        self.assertIn("RECOMMENDATIONS", output)
        self.assertIn("THRESHOLD", output)


class TestReportSerialization(unittest.TestCase):
    """Tests for report serialization."""

    def test_report_to_dict(self):
        """Test report serialization to dict."""
        drift = EffectivenessMetric(value=0.8, sample_size=10, confidence=0.9)
        fix = EffectivenessMetric(value=0.5, sample_size=5, confidence=0.5)
        handoff = EffectivenessMetric(value=0.9, sample_size=8, confidence=0.8)
        context = EffectivenessMetric(value=0.7, sample_size=10, confidence=0.9)

        report = EffectivenessReport(
            drift_effectiveness=drift,
            fix_hit_rate=fix,
            handoff_adoption=handoff,
            context_efficiency=context,
            sessions_analyzed=10,
        )

        d = report.to_dict()
        self.assertIn("drift_effectiveness", d)
        self.assertIn("sessions_analyzed", d)
        self.assertEqual(d["sessions_analyzed"], 10)

        # Should be JSON serializable
        json_str = json.dumps(d)
        self.assertIsInstance(json_str, str)


if __name__ == "__main__":
    unittest.main()
