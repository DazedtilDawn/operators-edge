#!/usr/bin/env python3
"""
Unit tests for session_metrics.py (Phase 5)
"""
import json
import os
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch, MagicMock

# Add hooks directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from session_metrics import (
    # Data structures
    DriftMetrics,
    FixMetrics,
    HandoffMetrics,
    ContextMetrics,
    SessionMetrics,
    AggregatedMetrics,
    # In-session tracking
    start_session_metrics,
    get_current_metrics,
    ensure_session_metrics,
    # Event handlers
    record_drift_signal,
    record_drift_response,
    record_fix_surfaced,
    record_fix_followed,
    record_fix_ignored,
    record_fix_learned,
    record_handoff_generated,
    record_handoff_used,
    record_handoff_available_but_not_used,
    record_context_usage,
    record_compression_performed,
    update_context_metrics,
    update_objective_metrics,
    # Persistence
    save_session_metrics,
    load_session_metrics,
    get_recent_sessions,
    # Aggregation
    aggregate_metrics,
    # Formatting
    format_session_summary,
    format_aggregated_summary,
    # Private functions for testing
    _get_metrics_path,
    _load_all_metrics,
    _save_all_metrics,
    _cleanup_old_metrics,
)


class TestDriftMetrics(unittest.TestCase):
    """Tests for DriftMetrics dataclass."""

    def test_default_values(self):
        """Test DriftMetrics has correct defaults."""
        metrics = DriftMetrics()
        self.assertEqual(metrics.signals_fired, {})
        self.assertEqual(metrics.interventions_shown, 0)
        self.assertEqual(metrics.course_corrections, 0)
        self.assertEqual(metrics.ignored_signals, 0)

    def test_to_dict(self):
        """Test serialization to dict."""
        metrics = DriftMetrics(
            signals_fired={"FILE_CHURN": 2, "COMMAND_REPEAT": 1},
            interventions_shown=3,
            course_corrections=2,
            ignored_signals=1
        )
        d = metrics.to_dict()
        self.assertEqual(d["signals_fired"]["FILE_CHURN"], 2)
        self.assertEqual(d["interventions_shown"], 3)

    def test_from_dict(self):
        """Test deserialization from dict."""
        d = {
            "signals_fired": {"STEP_STALL": 1},
            "interventions_shown": 1,
            "course_corrections": 0,
            "ignored_signals": 1
        }
        metrics = DriftMetrics.from_dict(d)
        self.assertEqual(metrics.signals_fired["STEP_STALL"], 1)
        self.assertEqual(metrics.ignored_signals, 1)

    def test_from_dict_handles_missing_keys(self):
        """Test from_dict handles missing keys gracefully."""
        metrics = DriftMetrics.from_dict({})
        self.assertEqual(metrics.signals_fired, {})
        self.assertEqual(metrics.interventions_shown, 0)


class TestFixMetrics(unittest.TestCase):
    """Tests for FixMetrics dataclass."""

    def test_roundtrip(self):
        """Test serialization roundtrip."""
        original = FixMetrics(
            fixes_surfaced=5,
            fixes_followed=3,
            fixes_successful=2,
            fixes_ignored=2,
            new_fixes_learned=1
        )
        d = original.to_dict()
        restored = FixMetrics.from_dict(d)
        self.assertEqual(original.fixes_surfaced, restored.fixes_surfaced)
        self.assertEqual(original.fixes_followed, restored.fixes_followed)
        self.assertEqual(original.fixes_successful, restored.fixes_successful)


class TestHandoffMetrics(unittest.TestCase):
    """Tests for HandoffMetrics dataclass."""

    def test_roundtrip(self):
        """Test serialization roundtrip."""
        original = HandoffMetrics(
            handoff_generated=True,
            handoff_used_by_next=False,
            previous_handoff_available=True,
            previous_handoff_used=True,
            time_to_first_action_seconds=45.5
        )
        d = original.to_dict()
        restored = HandoffMetrics.from_dict(d)
        self.assertEqual(original.handoff_generated, restored.handoff_generated)
        self.assertEqual(original.time_to_first_action_seconds, restored.time_to_first_action_seconds)


