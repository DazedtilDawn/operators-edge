#!/usr/bin/env python3
"""
Tests for Operator's Edge v8.0 - Codebase Knowledge

Tests cover:
- Error signature extraction
- Fix recording and lookup
- Co-change pattern tracking
- Confidence decay
- Formatting
"""
import json
import os
import shutil
import sys
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch, MagicMock

# Add hooks directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from codebase_knowledge import (
    KnownFix,
    RelatedFile,
    extract_error_signature,
    compute_signature_hash,
    record_fix,
    lookup_fix,
    get_all_fixes,
    record_cochange,
    get_related_files,
    format_known_fix,
    format_related_files,
    _get_knowledge_path,
    _load_knowledge,
    _save_knowledge,
)


class TestExtractErrorSignature(unittest.TestCase):
    """Tests for error signature extraction."""

    def test_extracts_python_import_error(self):
        """Should extract Python ImportError signature."""
        error = "ImportError: No module named 'mymodule'"
        sig, err_type = extract_error_signature(error)
        self.assertEqual(err_type, "import_error")
        self.assertIn("mymodule", sig)

    def test_extracts_python_module_not_found(self):
        """Should extract ModuleNotFoundError signature."""
        error = "ModuleNotFoundError: No module named 'utils.auth'"
        sig, err_type = extract_error_signature(error)
        self.assertEqual(err_type, "import_error")
        self.assertIn("utils.auth", sig)

    def test_extracts_file_not_found(self):
        """Should extract FileNotFoundError signature."""
        error = "FileNotFoundError: [Errno 2] No such file: '/app/config.yaml'"
        sig, err_type = extract_error_signature(error)
        self.assertEqual(err_type, "file_not_found")
        self.assertIn("config.yaml", sig)

    def test_extracts_key_error(self):
        """Should extract KeyError signature."""
        error = "KeyError: 'missing_key'"
        sig, err_type = extract_error_signature(error)
        self.assertEqual(err_type, "key_error")
        self.assertIn("missing_key", sig)

    def test_extracts_js_module_error(self):
        """Should extract JavaScript module error."""
        error = "Error: Cannot find module 'lodash'"
        sig, err_type = extract_error_signature(error)
        self.assertEqual(err_type, "module_not_found")
        self.assertIn("lodash", sig)

    def test_extracts_general_failure(self):
        """Should extract general failure patterns."""
        error = "FAIL: test_authentication"
        sig, err_type = extract_error_signature(error)
        self.assertEqual(err_type, "general_failure")
        self.assertIn("test_authentication", sig)

    def test_handles_empty_input(self):
        """Should handle empty input gracefully."""
        sig, err_type = extract_error_signature("")
        self.assertEqual(sig, "")
        self.assertEqual(err_type, "unknown")

    def test_handles_multiline_error(self):
        """Should extract from multiline error output."""
        error = """Traceback (most recent call last):
  File "test.py", line 5
    print(x)
NameError: name 'x' is not defined"""
        sig, err_type = extract_error_signature(error)
        self.assertNotEqual(sig, "")

    def test_truncates_long_signatures(self):
        """Should truncate very long signatures."""
        error = "TypeError: " + "x" * 500
        sig, _ = extract_error_signature(error)
        self.assertLessEqual(len(sig), 200)


class TestComputeSignatureHash(unittest.TestCase):
    """Tests for signature hashing."""

    def test_produces_consistent_hash(self):
        """Should produce same hash for same input."""
        sig = "ImportError: mymodule"
        hash1 = compute_signature_hash(sig)
        hash2 = compute_signature_hash(sig)
        self.assertEqual(hash1, hash2)

    def test_produces_different_hash_for_different_input(self):
        """Should produce different hash for different input."""
        hash1 = compute_signature_hash("ImportError: module1")
        hash2 = compute_signature_hash("ImportError: module2")
        self.assertNotEqual(hash1, hash2)

    def test_hash_length(self):
        """Hash should be 12 characters."""
        sig_hash = compute_signature_hash("test")
        self.assertEqual(len(sig_hash), 12)


