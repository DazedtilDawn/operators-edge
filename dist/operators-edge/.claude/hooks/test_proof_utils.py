#!/usr/bin/env python3
"""
Tests for proof_utils.py - Resilient Proof Logging

Tests the core guarantees:
1. Atomic proof logging
2. Session isolation
3. Recovery from missing/corrupted logs
4. Graceful fallback (user never trapped)
5. Backward compatibility
"""

import json
import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch, MagicMock

# Add hooks directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


class TestSessionManagement(unittest.TestCase):
    """Tests for session ID management."""

    def test_get_sessions_dir(self):
        """get_sessions_dir() returns .proof/sessions path."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch('proof_utils.get_proof_dir') as mock_proof:
                mock_proof.return_value = Path(tmpdir) / ".proof"
                from proof_utils import get_sessions_dir

                result = get_sessions_dir()

                self.assertEqual(result, Path(tmpdir) / ".proof" / "sessions")

    def test_get_current_session_id_from_file(self):
        """get_current_session_id() reads from session_id file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            state_dir = Path(tmpdir) / ".claude" / "state"
            state_dir.mkdir(parents=True)
            (state_dir / "session_id").write_text("20260113-120000")

            with patch('proof_utils.get_state_dir') as mock_state:
                mock_state.return_value = state_dir
                from proof_utils import get_current_session_id

                result = get_current_session_id()

                self.assertEqual(result, "20260113-120000")

    def test_get_current_session_id_fallback(self):
        """get_current_session_id() generates timestamp if file missing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            state_dir = Path(tmpdir) / ".claude" / "state"
            state_dir.mkdir(parents=True)
            # Don't create session_id file

            with patch('proof_utils.get_state_dir') as mock_state:
                mock_state.return_value = state_dir
                from proof_utils import get_current_session_id

                result = get_current_session_id()

                # Should be a timestamp format
                self.assertRegex(result, r"\d{8}-\d{6}")


class TestAtomicLogging(unittest.TestCase):
    """Tests for atomic proof logging."""

    def test_log_proof_entry_creates_file(self):
        """log_proof_entry() creates session log file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            proof_dir = Path(tmpdir) / ".proof"
            state_dir = Path(tmpdir) / ".claude" / "state"
            state_dir.mkdir(parents=True)
            (state_dir / "session_id").write_text("test-session")

            with patch('proof_utils.get_proof_dir') as mock_proof, \
                 patch('proof_utils.get_state_dir') as mock_state:
                mock_proof.return_value = proof_dir
                mock_state.return_value = state_dir

                from proof_utils import log_proof_entry

                entry = log_proof_entry("Bash", {"command": "ls"}, "output", True)

                # Check file was created
                log_path = proof_dir / "sessions" / "test-session.jsonl"
                self.assertTrue(log_path.exists())

                # Check entry has required fields
                self.assertIn("timestamp", entry)
                self.assertEqual(entry["tool"], "Bash")
                self.assertEqual(entry["success"], True)

    def test_log_proof_entry_appends(self):
        """Multiple log_proof_entry() calls append to same file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            proof_dir = Path(tmpdir) / ".proof"
            state_dir = Path(tmpdir) / ".claude" / "state"
            state_dir.mkdir(parents=True)
            (state_dir / "session_id").write_text("test-session")

            with patch('proof_utils.get_proof_dir') as mock_proof, \
                 patch('proof_utils.get_state_dir') as mock_state:
                mock_proof.return_value = proof_dir
                mock_state.return_value = state_dir

                from proof_utils import log_proof_entry

                log_proof_entry("Bash", "cmd1", "out1", True)
                log_proof_entry("Edit", "cmd2", "out2", True)
                log_proof_entry("Read", "cmd3", "out3", True)

                log_path = proof_dir / "sessions" / "test-session.jsonl"
                content = log_path.read_text()
                lines = [l for l in content.strip().split('\n') if l]

                self.assertEqual(len(lines), 3)

    def test_log_proof_entry_preserves_dict_input(self):
        """Dict inputs are preserved in log entry."""
        with tempfile.TemporaryDirectory() as tmpdir:
            proof_dir = Path(tmpdir) / ".proof"
            state_dir = Path(tmpdir) / ".claude" / "state"
            state_dir.mkdir(parents=True)
            (state_dir / "session_id").write_text("test-session")

            with patch('proof_utils.get_proof_dir') as mock_proof, \
                 patch('proof_utils.get_state_dir') as mock_state:
                mock_proof.return_value = proof_dir
                mock_state.return_value = state_dir

                from proof_utils import log_proof_entry

                input_dict = {"old_string": "foo", "new_string": "bar"}
                entry = log_proof_entry("Edit", input_dict, "success", True)

                self.assertEqual(entry["input_preview"], input_dict)


class TestProofVerification(unittest.TestCase):
    """Tests for proof verification."""

    def test_check_proof_for_session_exists(self):
        """check_proof_for_session() returns True when log exists."""
        with tempfile.TemporaryDirectory() as tmpdir:
            proof_dir = Path(tmpdir) / ".proof"
            sessions_dir = proof_dir / "sessions"
            sessions_dir.mkdir(parents=True)

            # Create log with entries
            log_file = sessions_dir / "test-session.jsonl"
            log_file.write_text('{"timestamp": "2026-01-13", "tool": "Bash", "success": true}\n')

            state_dir = Path(tmpdir) / ".claude" / "state"
            state_dir.mkdir(parents=True)
            (state_dir / "session_id").write_text("test-session")

            with patch('proof_utils.get_proof_dir') as mock_proof, \
                 patch('proof_utils.get_state_dir') as mock_state:
                mock_proof.return_value = proof_dir
                mock_state.return_value = state_dir

                from proof_utils import check_proof_for_session

                exists, msg, count = check_proof_for_session("test-session")

                self.assertTrue(exists)
                self.assertEqual(count, 1)

    def test_check_proof_for_session_missing(self):
        """check_proof_for_session() returns False when log missing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            proof_dir = Path(tmpdir) / ".proof"
            sessions_dir = proof_dir / "sessions"
            sessions_dir.mkdir(parents=True)
            # Don't create log file

            state_dir = Path(tmpdir) / ".claude" / "state"
            state_dir.mkdir(parents=True)
            (state_dir / "session_id").write_text("test-session")

            with patch('proof_utils.get_proof_dir') as mock_proof, \
                 patch('proof_utils.get_state_dir') as mock_state:
                mock_proof.return_value = proof_dir
                mock_state.return_value = state_dir

                from proof_utils import check_proof_for_session

                exists, msg, count = check_proof_for_session("test-session")

                self.assertFalse(exists)
                self.assertEqual(count, 0)