class TestContextMetrics(unittest.TestCase):
    """Tests for ContextMetrics dataclass."""

    def test_roundtrip(self):
        """Test serialization roundtrip."""
        original = ContextMetrics(
            peak_usage_percent=85.5,
            final_usage_percent=80.0,
            compression_recommendations=2,
            compressions_performed=1,
            session_duration_minutes=45.0,
            tool_calls_total=100,
            files_read=20,
            files_modified=10
        )
        d = original.to_dict()
        restored = ContextMetrics.from_dict(d)
        self.assertEqual(restored.peak_usage_percent, 85.5)
        self.assertEqual(restored.tool_calls_total, 100)


class TestSessionMetrics(unittest.TestCase):
    """Tests for SessionMetrics dataclass."""

    def test_full_roundtrip(self):
        """Test complete serialization roundtrip."""
        original = SessionMetrics(
            session_id="test-123",
            started_at="2026-01-18T10:00:00",
            ended_at="2026-01-18T11:00:00",
            objective="Test objective",
            drift=DriftMetrics(signals_fired={"FILE_CHURN": 1}),
            fixes=FixMetrics(fixes_surfaced=2),
            handoff=HandoffMetrics(handoff_generated=True),
            context=ContextMetrics(peak_usage_percent=60.0),
            objective_completed=True,
            steps_completed=5,
            steps_total=7
        )
        d = original.to_dict()
        restored = SessionMetrics.from_dict(d)

        self.assertEqual(original.session_id, restored.session_id)
        self.assertEqual(original.objective, restored.objective)
        self.assertEqual(original.drift.signals_fired, restored.drift.signals_fired)
        self.assertEqual(original.fixes.fixes_surfaced, restored.fixes.fixes_surfaced)
        self.assertEqual(original.objective_completed, restored.objective_completed)


class TestInSessionTracking(unittest.TestCase):
    """Tests for in-session metrics tracking."""

    def setUp(self):
        """Reset global state before each test."""
        import session_metrics
        session_metrics._current_session_metrics = None
        session_metrics._peak_context_usage = 0.0

    def test_start_session_metrics(self):
        """Test starting session metrics."""
        metrics = start_session_metrics("test-session", "Test objective")
        self.assertEqual(metrics.session_id, "test-session")
        self.assertEqual(metrics.objective, "Test objective")
        self.assertNotEqual(metrics.started_at, "")

    def test_get_current_metrics(self):
        """Test getting current metrics."""
        self.assertIsNone(get_current_metrics())

        start_session_metrics("test", "obj")
        metrics = get_current_metrics()
        self.assertIsNotNone(metrics)
        self.assertEqual(metrics.session_id, "test")

    def test_ensure_session_metrics_creates_if_needed(self):
        """Test ensure_session_metrics creates metrics if none exist."""
        metrics = ensure_session_metrics("auto-created")
        self.assertIsNotNone(metrics)
        self.assertEqual(metrics.session_id, "auto-created")


class TestDriftEventHandlers(unittest.TestCase):
    """Tests for drift event handlers."""

    def setUp(self):
        import session_metrics
        session_metrics._current_session_metrics = None
        session_metrics._peak_context_usage = 0.0
        start_session_metrics("drift-test", "")

    def test_record_drift_signal(self):
        """Test recording drift signals."""
        record_drift_signal("FILE_CHURN", "warning")
        record_drift_signal("FILE_CHURN", "critical")
        record_drift_signal("COMMAND_REPEAT", "warning")

        metrics = get_current_metrics()
        self.assertEqual(metrics.drift.signals_fired["FILE_CHURN"], 2)
        self.assertEqual(metrics.drift.signals_fired["COMMAND_REPEAT"], 1)
        self.assertEqual(metrics.drift.interventions_shown, 3)

    def test_record_drift_signal_info_not_intervention(self):
        """Test that info-level signals don't count as interventions."""
        record_drift_signal("STEP_STALL", "info")

        metrics = get_current_metrics()
        self.assertEqual(metrics.drift.signals_fired["STEP_STALL"], 1)
        self.assertEqual(metrics.drift.interventions_shown, 0)

    def test_record_drift_response(self):
        """Test recording drift responses."""
        record_drift_response(True)  # Course corrected
        record_drift_response(False)  # Ignored
        record_drift_response(True)  # Course corrected

        metrics = get_current_metrics()
        self.assertEqual(metrics.drift.course_corrections, 2)
        self.assertEqual(metrics.drift.ignored_signals, 1)


