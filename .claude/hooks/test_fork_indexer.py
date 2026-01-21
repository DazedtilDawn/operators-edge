#!/usr/bin/env python3
"""
Tests for fork_indexer.py - Session indexing for Smart Forking.
"""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

# Add hooks directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fork_indexer import (
    parse_session_jsonl,
    extract_user_messages,
    extract_objective,
    extract_summary,
    get_session_metadata,
    scan_sessions,
    build_index,
    extract_project_name,
    clean_message_content,
    suggest_similar_sessions,
)


class TestParseSessionJsonl(unittest.TestCase):
    """Test JSONL session file parsing."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_parse_valid_jsonl(self):
        """Valid JSONL file is parsed correctly."""
        path = Path(self.temp_dir) / "session.jsonl"
        with open(path, "w") as f:
            f.write('{"type": "human", "content": "Hello"}\n')
            f.write('{"type": "assistant", "content": "Hi there"}\n')

        messages = parse_session_jsonl(path)
        self.assertEqual(len(messages), 2)
        self.assertEqual(messages[0]["type"], "human")
        self.assertEqual(messages[1]["type"], "assistant")

    def test_parse_empty_file(self):
        """Empty file returns empty list."""
        path = Path(self.temp_dir) / "empty.jsonl"
        path.touch()

        messages = parse_session_jsonl(path)
        self.assertEqual(messages, [])

    def test_parse_invalid_json_lines(self):
        """Invalid JSON lines are skipped."""
        path = Path(self.temp_dir) / "mixed.jsonl"
        with open(path, "w") as f:
            f.write('{"type": "human", "content": "Hello"}\n')
            f.write('not valid json\n')
            f.write('{"type": "assistant", "content": "Hi"}\n')

        messages = parse_session_jsonl(path)
        self.assertEqual(len(messages), 2)

    def test_parse_nonexistent_file(self):
        """Nonexistent file returns empty list."""
        path = Path(self.temp_dir) / "nonexistent.jsonl"
        messages = parse_session_jsonl(path)
        self.assertEqual(messages, [])


class TestExtractUserMessages(unittest.TestCase):
    """Test user message extraction."""

    def test_extract_human_type(self):
        """Messages with type='human' are extracted."""
        messages = [
            {"type": "human", "content": "Hello"},
            {"type": "assistant", "content": "Hi"},
            {"type": "human", "content": "How are you?"},
        ]

        user_msgs = extract_user_messages(messages)
        self.assertEqual(len(user_msgs), 2)
        self.assertEqual(user_msgs[0], "Hello")
        self.assertEqual(user_msgs[1], "How are you?")

    def test_extract_user_role(self):
        """Messages with role='user' are extracted."""
        messages = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi"},
        ]

        user_msgs = extract_user_messages(messages)
        self.assertEqual(len(user_msgs), 1)
        self.assertEqual(user_msgs[0], "Hello")

    def test_extract_structured_content(self):
        """Structured content blocks are extracted."""
        messages = [
            {
                "type": "human",
                "content": [
                    {"type": "text", "text": "Part 1"},
                    {"type": "text", "text": "Part 2"},
                ]
            }
        ]

        user_msgs = extract_user_messages(messages)
        self.assertEqual(len(user_msgs), 2)
        self.assertEqual(user_msgs[0], "Part 1")

    def test_extract_empty_messages(self):
        """Empty message list returns empty list."""
        user_msgs = extract_user_messages([])
        self.assertEqual(user_msgs, [])


class TestExtractObjective(unittest.TestCase):
    """Test objective extraction from messages."""

    def test_extract_from_first_message(self):
        """Objective from first user message."""
        messages = [
            {"type": "human", "content": "Build a todo app"},
        ]

        objective = extract_objective(messages)
        self.assertEqual(objective, "Build a todo app")

    def test_extract_explicit_objective(self):
        """Explicit 'objective:' marker is detected."""
        messages = [
            {"type": "human", "content": "Hello"},
            {"type": "human", "content": "Objective: Create a REST API"},
        ]

        objective = extract_objective(messages)
        self.assertIn("Objective:", objective)

    def test_extract_truncates_long_objectives(self):
        """Long objectives are truncated."""
        long_content = "Build " + "x" * 300
        messages = [
            {"type": "human", "content": long_content},
        ]

        objective = extract_objective(messages)
        self.assertLessEqual(len(objective), 200)

    def test_extract_empty_returns_none(self):
        """Empty messages returns None."""
        objective = extract_objective([])
        self.assertIsNone(objective)


class TestExtractSummary(unittest.TestCase):
    """Test summary extraction for embedding."""

    def test_summary_includes_objective(self):
        """Summary includes extracted objective."""
        messages = [
            {"type": "human", "content": "Objective: Build authentication"},
        ]

        summary = extract_summary(messages)
        self.assertIn("Objective:", summary)
        self.assertIn("authentication", summary)

    def test_summary_includes_user_messages(self):
        """Summary includes first N user messages."""
        messages = [
            {"type": "human", "content": "First message"},
            {"type": "assistant", "content": "Response"},
            {"type": "human", "content": "Second message"},
        ]

        summary = extract_summary(messages, max_user_messages=2)
        self.assertIn("First message", summary)
        self.assertIn("Second message", summary)

    def test_summary_respects_max_messages(self):
        """Summary respects max_user_messages limit and samples from full session."""
        # Use longer messages to avoid being filtered by minimum length
        messages = [
            {"type": "human", "content": f"User request number {i} with details"}
            for i in range(10)
        ]

        # v1.2: Now samples from beginning, middle, and end
        summary = extract_summary(messages, max_user_messages=3)
        self.assertIn("number 0", summary)  # From start
        self.assertIn("number 3", summary)  # From middle (10 // 3 = 3)
        self.assertIn("number 9", summary)  # From end


class TestGetSessionMetadata(unittest.TestCase):
    """Test session metadata extraction."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_metadata_includes_session_id(self):
        """Metadata includes session ID from filename."""
        path = Path(self.temp_dir) / "abc123.jsonl"
        path.touch()

        messages = [
            {"type": "human", "content": "Hello"},
        ]

        metadata = get_session_metadata(path, messages)
        self.assertEqual(metadata["session_id"], "abc123")

    def test_metadata_includes_message_counts(self):
        """Metadata includes message counts."""
        path = Path(self.temp_dir) / "test.jsonl"
        path.touch()

        messages = [
            {"type": "human", "content": "Hello"},
            {"type": "assistant", "content": "Hi"},
            {"type": "human", "content": "Bye"},
        ]

        metadata = get_session_metadata(path, messages)
        self.assertEqual(metadata["message_count"], 3)
        self.assertEqual(metadata["user_message_count"], 2)

    def test_metadata_includes_timestamps(self):
        """Metadata includes first/last timestamps."""
        path = Path(self.temp_dir) / "test.jsonl"
        path.touch()

        messages = [
            {"type": "human", "content": "Hello", "timestamp": "2026-01-01T10:00:00"},
            {"type": "assistant", "content": "Hi", "timestamp": "2026-01-01T10:05:00"},
        ]

        metadata = get_session_metadata(path, messages)
        self.assertEqual(metadata["first_timestamp"], "2026-01-01T10:00:00")
        self.assertEqual(metadata["last_timestamp"], "2026-01-01T10:05:00")


