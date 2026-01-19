#!/usr/bin/env python3
"""
Tests for obligation_utils.py - Mechanical Learning

Tests the Obligation lifecycle:
- Create obligation when lesson surfaced
- Auto-resolve on tool completion
- Explicit dismiss with reason
- Stale obligation cleanup
"""
import json
import tempfile
import unittest
from pathlib import Path
from datetime import datetime, timedelta
from unittest.mock import patch

import obligation_utils
from obligation_utils import (
    Obligation,
    DismissReason,
    create_obligation,
    resolve_obligation,
    get_pending_obligations,
    dismiss_obligation,
    auto_resolve_obligations,
    clear_stale_obligations,
    load_obligations,
    save_obligations,
    log_obligation_event,
    format_obligation_for_display,
    analyze_matching_quality,
    format_matching_quality_report,
)


class TestObligationDataclass(unittest.TestCase):
    """Test the Obligation dataclass."""

    def test_obligation_defaults(self):
        """Obligation should have sensible defaults."""
        ob = Obligation()
        self.assertEqual(ob.status, "pending")
        self.assertEqual(ob.success_window, "same_turn")
        self.assertIsNotNone(ob.id)
        self.assertIsNotNone(ob.created_at)

    def test_obligation_to_dict(self):
        """Obligation should serialize to dict."""
        ob = Obligation(
            lesson_trigger="hooks",
            lesson_text="Policy is not enforcement",
            tool_name="Edit"
        )
        d = ob.to_dict()
        self.assertEqual(d["lesson_trigger"], "hooks")
        self.assertEqual(d["tool_name"], "Edit")
        self.assertEqual(d["status"], "pending")

    def test_obligation_from_dict(self):
        """Obligation should deserialize from dict."""
        d = {
            "id": "test123",
            "lesson_trigger": "hooks",
            "lesson_text": "Test lesson",
            "tool_name": "Edit",
            "status": "applied"
        }
        ob = Obligation.from_dict(d)
        self.assertEqual(ob.id, "test123")
        self.assertEqual(ob.status, "applied")

    def test_obligation_from_dict_ignores_unknown_fields(self):
        """Obligation.from_dict should ignore unknown fields."""
        d = {
            "id": "test123",
            "lesson_trigger": "hooks",
            "unknown_field": "should be ignored"
        }
        ob = Obligation.from_dict(d)
        self.assertEqual(ob.id, "test123")
        self.assertFalse(hasattr(ob, "unknown_field"))


class TestObligationStateManagement(unittest.TestCase):
    """Test obligation state file management."""

    def setUp(self):
        """Create temp directory for state files."""
        self.temp_dir = tempfile.mkdtemp()
        self.state_dir = Path(self.temp_dir) / ".claude" / "state"
        self.state_dir.mkdir(parents=True, exist_ok=True)

        # Patch get_state_dir to use temp directory
        self.patcher = patch.object(
            obligation_utils,
            'get_state_dir',
            return_value=self.state_dir
        )
        self.patcher.start()

    def tearDown(self):
        """Clean up temp directory."""
        self.patcher.stop()
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_load_empty_state(self):
        """load_obligations should return empty list if no file."""
        obligations = load_obligations()
        self.assertEqual(obligations, [])

    def test_save_and_load_obligations(self):
        """Obligations should round-trip through save/load."""
        ob = Obligation(
            id="test1",
            lesson_trigger="hooks",
            lesson_text="Test lesson",
            status="pending"
        )
        save_obligations([ob])
        loaded = load_obligations()
        self.assertEqual(len(loaded), 1)
        self.assertEqual(loaded[0].id, "test1")
        self.assertEqual(loaded[0].lesson_trigger, "hooks")

    def test_save_filters_resolved(self):
        """save_obligations should filter out resolved obligations."""
        ob1 = Obligation(id="pending1", status="pending")
        ob2 = Obligation(id="applied1", status="applied")
        ob3 = Obligation(id="dismissed1", status="dismissed")

        save_obligations([ob1, ob2, ob3])
        loaded = load_obligations()

        self.assertEqual(len(loaded), 1)
        self.assertEqual(loaded[0].id, "pending1")