class TestFixEventHandlers(unittest.TestCase):
    """Tests for fix event handlers."""

    def setUp(self):
        import session_metrics
        session_metrics._current_session_metrics = None
        session_metrics._peak_context_usage = 0.0
        start_session_metrics("fix-test", "")

    def test_record_fix_surfaced(self):
        """Test recording fix surfaced."""
        record_fix_surfaced()
        record_fix_surfaced()

        metrics = get_current_metrics()
        self.assertEqual(metrics.fixes.fixes_surfaced, 2)

    def test_record_fix_followed(self):
        """Test recording fix followed."""
        record_fix_followed(success=True)
        record_fix_followed(success=False)

        metrics = get_current_metrics()
        self.assertEqual(metrics.fixes.fixes_followed, 2)
        self.assertEqual(metrics.fixes.fixes_successful, 1)

    def test_record_fix_ignored(self):
        """Test recording fix ignored."""
        record_fix_ignored()

        metrics = get_current_metrics()
        self.assertEqual(metrics.fixes.fixes_ignored, 1)

    def test_record_fix_learned(self):
        """Test recording fix learned."""
        record_fix_learned()
        record_fix_learned()

        metrics = get_current_metrics()
        self.assertEqual(metrics.fixes.new_fixes_learned, 2)


class TestHandoffEventHandlers(unittest.TestCase):
    """Tests for handoff event handlers."""

    def setUp(self):
        import session_metrics
        session_metrics._current_session_metrics = None
        session_metrics._peak_context_usage = 0.0
        start_session_metrics("handoff-test", "")

    def test_record_handoff_generated(self):
        """Test recording handoff generated."""
        record_handoff_generated()

        metrics = get_current_metrics()
        self.assertTrue(metrics.handoff.handoff_generated)

    def test_record_handoff_used(self):
        """Test recording handoff used."""
        record_handoff_used(time_to_first_action=30.5)

        metrics = get_current_metrics()
        self.assertTrue(metrics.handoff.previous_handoff_available)
        self.assertTrue(metrics.handoff.previous_handoff_used)
        self.assertEqual(metrics.handoff.time_to_first_action_seconds, 30.5)

    def test_record_handoff_available_but_not_used(self):
        """Test recording handoff available but not used."""
        record_handoff_available_but_not_used()

        metrics = get_current_metrics()
        self.assertTrue(metrics.handoff.previous_handoff_available)
        self.assertFalse(metrics.handoff.previous_handoff_used)


class TestContextEventHandlers(unittest.TestCase):
    """Tests for context event handlers."""

    def setUp(self):
        import session_metrics
        session_metrics._current_session_metrics = None
        session_metrics._peak_context_usage = 0.0
        start_session_metrics("context-test", "")

    def test_record_context_usage_tracks_peak(self):
        """Test that peak usage is tracked correctly."""
        record_context_usage(40.0)
        record_context_usage(70.0)
        record_context_usage(60.0)  # Lower than peak

        metrics = get_current_metrics()
        self.assertEqual(metrics.context.peak_usage_percent, 70.0)

    def test_record_context_usage_compression_recommendations(self):
        """Test tracking compression recommendations."""
        record_context_usage(60.0, recommended_compression=False)
        record_context_usage(80.0, recommended_compression=True)
        record_context_usage(85.0, recommended_compression=True)

        metrics = get_current_metrics()
        self.assertEqual(metrics.context.compression_recommendations, 2)

    def test_record_compression_performed(self):
        """Test recording compression performed."""
        record_compression_performed()

        metrics = get_current_metrics()
        self.assertEqual(metrics.context.compressions_performed, 1)

    def test_update_context_metrics(self):
        """Test updating context metrics at session end."""
        update_context_metrics(
            duration_minutes=45.0,
            tool_calls=100,
            files_read=20,
            files_modified=10,
            final_usage=75.0
        )

        metrics = get_current_metrics()
        self.assertEqual(metrics.context.session_duration_minutes, 45.0)
        self.assertEqual(metrics.context.tool_calls_total, 100)
        self.assertEqual(metrics.context.files_read, 20)
        self.assertEqual(metrics.context.files_modified, 10)
        self.assertEqual(metrics.context.final_usage_percent, 75.0)