class TestScanSessions(unittest.TestCase):
    """Test session scanning."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _create_session_file(self, path: Path, num_messages: int = 6):
        """Create a session file with enough messages to pass min_messages filter."""
        with open(path, "w") as f:
            for i in range(num_messages):
                f.write(f'{{"type": "human", "content": "Message {i}"}}\n')

    def test_scan_finds_jsonl_files(self):
        """Scan finds .jsonl session files."""
        # Create test session files with enough messages (min_messages=5 default)
        for i in range(3):
            path = Path(self.temp_dir) / f"session{i}.jsonl"
            self._create_session_file(path, num_messages=6)

        sessions = list(scan_sessions(sessions_dir=Path(self.temp_dir)))
        self.assertEqual(len(sessions), 3)

    def test_scan_respects_max_sessions(self):
        """Scan respects max_sessions limit."""
        for i in range(10):
            path = Path(self.temp_dir) / f"session{i}.jsonl"
            self._create_session_file(path, num_messages=6)

        sessions = list(scan_sessions(max_sessions=5, sessions_dir=Path(self.temp_dir)))
        self.assertEqual(len(sessions), 5)

    def test_scan_skips_empty_files(self):
        """Scan skips files with no messages or too few messages."""
        # Create one valid file with enough messages
        valid = Path(self.temp_dir) / "valid.jsonl"
        self._create_session_file(valid, num_messages=6)

        # Create a file with too few messages (should be skipped)
        too_few = Path(self.temp_dir) / "toofew.jsonl"
        with open(too_few, "w") as f:
            f.write('{"type": "human", "content": "Test"}\n')

        # Create an empty file (should be skipped)
        empty = Path(self.temp_dir) / "empty.jsonl"
        empty.touch()

        sessions = list(scan_sessions(sessions_dir=Path(self.temp_dir)))
        self.assertEqual(len(sessions), 1)


class TestBuildIndex(unittest.TestCase):
    """Test index building."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.sessions_dir = Path(self.temp_dir) / "sessions"
        self.sessions_dir.mkdir()
        self.embeddings_dir = Path(self.temp_dir) / "embeddings"
        self.embeddings_dir.mkdir()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _create_session_file(self, path: Path, num_messages: int = 6):
        """Create a session file with enough messages to pass min_messages filter."""
        with open(path, "w") as f:
            for i in range(num_messages):
                f.write(f'{{"type": "human", "content": "Build a web app - message {i}"}}\n')

    def test_build_index_success(self):
        """Index is built successfully with mocked embeddings."""
        # Create test session with enough messages
        session_path = self.sessions_dir / "test123.jsonl"
        self._create_session_file(session_path, num_messages=6)

        # Mock the embedding generation and directory functions
        with patch("fork_indexer.generate_embedding", return_value=[0.1, 0.2, 0.3]):
            with patch("fork_indexer.get_claude_sessions_dir", return_value=self.sessions_dir):
                with patch("fork_utils.get_embeddings_dir", return_value=self.embeddings_dir):
                    indexed, skipped, errors = build_index(max_sessions=10)

        self.assertEqual(indexed, 1)
        self.assertEqual(len(errors), 0)

    def test_build_index_skips_on_embedding_failure(self):
        """Sessions are skipped when embedding fails."""
        session_path = self.sessions_dir / "test.jsonl"
        self._create_session_file(session_path, num_messages=6)

        with patch("fork_indexer.generate_embedding", return_value=None):
            with patch("fork_indexer.get_claude_sessions_dir", return_value=self.sessions_dir):
                with patch("fork_utils.get_embeddings_dir", return_value=self.embeddings_dir):
                    indexed, skipped, errors = build_index(max_sessions=10)

        self.assertEqual(indexed, 0)
        self.assertEqual(skipped, 1)
        self.assertGreater(len(errors), 0)