class TestObligationCRUD(unittest.TestCase):
    """Test obligation CRUD operations."""

    def setUp(self):
        """Create temp directory for state files."""
        self.temp_dir = tempfile.mkdtemp()
        self.state_dir = Path(self.temp_dir) / ".claude" / "state"
        self.state_dir.mkdir(parents=True, exist_ok=True)

        self.patcher = patch.object(
            obligation_utils,
            'get_state_dir',
            return_value=self.state_dir
        )
        self.patcher.start()

    def tearDown(self):
        """Clean up temp directory."""
        self.patcher.stop()
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_create_obligation(self):
        """create_obligation should create and save a pending obligation."""
        ob = create_obligation(
            lesson_trigger="hooks",
            lesson_text="Policy is not enforcement",
            tool_name="Edit",
            tool_input={"file_path": "/test/file.py"},
            session_id="test-session"
        )

        self.assertEqual(ob.status, "pending")
        self.assertEqual(ob.lesson_trigger, "hooks")
        self.assertEqual(ob.tool_name, "Edit")
        self.assertEqual(ob.tool_input_summary, "/test/file.py")

        # Should be persisted
        loaded = load_obligations()
        self.assertEqual(len(loaded), 1)

    def test_resolve_obligation_applied(self):
        """resolve_obligation should mark as applied."""
        ob = create_obligation(
            lesson_trigger="hooks",
            lesson_text="Test",
            tool_name="Edit",
            tool_input={}
        )

        resolved = resolve_obligation(ob.id, "applied", "File edited successfully")

        self.assertEqual(resolved.status, "applied")
        self.assertEqual(resolved.outcome, "File edited successfully")
        self.assertIsNotNone(resolved.resolved_at)

        # Should be removed from pending
        pending = get_pending_obligations()
        self.assertEqual(len(pending), 0)

    def test_resolve_obligation_violated(self):
        """resolve_obligation should mark as violated."""
        ob = create_obligation(
            lesson_trigger="hooks",
            lesson_text="Test",
            tool_name="Edit",
            tool_input={}
        )

        resolved = resolve_obligation(ob.id, "violated", "Edit failed")

        self.assertEqual(resolved.status, "violated")
        self.assertEqual(resolved.outcome, "Edit failed")

    def test_dismiss_obligation(self):
        """dismiss_obligation should mark as dismissed with reason."""
        ob = create_obligation(
            lesson_trigger="hooks",
            lesson_text="Test",
            tool_name="Edit",
            tool_input={}
        )

        dismissed = dismiss_obligation(ob.id, "Not applicable to this edit")

        self.assertEqual(dismissed.status, "dismissed")
        self.assertEqual(dismissed.dismiss_reason, "Not applicable to this edit")

    def test_get_pending_by_tool_name(self):
        """get_pending_obligations should filter by tool name."""
        create_obligation("hooks", "Test1", "Edit", {})
        create_obligation("paths", "Test2", "Bash", {})
        create_obligation("python", "Test3", "Edit", {})

        edit_obligations = get_pending_obligations("Edit")
        bash_obligations = get_pending_obligations("Bash")

        self.assertEqual(len(edit_obligations), 2)
        self.assertEqual(len(bash_obligations), 1)