class TestRecoveryMechanism(unittest.TestCase):
    """Tests for proof recovery from state changes."""

    def test_recover_proof_from_state_change(self):
        """recover_proof_from_state() creates entry when state changed."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir = Path(tmpdir)
            proof_dir = project_dir / ".proof"
            state_dir = project_dir / ".claude" / "state"
            state_dir.mkdir(parents=True)
            (state_dir / "session_id").write_text("test-session")

            # Create state file
            yaml_file = project_dir / "active_context.yaml"
            yaml_file.write_text("objective: test\n")

            # Save different start hash
            start_hash = "different_hash_from_start"
            (state_dir / "session_start_hash").write_text(start_hash)

            with patch('proof_utils.get_project_dir') as mock_proj, \
                 patch('proof_utils.get_proof_dir') as mock_proof, \
                 patch('proof_utils.get_state_dir') as mock_state, \
                 patch('proof_utils.get_start_hash') as mock_hash:
                mock_proj.return_value = project_dir
                mock_proof.return_value = proof_dir
                mock_state.return_value = state_dir
                mock_hash.return_value = start_hash

                from proof_utils import recover_proof_from_state

                recovered, msg = recover_proof_from_state()

                self.assertTrue(recovered)
                self.assertIn("recovered", msg.lower())

                # Check recovery entry was created
                log_path = proof_dir / "sessions" / "test-session.jsonl"
                self.assertTrue(log_path.exists())

    def test_recover_proof_no_state_change(self):
        """recover_proof_from_state() fails when state unchanged."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir = Path(tmpdir)
            state_dir = project_dir / ".claude" / "state"
            state_dir.mkdir(parents=True)
            (state_dir / "session_id").write_text("test-session")

            # Create state file and capture its hash
            yaml_file = project_dir / "active_context.yaml"
            yaml_file.write_text("objective: test\n")

            import hashlib
            actual_hash = hashlib.sha256(yaml_file.read_bytes()).hexdigest()

            with patch('proof_utils.get_project_dir') as mock_proj, \
                 patch('proof_utils.get_state_dir') as mock_state, \
                 patch('proof_utils.get_start_hash') as mock_hash:
                mock_proj.return_value = project_dir
                mock_state.return_value = state_dir
                mock_hash.return_value = actual_hash  # Same hash = no change

                from proof_utils import recover_proof_from_state

                recovered, msg = recover_proof_from_state()

                self.assertFalse(recovered)