class TestRecordAndLookupFix(unittest.TestCase):
    """Tests for fix recording and lookup."""

    def setUp(self):
        """Create temp directory for knowledge store."""
        self.temp_dir = tempfile.mkdtemp()
        self.original_path = None

    def tearDown(self):
        """Clean up temp directory."""
        shutil.rmtree(self.temp_dir)

    @patch('codebase_knowledge._get_knowledge_path')
    def test_records_new_fix(self, mock_path):
        """Should record a new fix."""
        mock_path.return_value = Path(self.temp_dir) / "knowledge.json"

        result = record_fix(
            error_output="ImportError: No module named 'mymodule'",
            fix_description="Install the module",
            fix_commands=["pip install mymodule"],
            fix_files=["requirements.txt"]
        )

        self.assertIsNotNone(result)
        self.assertEqual(len(result), 12)  # Hash length

    @patch('codebase_knowledge._get_knowledge_path')
    def test_lookup_finds_recorded_fix(self, mock_path):
        """Should find a previously recorded fix."""
        mock_path.return_value = Path(self.temp_dir) / "knowledge.json"

        # Record a fix
        record_fix(
            error_output="ImportError: No module named 'testmod'",
            fix_description="Install testmod package"
        )

        # Look it up
        fix = lookup_fix("ImportError: No module named 'testmod'")

        self.assertIsNotNone(fix)
        self.assertEqual(fix.fix_description, "Install testmod package")

    @patch('codebase_knowledge._get_knowledge_path')
    def test_lookup_returns_none_for_unknown(self, mock_path):
        """Should return None for unknown errors."""
        mock_path.return_value = Path(self.temp_dir) / "knowledge.json"

        fix = lookup_fix("SomeUnknownError: never seen before")

        self.assertIsNone(fix)

    @patch('codebase_knowledge._get_knowledge_path')
    def test_updates_existing_fix(self, mock_path):
        """Should update existing fix on re-record."""
        mock_path.return_value = Path(self.temp_dir) / "knowledge.json"

        # Record same fix twice
        record_fix(
            error_output="ImportError: No module named 'updatetest'",
            fix_description="First fix"
        )
        record_fix(
            error_output="ImportError: No module named 'updatetest'",
            fix_description="Updated fix"
        )

        # Look it up
        fix = lookup_fix("ImportError: No module named 'updatetest'")

        self.assertEqual(fix.times_used, 2)
        # Confidence should be boosted
        self.assertGreater(fix.confidence, 0.6)

    @patch('codebase_knowledge._get_knowledge_path')
    def test_merges_commands_and_files(self, mock_path):
        """Should merge commands and files on update."""
        mock_path.return_value = Path(self.temp_dir) / "knowledge.json"

        record_fix(
            error_output="ImportError: No module named 'mergetest'",
            fix_description="Merge test",
            fix_commands=["cmd1"],
            fix_files=["file1.py"]
        )
        record_fix(
            error_output="ImportError: No module named 'mergetest'",
            fix_description="Merge test",
            fix_commands=["cmd2"],
            fix_files=["file2.py"]
        )

        fix = lookup_fix("ImportError: No module named 'mergetest'")

        self.assertIn("cmd1", fix.fix_commands)
        self.assertIn("cmd2", fix.fix_commands)
        self.assertIn("file1.py", fix.fix_files)
        self.assertIn("file2.py", fix.fix_files)

    @patch('codebase_knowledge._get_knowledge_path')
    def test_get_all_fixes(self, mock_path):
        """Should return all recorded fixes."""
        mock_path.return_value = Path(self.temp_dir) / "knowledge.json"

        record_fix("ImportError: mod1", "Fix 1")
        record_fix("ImportError: mod2", "Fix 2")

        fixes = get_all_fixes()

        self.assertEqual(len(fixes), 2)


class TestCochangePatterns(unittest.TestCase):
    """Tests for file co-change pattern tracking."""

    def setUp(self):
        """Create temp directory for knowledge store."""
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        """Clean up temp directory."""
        shutil.rmtree(self.temp_dir)

    @patch('codebase_knowledge._get_knowledge_path')
    def test_records_cochange(self, mock_path):
        """Should record co-change relationship."""
        mock_path.return_value = Path(self.temp_dir) / "knowledge.json"

        record_cochange("file1.py", "file2.py", "Updated together")

        relations = get_related_files("file1.py")

        self.assertEqual(len(relations), 1)
        self.assertEqual(relations[0].file_path, "file2.py")

    @patch('codebase_knowledge._get_knowledge_path')
    def test_cochange_is_bidirectional(self, mock_path):
        """Co-change should create bidirectional relationship."""
        mock_path.return_value = Path(self.temp_dir) / "knowledge.json"

        record_cochange("a.py", "b.py")

        relations_a = get_related_files("a.py")
        relations_b = get_related_files("b.py")

        self.assertEqual(len(relations_a), 1)
        self.assertEqual(len(relations_b), 1)
        self.assertEqual(relations_a[0].file_path, "b.py")
        self.assertEqual(relations_b[0].file_path, "a.py")

    @patch('codebase_knowledge._get_knowledge_path')
    def test_repeated_cochange_strengthens(self, mock_path):
        """Repeated co-changes should strengthen relationship."""
        mock_path.return_value = Path(self.temp_dir) / "knowledge.json"

        record_cochange("x.py", "y.py")
        initial = get_related_files("x.py")[0].strength

        record_cochange("x.py", "y.py")
        strengthened = get_related_files("x.py")[0].strength

        self.assertGreater(strengthened, initial)

    @patch('codebase_knowledge._get_knowledge_path')
    def test_min_strength_filter(self, mock_path):
        """Should filter by minimum strength."""
        mock_path.return_value = Path(self.temp_dir) / "knowledge.json"

        record_cochange("strong.py", "weak.py")  # 0.5 strength

        # High threshold should filter out
        relations = get_related_files("strong.py", min_strength=0.8)
        self.assertEqual(len(relations), 0)

        # Low threshold should include
        relations = get_related_files("strong.py", min_strength=0.3)
        self.assertEqual(len(relations), 1)

    @patch('codebase_knowledge._get_knowledge_path')
    def test_returns_empty_for_unknown_file(self, mock_path):
        """Should return empty list for file with no relations."""
        mock_path.return_value = Path(self.temp_dir) / "knowledge.json"

        relations = get_related_files("unknown.py")

        self.assertEqual(relations, [])