class TestAutoResolve(unittest.TestCase):
    """Test automatic obligation resolution."""

    def setUp(self):
        """Create temp directory for state files."""
        self.temp_dir = tempfile.mkdtemp()
        self.state_dir = Path(self.temp_dir) / ".claude" / "state"
        self.state_dir.mkdir(parents=True, exist_ok=True)

        self.patcher = patch.object(
            obligation_utils,
            'get_state_dir',
            return_value=self.state_dir
        )
        self.patcher.start()

    def tearDown(self):
        """Clean up temp directory."""
        self.patcher.stop()
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_auto_resolve_on_success(self):
        """auto_resolve_obligations should mark applied on success."""
        ob = create_obligation(
            lesson_trigger="hooks",
            lesson_text="Test",
            tool_name="Edit",
            tool_input={"file_path": "/test/file.py"}
        )

        resolved = auto_resolve_obligations(
            tool_name="Edit",
            success=True,
            tool_input={"file_path": "/test/file.py"}
        )

        self.assertEqual(len(resolved), 1)
        self.assertEqual(resolved[0].status, "applied")

    def test_auto_resolve_on_failure(self):
        """auto_resolve_obligations should mark violated on failure."""
        ob = create_obligation(
            lesson_trigger="hooks",
            lesson_text="Test",
            tool_name="Edit",
            tool_input={"file_path": "/test/file.py"}
        )

        resolved = auto_resolve_obligations(
            tool_name="Edit",
            success=False,
            tool_input={"file_path": "/test/file.py"}
        )

        self.assertEqual(len(resolved), 1)
        self.assertEqual(resolved[0].status, "violated")

    def test_auto_resolve_only_matching_tool(self):
        """auto_resolve_obligations should only resolve matching tool."""
        create_obligation("hooks", "Test1", "Edit", {"file_path": "/a.py"})
        create_obligation("paths", "Test2", "Bash", {"command": "ls"})

        resolved = auto_resolve_obligations(
            tool_name="Edit",
            success=True,
            tool_input={"file_path": "/a.py"}
        )

        # Only Edit obligation should be resolved
        self.assertEqual(len(resolved), 1)

        # Bash obligation should still be pending
        pending = get_pending_obligations("Bash")
        self.assertEqual(len(pending), 1)

    def test_auto_resolve_mismatched_input_as_false_positive(self):
        """Mismatched input should auto-categorize as false_positive."""
        # Lesson surfaced for file_a.py
        create_obligation("hooks", "Test", "Edit", {"file_path": "/file_a.py"})

        # But user actually edited file_b.py
        resolved = auto_resolve_obligations(
            tool_name="Edit",
            success=True,
            tool_input={"file_path": "/file_b.py"}
        )

        self.assertEqual(len(resolved), 1)
        self.assertEqual(resolved[0].status, "dismissed")
        self.assertEqual(resolved[0].dismiss_reason_category, "false_positive")

    def test_auto_resolve_matching_input_as_applied(self):
        """Matching input should resolve as applied."""
        create_obligation("hooks", "Test", "Edit", {"file_path": "/file.py"})

        resolved = auto_resolve_obligations(
            tool_name="Edit",
            success=True,
            tool_input={"file_path": "/file.py"}
        )

        self.assertEqual(len(resolved), 1)
        self.assertEqual(resolved[0].status, "applied")


class TestStaleCleanup(unittest.TestCase):
    """Test stale obligation cleanup."""

    def setUp(self):
        """Create temp directory for state files."""
        self.temp_dir = tempfile.mkdtemp()
        self.state_dir = Path(self.temp_dir) / ".claude" / "state"
        self.state_dir.mkdir(parents=True, exist_ok=True)

        self.patcher = patch.object(
            obligation_utils,
            'get_state_dir',
            return_value=self.state_dir
        )
        self.patcher.start()

    def tearDown(self):
        """Clean up temp directory."""
        self.patcher.stop()
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_clear_stale_obligations(self):
        """clear_stale_obligations should remove old obligations."""
        # Create obligations with old timestamps
        old_time = (datetime.now() - timedelta(hours=48)).isoformat()
        new_time = datetime.now().isoformat()

        old_ob = Obligation(id="old1", created_at=old_time, status="pending")
        new_ob = Obligation(id="new1", created_at=new_time, status="pending")

        save_obligations([old_ob, new_ob])

        cleared = clear_stale_obligations(max_age_hours=24)

        self.assertEqual(len(cleared), 1)

        # Only new obligation should remain
        remaining = load_obligations()
        self.assertEqual(len(remaining), 1)
        self.assertEqual(remaining[0].id, "new1")

    def test_clear_stale_categorizes_as_context_changed(self):
        """clear_stale_obligations should categorize as context_changed."""
        old_time = (datetime.now() - timedelta(hours=48)).isoformat()
        old_ob = Obligation(id="old1", created_at=old_time, status="pending")
        save_obligations([old_ob])

        cleared = clear_stale_obligations(max_age_hours=24)

        self.assertEqual(len(cleared), 1)
        self.assertEqual(cleared[0].status, "dismissed")
        self.assertEqual(cleared[0].dismiss_reason_category, "context_changed")


class TestLoggingHelpers(unittest.TestCase):
    """Test logging helper functions."""

    def test_log_obligation_event(self):
        """log_obligation_event should create proper log entry."""
        ob = Obligation(
            id="test123",
            lesson_trigger="hooks",
            tool_name="Edit",
            status="applied"
        )

        log = log_obligation_event("applied", ob, "session-1")

        self.assertEqual(log["type"], "obligation:applied")
        self.assertEqual(log["obligation_id"], "test123")
        self.assertEqual(log["lesson_trigger"], "hooks")
        self.assertEqual(log["session_id"], "session-1")

    def test_format_obligation_for_display(self):
        """format_obligation_for_display should format correctly."""
        ob = Obligation(
            lesson_trigger="hooks",
            lesson_text="Policy is not enforcement - hooks are enforcement",
            status="applied"
        )

        display = format_obligation_for_display(ob)

        self.assertIn("✅", display)
        self.assertIn("[hooks]", display)
        self.assertIn("Policy is not enforcement", display)

    def test_format_obligation_status_icons(self):
        """format_obligation_for_display should use correct status icons."""
        statuses = [
            ("pending", "⏳"),
            ("applied", "✅"),
            ("dismissed", "❌"),
            ("violated", "⚠️"),
        ]

        for status, expected_icon in statuses:
            ob = Obligation(lesson_trigger="test", lesson_text="Test", status=status)
            display = format_obligation_for_display(ob)
            self.assertIn(expected_icon, display, f"Status {status} should have icon {expected_icon}")