class TestObjectiveMetrics(unittest.TestCase):
    """Tests for objective metrics tracking."""

    def setUp(self):
        import session_metrics
        session_metrics._current_session_metrics = None
        session_metrics._peak_context_usage = 0.0
        start_session_metrics("objective-test", "Test objective")

    def test_update_objective_metrics(self):
        """Test updating objective metrics."""
        update_objective_metrics(completed=True, steps_done=5, steps_total=7)

        metrics = get_current_metrics()
        self.assertTrue(metrics.objective_completed)
        self.assertEqual(metrics.steps_completed, 5)
        self.assertEqual(metrics.steps_total, 7)


class TestMetricsPersistence(unittest.TestCase):
    """Tests for metrics persistence."""

    def setUp(self):
        import session_metrics
        session_metrics._current_session_metrics = None
        session_metrics._peak_context_usage = 0.0
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_save_and_load_session_metrics(self):
        """Test saving and loading session metrics."""
        with patch('session_metrics._get_metrics_path') as mock_path:
            metrics_file = Path(self.temp_dir) / "test_metrics.json"
            mock_path.return_value = metrics_file

            # Create and save metrics
            start_session_metrics("persist-test", "Test objective")
            record_drift_signal("FILE_CHURN", "warning")
            record_fix_surfaced()
            save_session_metrics()

            # Load and verify
            loaded = load_session_metrics("persist-test")
            self.assertIsNotNone(loaded)
            self.assertEqual(loaded.session_id, "persist-test")
            self.assertEqual(loaded.drift.signals_fired.get("FILE_CHURN"), 1)

    def test_get_recent_sessions(self):
        """Test getting recent sessions."""
        with patch('session_metrics._get_metrics_path') as mock_path:
            metrics_file = Path(self.temp_dir) / "test_metrics.json"
            mock_path.return_value = metrics_file

            import session_metrics

            # Create multiple sessions
            for i in range(3):
                session_metrics._current_session_metrics = None
                start_session_metrics(f"session-{i}", f"Objective {i}")
                save_session_metrics()

            # Get recent sessions
            recent = get_recent_sessions(limit=2)
            self.assertEqual(len(recent), 2)


class TestMetricsAggregation(unittest.TestCase):
    """Tests for metrics aggregation."""

    def test_aggregate_empty_list(self):
        """Test aggregating empty list."""
        agg = aggregate_metrics([])
        self.assertEqual(agg.sessions_analyzed, 0)

    def test_aggregate_drift_metrics(self):
        """Test aggregating drift metrics."""
        sessions = [
            SessionMetrics(
                session_id="s1",
                started_at="2026-01-18T10:00:00",
                drift=DriftMetrics(
                    signals_fired={"FILE_CHURN": 2},
                    course_corrections=1
                )
            ),
            SessionMetrics(
                session_id="s2",
                started_at="2026-01-18T11:00:00",
                drift=DriftMetrics(
                    signals_fired={"COMMAND_REPEAT": 1},
                    course_corrections=1
                )
            ),
        ]
        agg = aggregate_metrics(sessions)

        self.assertEqual(agg.total_drift_signals, 3)
        self.assertEqual(agg.total_course_corrections, 2)
        self.assertAlmostEqual(agg.drift_effectiveness_rate, 2/3, places=2)

    def test_aggregate_fix_metrics(self):
        """Test aggregating fix metrics."""
        sessions = [
            SessionMetrics(
                session_id="s1",
                started_at="2026-01-18T10:00:00",
                fixes=FixMetrics(
                    fixes_surfaced=4,
                    fixes_followed=2,
                    fixes_successful=2
                )
            ),
            SessionMetrics(
                session_id="s2",
                started_at="2026-01-18T11:00:00",
                fixes=FixMetrics(
                    fixes_surfaced=2,
                    fixes_followed=1,
                    fixes_successful=0
                )
            ),
        ]
        agg = aggregate_metrics(sessions)

        self.assertEqual(agg.total_fixes_surfaced, 6)
        self.assertEqual(agg.total_fixes_followed, 3)
        self.assertEqual(agg.fix_follow_rate, 0.5)
        self.assertAlmostEqual(agg.fix_success_rate, 2/3, places=2)

    def test_aggregate_handoff_metrics(self):
        """Test aggregating handoff metrics."""
        sessions = [
            SessionMetrics(
                session_id="s1",
                started_at="2026-01-18T10:00:00",
                handoff=HandoffMetrics(
                    handoff_generated=True,
                    previous_handoff_available=True,
                    previous_handoff_used=True,
                    time_to_first_action_seconds=30.0
                )
            ),
            SessionMetrics(
                session_id="s2",
                started_at="2026-01-18T11:00:00",
                handoff=HandoffMetrics(
                    handoff_generated=True,
                    previous_handoff_available=True,
                    previous_handoff_used=False,
                )
            ),
        ]
        agg = aggregate_metrics(sessions)

        self.assertEqual(agg.handoffs_generated, 2)
        self.assertEqual(agg.handoffs_used, 1)
        self.assertEqual(agg.handoff_adoption_rate, 0.5)
        self.assertEqual(agg.avg_time_to_first_action, 30.0)

    def test_aggregate_context_metrics(self):
        """Test aggregating context metrics."""
        sessions = [
            SessionMetrics(
                session_id="s1",
                started_at="2026-01-18T10:00:00",
                context=ContextMetrics(
                    peak_usage_percent=60.0,
                    session_duration_minutes=30.0,
                    compression_recommendations=1
                )
            ),
            SessionMetrics(
                session_id="s2",
                started_at="2026-01-18T11:00:00",
                context=ContextMetrics(
                    peak_usage_percent=80.0,
                    session_duration_minutes=60.0,
                    compression_recommendations=2
                )
            ),
        ]
        agg = aggregate_metrics(sessions)

        self.assertEqual(agg.avg_context_usage, 70.0)
        self.assertEqual(agg.avg_session_duration, 45.0)
        self.assertEqual(agg.compression_recommendation_rate, 1.5)

    def test_aggregate_objective_metrics(self):
        """Test aggregating objective metrics."""
        sessions = [
            SessionMetrics(
                session_id="s1",
                started_at="2026-01-18T10:00:00",
                objective_completed=True,
                steps_completed=5,
                steps_total=5
            ),
            SessionMetrics(
                session_id="s2",
                started_at="2026-01-18T11:00:00",
                objective_completed=False,
                steps_completed=3,
                steps_total=7
            ),
        ]
        agg = aggregate_metrics(sessions)

        self.assertEqual(agg.objectives_completed, 1)
        self.assertEqual(agg.completion_rate, 0.5)
        self.assertEqual(agg.avg_steps_per_session, 4.0)