class TestConfidenceDecay(unittest.TestCase):
    """Tests for confidence decay over time."""

    def setUp(self):
        """Create temp directory for knowledge store."""
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        """Clean up temp directory."""
        shutil.rmtree(self.temp_dir)

    @patch('codebase_knowledge._get_knowledge_path')
    def test_confidence_decays_with_age(self, mock_path):
        """Confidence should decay for old fixes."""
        mock_path.return_value = Path(self.temp_dir) / "knowledge.json"

        # Record a fix
        record_fix("ImportError: oldmod", "Old fix")

        # Manually age the fix
        knowledge = _load_knowledge()
        for key in knowledge["fixes"]:
            old_time = datetime.now() - timedelta(days=60)
            knowledge["fixes"][key]["last_success"] = old_time.isoformat()
        _save_knowledge(knowledge)

        # Look up - should have decayed confidence
        fix = lookup_fix("ImportError: oldmod")

        # Original confidence was 0.6, should be lower now
        self.assertLess(fix.confidence, 0.6)


class TestFormatting(unittest.TestCase):
    """Tests for formatting functions."""

    def test_format_known_fix(self):
        """Should format a known fix nicely."""
        fix = KnownFix(
            error_signature="ImportError: mymod",
            error_type="import_error",
            fix_description="Install the module",
            fix_commands=["pip install mymod"],
            fix_files=["requirements.txt"],
            confidence=0.8,
            times_used=5,
            created_at="2026-01-01T00:00:00",
            context_hints=["Python project"]
        )

        output = format_known_fix(fix)

        self.assertIn("KNOWN FIX FOUND", output)
        self.assertIn("Install the module", output)
        self.assertIn("pip install mymod", output)
        self.assertIn("requirements.txt", output)
        self.assertIn("80%", output)  # Confidence
        self.assertIn("5x", output)   # Times used

    def test_format_related_files(self):
        """Should format related files nicely."""
        relations = [
            RelatedFile("file1.py", "cochange", 0.8, "Changed together"),
            RelatedFile("file2.py", "dependency", 0.5, "Imports from"),
        ]

        output = format_related_files(relations)

        self.assertIn("Related Files", output)
        self.assertIn("file1.py", output)
        self.assertIn("file2.py", output)

    def test_format_empty_relations(self):
        """Should return empty string for no relations."""
        output = format_related_files([])
        self.assertEqual(output, "")


class TestDataclasses(unittest.TestCase):
    """Tests for dataclass serialization."""

    def test_known_fix_to_dict(self):
        """KnownFix should serialize to dict."""
        fix = KnownFix(
            error_signature="test",
            error_type="test_type",
            fix_description="test fix",
            fix_commands=["cmd"],
            fix_files=["file"],
            confidence=0.5,
            times_used=1
        )

        d = fix.to_dict()

        self.assertEqual(d["error_signature"], "test")
        self.assertEqual(d["fix_description"], "test fix")

    def test_known_fix_from_dict(self):
        """KnownFix should deserialize from dict."""
        data = {
            "error_signature": "test",
            "error_type": "test_type",
            "fix_description": "test fix",
            "fix_commands": ["cmd"],
            "fix_files": ["file"],
            "confidence": 0.7,
            "times_used": 3
        }

        fix = KnownFix.from_dict(data)

        self.assertEqual(fix.error_signature, "test")
        self.assertEqual(fix.confidence, 0.7)
        self.assertEqual(fix.times_used, 3)

    def test_related_file_to_dict(self):
        """RelatedFile should serialize to dict."""
        rel = RelatedFile("file.py", "cochange", 0.5, "reason")

        d = rel.to_dict()

        self.assertEqual(d["file_path"], "file.py")
        self.assertEqual(d["relation_type"], "cochange")

    def test_related_file_from_dict(self):
        """RelatedFile should deserialize from dict."""
        data = {
            "file_path": "test.py",
            "relation_type": "dependency",
            "strength": 0.8,
            "reason": "imports"
        }

        rel = RelatedFile.from_dict(data)

        self.assertEqual(rel.file_path, "test.py")
        self.assertEqual(rel.strength, 0.8)


if __name__ == "__main__":
    unittest.main()