class TestDismissReason(unittest.TestCase):
    """Test DismissReason enum (v3.11.1)."""

    def test_dismiss_reason_values(self):
        """DismissReason should have expected categories."""
        self.assertEqual(DismissReason.FALSE_POSITIVE.value, "false_positive")
        self.assertEqual(DismissReason.WRONG_LESSON.value, "wrong_lesson")
        self.assertEqual(DismissReason.ALREADY_KNEW.value, "already_knew")
        self.assertEqual(DismissReason.CONTEXT_CHANGED.value, "context_changed")
        self.assertEqual(DismissReason.OTHER.value, "other")

    def test_from_string_valid(self):
        """DismissReason.from_string should parse valid values."""
        self.assertEqual(DismissReason.from_string("false_positive"), DismissReason.FALSE_POSITIVE)
        self.assertEqual(DismissReason.from_string("FALSE_POSITIVE"), DismissReason.FALSE_POSITIVE)
        self.assertEqual(DismissReason.from_string("false-positive"), DismissReason.FALSE_POSITIVE)

    def test_from_string_invalid(self):
        """DismissReason.from_string should default to OTHER for invalid."""
        self.assertEqual(DismissReason.from_string("invalid"), DismissReason.OTHER)
        self.assertEqual(DismissReason.from_string(""), DismissReason.OTHER)

    def test_choices(self):
        """DismissReason.choices should return all values."""
        choices = DismissReason.choices()
        self.assertIn("false_positive", choices)
        self.assertIn("wrong_lesson", choices)
        self.assertEqual(len(choices), 5)


class TestDismissWithCategory(unittest.TestCase):
    """Test dismissal with category tracking (v3.11.1)."""

    def setUp(self):
        """Create temp directory for state files."""
        self.temp_dir = tempfile.mkdtemp()
        self.state_dir = Path(self.temp_dir) / ".claude" / "state"
        self.state_dir.mkdir(parents=True, exist_ok=True)

        self.patcher = patch.object(
            obligation_utils,
            'get_state_dir',
            return_value=self.state_dir
        )
        self.patcher.start()

    def tearDown(self):
        """Clean up temp directory."""
        self.patcher.stop()
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_dismiss_with_category(self):
        """dismiss_obligation should accept category."""
        ob = create_obligation("hooks", "Test", "Edit", {})

        dismissed = dismiss_obligation(
            ob.id,
            "Lesson was not relevant",
            category="false_positive"
        )

        self.assertEqual(dismissed.status, "dismissed")
        self.assertEqual(dismissed.dismiss_reason, "Lesson was not relevant")
        self.assertEqual(dismissed.dismiss_reason_category, "false_positive")

    def test_dismiss_without_category_defaults_to_other(self):
        """dismiss_obligation should default to OTHER if no category."""
        ob = create_obligation("hooks", "Test", "Edit", {})

        dismissed = dismiss_obligation(ob.id, "Just because")

        self.assertEqual(dismissed.dismiss_reason_category, "other")

    def test_dismiss_with_invalid_category(self):
        """dismiss_obligation should normalize invalid category to other."""
        ob = create_obligation("hooks", "Test", "Edit", {})

        dismissed = dismiss_obligation(ob.id, "Reason", category="invalid_category")

        self.assertEqual(dismissed.dismiss_reason_category, "other")

    def test_log_includes_category(self):
        """log_obligation_event should include category for dismissals."""
        ob = Obligation(
            id="test123",
            lesson_trigger="hooks",
            tool_name="Edit",
            status="dismissed",
            dismiss_reason="Not relevant",
            dismiss_reason_category="false_positive"
        )

        log = log_obligation_event("dismissed", ob, "session-1")

        self.assertEqual(log["type"], "obligation:dismissed")
        self.assertEqual(log["dismiss_reason_category"], "false_positive")
        self.assertEqual(log["dismiss_reason"], "Not relevant")