class TestMetricsFormatting(unittest.TestCase):
    """Tests for metrics formatting."""

    def test_format_session_summary(self):
        """Test session summary formatting."""
        metrics = SessionMetrics(
            session_id="format-test",
            started_at="2026-01-18T10:00:00",
            objective="Test objective",
            drift=DriftMetrics(
                signals_fired={"FILE_CHURN": 2},
                interventions_shown=2,
                course_corrections=1
            ),
            fixes=FixMetrics(fixes_surfaced=3, fixes_followed=2),
            context=ContextMetrics(
                peak_usage_percent=65.0,
                session_duration_minutes=30.0,
                tool_calls_total=50
            ),
            objective_completed=True,
            steps_completed=5,
            steps_total=7
        )
        summary = format_session_summary(metrics)

        self.assertIn("format-test", summary)
        self.assertIn("Test objective", summary)
        self.assertIn("5/7", summary)
        self.assertIn("Drift Detection", summary)
        self.assertIn("Known Fixes", summary)

    def test_format_aggregated_summary(self):
        """Test aggregated summary formatting."""
        agg = AggregatedMetrics(
            sessions_analyzed=10,
            total_drift_signals=20,
            total_course_corrections=15,
            drift_effectiveness_rate=0.75,
            total_fixes_surfaced=30,
            fix_follow_rate=0.6,
            completion_rate=0.8
        )
        summary = format_aggregated_summary(agg)

        self.assertIn("EFFECTIVENESS REPORT", summary)
        self.assertIn("10", summary)  # sessions analyzed
        self.assertIn("75%", summary)  # drift effectiveness


class TestCleanupOldMetrics(unittest.TestCase):
    """Tests for metrics cleanup."""

    def test_cleanup_removes_old_sessions(self):
        """Test that cleanup removes old sessions."""
        data = {"sessions": {}, "metadata": {"version": 1}}

        # Add 60 sessions (more than MAX_SESSIONS=50)
        for i in range(60):
            data["sessions"][f"session-{i:02d}"] = {
                "session_id": f"session-{i:02d}",
                "started_at": f"2026-01-{i%28+1:02d}T10:00:00"
            }

        cleaned = _cleanup_old_metrics(data)
        self.assertLessEqual(len(cleaned["sessions"]), 50)


if __name__ == '__main__':
    unittest.main()