class TestCrossProjectSearch(unittest.TestCase):
    """Test cross-project search features (v1.1)."""

    def test_extract_project_name_simple(self):
        """Extract project name from simple path."""
        path = Path("/Users/andy/.claude/projects/-Users-andy-MyProject")
        name = extract_project_name(path)
        self.assertEqual(name, "MyProject")

    def test_extract_project_name_with_documents(self):
        """Extract project name skipping common path segments."""
        path = Path("/Users/andy/.claude/projects/-Users-andy-Documents-CoolProject")
        name = extract_project_name(path)
        self.assertEqual(name, "CoolProject")

    def test_extract_project_name_complex(self):
        """Extract project name from complex path."""
        path = Path("/Users/andy/.claude/projects/-Users-andy-Code-dev-my-app")
        name = extract_project_name(path)
        # Should get last meaningful segment
        self.assertIn("app", name.lower())


class TestCleanMessageContent(unittest.TestCase):
    """Test message content cleaning (v1.1)."""

    def test_removes_system_reminder(self):
        """System reminder blocks are removed."""
        text = "Hello <system-reminder>This is system stuff</system-reminder> World"
        cleaned = clean_message_content(text)
        self.assertNotIn("system", cleaned.lower())
        self.assertIn("Hello", cleaned)
        self.assertIn("World", cleaned)

    def test_removes_command_blocks(self):
        """Command blocks are removed."""
        text = "Start <command-name>edge-plan</command-name> End"
        cleaned = clean_message_content(text)
        self.assertNotIn("edge-plan", cleaned)
        self.assertIn("Start", cleaned)

    def test_preserves_user_content(self):
        """Regular user content is preserved."""
        text = "I want to implement authentication for my app"
        cleaned = clean_message_content(text)
        self.assertEqual(cleaned, text)

    def test_removes_edge_commands(self):
        """Edge command prefixes are removed."""
        text = "/edge-plan create a new feature"
        cleaned = clean_message_content(text)
        self.assertNotIn("/edge-plan", cleaned)
        self.assertIn("create a new feature", cleaned)

    def test_handles_hook_output(self):
        """Hook output blocks are filtered when after separators."""
        text = """Real user message
============================================================
OPERATOR'S EDGE - Session Initialized
Mode: active
State: pending
============================================================
Another user message"""
        cleaned = clean_message_content(text)
        self.assertIn("Real user message", cleaned)
        self.assertIn("Another user message", cleaned)
        # Hook output should be filtered
        self.assertNotIn("OPERATOR'S EDGE", cleaned)


class TestSuggestSimilarSessions(unittest.TestCase):
    """Test auto-suggest functionality (v1.1)."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_suggest_returns_empty_for_short_objective(self):
        """Short objectives return empty suggestions."""
        suggestions = suggest_similar_sessions("hi", top_k=3)
        self.assertEqual(suggestions, [])

    def test_suggest_returns_empty_for_no_index(self):
        """No index returns empty suggestions."""
        with patch("fork_indexer.load_index", return_value=(None, None)):
            suggestions = suggest_similar_sessions(
                "Build a web application",
                top_k=3
            )
            self.assertEqual(suggestions, [])

    def test_suggest_respects_min_score(self):
        """Suggestions below min_score are filtered out."""
        mock_metadata = {
            "sessions": [
                {"session_id": "session1", "summary_preview": "Test 1", "project_name": "proj"},
                {"session_id": "session2", "summary_preview": "Test 2", "project_name": "proj"},
            ]
        }
        mock_vectors = [[0.1, 0.2], [0.3, 0.4]]

        with patch("fork_indexer.load_index", return_value=(mock_metadata, mock_vectors)):
            with patch("fork_indexer.generate_embedding", return_value=[0.5, 0.5]):
                # With very high min_score, should filter out results
                suggestions = suggest_similar_sessions(
                    "Build a web application",
                    top_k=3,
                    min_score=0.99
                )
                # Cosine similarity of [0.5, 0.5] with [0.1, 0.2] or [0.3, 0.4] is < 0.99
                self.assertEqual(len(suggestions), 0)


if __name__ == "__main__":
    unittest.main()