class TestGracefulFallback(unittest.TestCase):
    """Tests for graceful fallback - user should NEVER be trapped."""

    def test_graceful_fallback_allows_when_state_changed(self):
        """graceful_fallback() allows exit when state was modified."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir = Path(tmpdir)
            state_dir = project_dir / ".claude" / "state"
            state_dir.mkdir(parents=True)

            # Create state file
            yaml_file = project_dir / "active_context.yaml"
            yaml_file.write_text("objective: test\n")

            with patch('proof_utils.get_project_dir') as mock_proj, \
                 patch('proof_utils.get_start_hash') as mock_hash:
                mock_proj.return_value = project_dir
                mock_hash.return_value = "different_hash"  # Different = changed

                from proof_utils import graceful_fallback

                should_allow, msg = graceful_fallback()

                self.assertTrue(should_allow)
                self.assertIn("WARNING", msg)

    def test_graceful_fallback_allows_when_no_session_tracking(self):
        """graceful_fallback() allows exit when session wasn't tracked."""
        with patch('proof_utils.get_start_hash') as mock_hash:
            mock_hash.return_value = None  # No session tracking

            from proof_utils import graceful_fallback

            should_allow, msg = graceful_fallback()

            self.assertTrue(should_allow)


class TestSessionIsolation(unittest.TestCase):
    """Tests for session isolation."""

    def test_different_sessions_different_files(self):
        """Each session gets its own log file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            proof_dir = Path(tmpdir) / ".proof"
            state_dir = Path(tmpdir) / ".claude" / "state"
            state_dir.mkdir(parents=True)

            with patch('proof_utils.get_proof_dir') as mock_proof, \
                 patch('proof_utils.get_state_dir') as mock_state:
                mock_proof.return_value = proof_dir
                mock_state.return_value = state_dir

                from proof_utils import get_session_log_path

                # Session 1
                (state_dir / "session_id").write_text("session-001")
                path1 = get_session_log_path()

                # Session 2
                (state_dir / "session_id").write_text("session-002")
                path2 = get_session_log_path()

                self.assertNotEqual(path1, path2)
                self.assertIn("session-001", str(path1))
                self.assertIn("session-002", str(path2))


class TestSessionLifecycle(unittest.TestCase):
    """Tests for session initialization and archival."""

    def test_initialize_proof_session(self):
        """initialize_proof_session() creates session log."""
        with tempfile.TemporaryDirectory() as tmpdir:
            proof_dir = Path(tmpdir) / ".proof"
            state_dir = Path(tmpdir) / ".claude" / "state"
            state_dir.mkdir(parents=True)

            with patch('proof_utils.get_proof_dir') as mock_proof, \
                 patch('proof_utils.get_state_dir') as mock_state:
                mock_proof.return_value = proof_dir
                mock_state.return_value = state_dir

                from proof_utils import initialize_proof_session

                session_id = initialize_proof_session("test-init-session")

                self.assertEqual(session_id, "test-init-session")

                # Check session ID was saved
                saved_id = (state_dir / "session_id").read_text()
                self.assertEqual(saved_id, "test-init-session")

                # Check sessions dir exists
                self.assertTrue((proof_dir / "sessions").exists())

    def test_archive_old_sessions(self):
        """archive_old_sessions() removes old session logs."""
        with tempfile.TemporaryDirectory() as tmpdir:
            proof_dir = Path(tmpdir) / ".proof"
            sessions_dir = proof_dir / "sessions"
            sessions_dir.mkdir(parents=True)

            # Create old session (8 days ago)
            old_date = datetime.now() - timedelta(days=8)
            old_session_id = old_date.strftime("%Y%m%d-%H%M%S")
            old_log = sessions_dir / f"{old_session_id}.jsonl"
            old_log.write_text('{"timestamp": "old", "tool": "Test", "success": true}\n')

            # Create recent session (1 day ago)
            recent_date = datetime.now() - timedelta(days=1)
            recent_session_id = recent_date.strftime("%Y%m%d-%H%M%S")
            recent_log = sessions_dir / f"{recent_session_id}.jsonl"
            recent_log.write_text('{"timestamp": "recent", "tool": "Test", "success": true}\n')

            with patch('proof_utils.get_proof_dir') as mock_proof, \
                 patch('archive_utils.log_to_archive'):  # Mock archive to avoid dependency
                mock_proof.return_value = proof_dir

                from proof_utils import archive_old_sessions

                archived = archive_old_sessions(days_threshold=7)

                self.assertEqual(archived, 1)
                self.assertFalse(old_log.exists())  # Old log removed
                self.assertTrue(recent_log.exists())  # Recent log kept


class TestProofValidation(unittest.TestCase):
    """Tests for proof integrity validation."""

    def test_validate_proof_integrity_valid(self):
        """validate_proof_integrity() returns True for valid log."""
        with tempfile.TemporaryDirectory() as tmpdir:
            proof_dir = Path(tmpdir) / ".proof"
            sessions_dir = proof_dir / "sessions"
            sessions_dir.mkdir(parents=True)
            state_dir = Path(tmpdir) / ".claude" / "state"
            state_dir.mkdir(parents=True)
            (state_dir / "session_id").write_text("test-session")

            # Create valid log
            log_file = sessions_dir / "test-session.jsonl"
            entries = [
                {"timestamp": "2026-01-13T10:00:00", "tool": "Bash", "success": True},
                {"timestamp": "2026-01-13T10:01:00", "tool": "Edit", "success": True},
            ]
            log_file.write_text('\n'.join(json.dumps(e) for e in entries) + '\n')

            with patch('proof_utils.get_proof_dir') as mock_proof, \
                 patch('proof_utils.get_state_dir') as mock_state:
                mock_proof.return_value = proof_dir
                mock_state.return_value = state_dir

                from proof_utils import validate_proof_integrity

                valid, issues = validate_proof_integrity("test-session")

                self.assertTrue(valid)
                self.assertEqual(len(issues), 0)

    def test_validate_proof_integrity_invalid_json(self):
        """validate_proof_integrity() detects invalid JSON."""
        with tempfile.TemporaryDirectory() as tmpdir:
            proof_dir = Path(tmpdir) / ".proof"
            sessions_dir = proof_dir / "sessions"
            sessions_dir.mkdir(parents=True)
            state_dir = Path(tmpdir) / ".claude" / "state"
            state_dir.mkdir(parents=True)
            (state_dir / "session_id").write_text("test-session")

            # Create log with invalid JSON
            log_file = sessions_dir / "test-session.jsonl"
            log_file.write_text('{"valid": true}\nnot valid json\n')

            with patch('proof_utils.get_proof_dir') as mock_proof, \
                 patch('proof_utils.get_state_dir') as mock_state:
                mock_proof.return_value = proof_dir
                mock_state.return_value = state_dir

                from proof_utils import validate_proof_integrity

                valid, issues = validate_proof_integrity("test-session")

                self.assertFalse(valid)
                self.assertTrue(any("Invalid JSON" in issue for issue in issues))


class TestProofVitality(unittest.TestCase):
    """Tests for proof-grounded memory vitality (v3.10.1)."""

    def test_get_proof_vitality_no_sessions(self):
        """get_proof_vitality() returns zero when no sessions dir."""
        with tempfile.TemporaryDirectory() as tmpdir:
            proof_dir = Path(tmpdir) / ".proof"
            # Don't create sessions dir

            with patch('proof_utils.get_sessions_dir') as mock_sessions:
                mock_sessions.return_value = proof_dir / "sessions"

                from proof_utils import get_proof_vitality

                result = get_proof_vitality("hooks")

                self.assertEqual(result["matches"], 0)
                self.assertIsNone(result["last_match"])
                self.assertEqual(result["sessions"], [])

    def test_get_proof_vitality_finds_matches(self):
        """get_proof_vitality() finds lesson_match entries in proof logs."""
        with tempfile.TemporaryDirectory() as tmpdir:
            sessions_dir = Path(tmpdir) / ".proof" / "sessions"
            sessions_dir.mkdir(parents=True)

            # Create a session log with lesson_match entries
            session_id = datetime.now().strftime("%Y%m%d-%H%M%S")
            log_file = sessions_dir / f"{session_id}.jsonl"

            entries = [
                {"timestamp": "2026-01-13T10:00:00", "tool": "lesson_match",
                 "input_preview": {"triggers": ["hooks", "paths"], "context": "Edit foo.py"}, "success": True},
                {"timestamp": "2026-01-13T10:01:00", "tool": "Bash",
                 "input_preview": "ls", "success": True},
                {"timestamp": "2026-01-13T10:02:00", "tool": "lesson_match",
                 "input_preview": {"triggers": ["hooks"], "context": "Edit bar.py"}, "success": True},
            ]
            log_file.write_text('\n'.join(json.dumps(e) for e in entries) + '\n')

            with patch('proof_utils.get_sessions_dir') as mock_sessions:
                mock_sessions.return_value = sessions_dir

                from proof_utils import get_proof_vitality

                result = get_proof_vitality("hooks")

                self.assertEqual(result["matches"], 2)  # Found in 2 lesson_match entries
                self.assertEqual(result["last_match"], "2026-01-13T10:02:00")
                self.assertEqual(len(result["sessions"]), 1)

    def test_get_proof_vitality_respects_lookback(self):
        """get_proof_vitality() only checks sessions within lookback period."""
        with tempfile.TemporaryDirectory() as tmpdir:
            sessions_dir = Path(tmpdir) / ".proof" / "sessions"
            sessions_dir.mkdir(parents=True)

            # Create an old session (20 days ago)
            old_date = datetime.now() - timedelta(days=20)
            old_session_id = old_date.strftime("%Y%m%d-%H%M%S")
            old_log = sessions_dir / f"{old_session_id}.jsonl"
            old_log.write_text(json.dumps({
                "timestamp": old_date.isoformat(), "tool": "lesson_match",
                "input_preview": {"triggers": ["old_trigger"], "context": "old"}, "success": True
            }) + '\n')

            # Create a recent session (2 days ago)
            recent_date = datetime.now() - timedelta(days=2)
            recent_session_id = recent_date.strftime("%Y%m%d-%H%M%S")
            recent_log = sessions_dir / f"{recent_session_id}.jsonl"
            recent_log.write_text(json.dumps({
                "timestamp": recent_date.isoformat(), "tool": "lesson_match",
                "input_preview": {"triggers": ["recent_trigger"], "context": "recent"}, "success": True
            }) + '\n')

            with patch('proof_utils.get_sessions_dir') as mock_sessions:
                mock_sessions.return_value = sessions_dir

                from proof_utils import get_proof_vitality

                # With 14-day lookback, old trigger should not be found
                result_old = get_proof_vitality("old_trigger", days_lookback=14)
                self.assertEqual(result_old["matches"], 0)

                # Recent trigger should be found
                result_recent = get_proof_vitality("recent_trigger", days_lookback=14)
                self.assertEqual(result_recent["matches"], 1)

    def test_check_lesson_vitality_above_threshold(self):
        """check_lesson_vitality() returns True when matches >= threshold."""
        with tempfile.TemporaryDirectory() as tmpdir:
            sessions_dir = Path(tmpdir) / ".proof" / "sessions"
            sessions_dir.mkdir(parents=True)

            session_id = datetime.now().strftime("%Y%m%d-%H%M%S")
            log_file = sessions_dir / f"{session_id}.jsonl"
            log_file.write_text(json.dumps({
                "timestamp": datetime.now().isoformat(), "tool": "lesson_match",
                "input_preview": {"triggers": ["vital_trigger"], "context": "test"}, "success": True
            }) + '\n')

            with patch('proof_utils.get_sessions_dir') as mock_sessions:
                mock_sessions.return_value = sessions_dir

                from proof_utils import check_lesson_vitality

                is_vital, reason = check_lesson_vitality("vital_trigger", threshold=1)

                self.assertTrue(is_vital)
                self.assertIn("1 matches", reason)

    def test_check_lesson_vitality_below_threshold(self):
        """check_lesson_vitality() returns False when matches < threshold."""
        with tempfile.TemporaryDirectory() as tmpdir:
            sessions_dir = Path(tmpdir) / ".proof" / "sessions"
            sessions_dir.mkdir(parents=True)
            # Empty sessions dir

            with patch('proof_utils.get_sessions_dir') as mock_sessions:
                mock_sessions.return_value = sessions_dir

                from proof_utils import check_lesson_vitality

                is_vital, reason = check_lesson_vitality("nonexistent_trigger", threshold=1)

                self.assertFalse(is_vital)
                self.assertIn("0 matches", reason)


class TestBackwardCompatibility(unittest.TestCase):
    """Tests for backward compatibility with legacy session_log.jsonl."""

    def test_check_proof_falls_back_to_legacy(self):
        """check_proof_for_session() falls back to legacy log."""
        with tempfile.TemporaryDirectory() as tmpdir:
            proof_dir = Path(tmpdir) / ".proof"
            proof_dir.mkdir(parents=True)

            # Create legacy log (not in sessions/)
            legacy_log = proof_dir / "session_log.jsonl"
            legacy_log.write_text('{"timestamp": "legacy", "tool": "Bash", "success": true}\n')

            # No session-specific log
            sessions_dir = proof_dir / "sessions"
            sessions_dir.mkdir(parents=True)

            state_dir = Path(tmpdir) / ".claude" / "state"
            state_dir.mkdir(parents=True)
            (state_dir / "session_id").write_text("nonexistent-session")

            with patch('proof_utils.get_proof_dir') as mock_proof, \
                 patch('proof_utils.get_state_dir') as mock_state:
                mock_proof.return_value = proof_dir
                mock_state.return_value = state_dir

                from proof_utils import check_proof_for_session

                exists, msg, count = check_proof_for_session()

                self.assertTrue(exists)
                self.assertIn("legacy", msg.lower())


if __name__ == "__main__":
    unittest.main()