class TestMatchingQualityAnalysis(unittest.TestCase):
    """Test matching quality analysis (v3.11.1)."""

    def setUp(self):
        """Create temp directories for state and proof."""
        self.temp_dir = tempfile.mkdtemp()
        self.state_dir = Path(self.temp_dir) / ".claude" / "state"
        self.proof_dir = Path(self.temp_dir) / ".proof"
        self.sessions_dir = self.proof_dir / "sessions"
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.sessions_dir.mkdir(parents=True, exist_ok=True)

        # Patch both state and proof directories
        self.state_patcher = patch.object(
            obligation_utils,
            'get_state_dir',
            return_value=self.state_dir
        )
        self.state_patcher.start()

    def tearDown(self):
        """Clean up temp directory."""
        self.state_patcher.stop()
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _create_session_log(self, session_id: str, entries: list):
        """Helper to create a session log file."""
        log_file = self.sessions_dir / f"{session_id}.jsonl"
        with open(log_file, 'w') as f:
            for entry in entries:
                f.write(json.dumps(entry) + '\n')

    def test_analyze_empty_sessions(self):
        """analyze_matching_quality should handle empty sessions."""
        with patch('proof_utils.get_sessions_dir', return_value=self.sessions_dir):
            analysis = analyze_matching_quality()

        self.assertEqual(analysis["total_surfaced"], 0)
        self.assertEqual(analysis["noise_rate"], 0.0)

    def test_analyze_counts_obligations(self):
        """analyze_matching_quality should count obligation events."""
        session_id = datetime.now().strftime("%Y%m%d-%H%M%S")
        entries = [
            {"type": "obligation:created", "lesson_trigger": "hooks"},
            {"type": "obligation:created", "lesson_trigger": "paths"},
            {"type": "obligation:applied", "lesson_trigger": "hooks"},
            {"type": "obligation:dismissed", "lesson_trigger": "paths",
             "dismiss_reason_category": "false_positive"},
        ]
        self._create_session_log(session_id, entries)

        with patch('proof_utils.get_sessions_dir', return_value=self.sessions_dir):
            analysis = analyze_matching_quality()

        self.assertEqual(analysis["total_surfaced"], 2)
        self.assertEqual(analysis["total_dismissed"], 1)
        self.assertEqual(analysis["by_category"]["false_positive"], 1)

    def test_analyze_calculates_rates(self):
        """analyze_matching_quality should calculate correct rates."""
        session_id = datetime.now().strftime("%Y%m%d-%H%M%S")
        entries = [
            # 10 created
            *[{"type": "obligation:created", "lesson_trigger": f"t{i}"} for i in range(10)],
            # 2 false positives
            {"type": "obligation:dismissed", "dismiss_reason_category": "false_positive"},
            {"type": "obligation:dismissed", "dismiss_reason_category": "false_positive"},
            # 1 wrong lesson
            {"type": "obligation:dismissed", "dismiss_reason_category": "wrong_lesson"},
        ]
        self._create_session_log(session_id, entries)

        with patch('proof_utils.get_sessions_dir', return_value=self.sessions_dir):
            analysis = analyze_matching_quality()

        self.assertEqual(analysis["total_surfaced"], 10)
        self.assertEqual(analysis["false_positive_rate"], 0.2)  # 2/10
        self.assertEqual(analysis["wrong_lesson_rate"], 0.1)    # 1/10
        self.assertEqual(analysis["noise_rate"], 0.3)           # 3/10

    def test_recommendation_insufficient_data(self):
        """Should recommend more data when < 10 obligations."""
        session_id = datetime.now().strftime("%Y%m%d-%H%M%S")
        entries = [
            {"type": "obligation:created", "lesson_trigger": "test"},
        ]
        self._create_session_log(session_id, entries)

        with patch('proof_utils.get_sessions_dir', return_value=self.sessions_dir):
            analysis = analyze_matching_quality()

        self.assertIn("Insufficient data", analysis["recommendation"])

    def test_format_matching_quality_report(self):
        """format_matching_quality_report should produce readable output."""
        with patch('proof_utils.get_sessions_dir', return_value=self.sessions_dir):
            report = format_matching_quality_report()

        self.assertIn("MATCHING QUALITY ANALYSIS", report)
        self.assertIn("False Positive Rate", report)
        self.assertIn("Recommendation", report)


if __name__ == "__main__":
    unittest.main()
