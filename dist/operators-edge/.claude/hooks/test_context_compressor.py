#!/usr/bin/env python3
"""
Tests for context_compressor.py - Phase 10.1 Context Compression

Tests cover:
- Configuration loading
- Cooldown management
- Segment identification
- Compression strategies (Python, JS, JSON, YAML, Markdown, Bash)
- Snapshot storage
- Compression offer formatting
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

from context_compressor import (
    # Configuration
    _load_compression_config,
    _get_config_value,
    DEFAULT_CONTEXT_TRIGGER_PERCENT,
    DEFAULT_MIN_SEGMENT_CHARS,
    DEFAULT_MIN_SEGMENT_TOKENS,
    COMPRESSION_COOLDOWN_SECONDS,
    # Cooldown
    _can_offer_compression,
    _mark_compression_offered,
    reset_compression_cooldown,
    # Segment types
    SEGMENT_TYPE_FILE_READ,
    SEGMENT_TYPE_BASH_OUTPUT,
    # Data structures
    ContextSegment,
    CompressionResult,
    # Segment identification
    _estimate_tokens,
    _generate_segment_id,
    identify_compressible_segments,
    get_largest_segments,
    # Compression strategies
    compress_file_read,
    compress_bash_output,
    compress_segment,
    _extract_python_structure,
    _extract_js_structure,
    _extract_json_structure,
    _extract_yaml_structure,
    _extract_markdown_structure,
    _extract_generic_structure,
    # Storage
    save_snapshot,
    load_snapshot,
    # Offer formatting
    format_compression_offer,
    check_and_offer_compression,
    get_compression_summary,
)


class TestConfiguration(unittest.TestCase):
    """Test configuration loading."""

    def test_default_values(self):
        """Test that default values are reasonable."""
        self.assertEqual(DEFAULT_CONTEXT_TRIGGER_PERCENT, 70)
        self.assertEqual(DEFAULT_MIN_SEGMENT_CHARS, 5000)
        self.assertEqual(DEFAULT_MIN_SEGMENT_TOKENS, 1250)

    def test_load_config_with_no_file(self):
        """Test config loading when no file exists."""
        with patch('context_compressor._get_config_path') as mock_path:
            mock_path.return_value = Path("/nonexistent/path/config.json")
            config = _load_compression_config()

            self.assertEqual(config["context_trigger_percent"], DEFAULT_CONTEXT_TRIGGER_PERCENT)
            self.assertEqual(config["min_segment_chars"], DEFAULT_MIN_SEGMENT_CHARS)

    def test_load_config_with_custom_values(self):
        """Test config loading with custom values."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump({
                "compression": {
                    "context_trigger_percent": 80,
                    "min_segment_chars": 10000,
                }
            }, f)
            f.flush()

            with patch('context_compressor._get_config_path') as mock_path:
                mock_path.return_value = Path(f.name)
                config = _load_compression_config()

                self.assertEqual(config["context_trigger_percent"], 80)
                self.assertEqual(config["min_segment_chars"], 10000)
                # Defaults for unspecified
                self.assertEqual(config["min_segment_tokens"], DEFAULT_MIN_SEGMENT_TOKENS)

            os.unlink(f.name)


class TestCooldown(unittest.TestCase):
    """Test cooldown management."""

    def setUp(self):
        reset_compression_cooldown()

    def test_can_offer_when_never_offered(self):
        """Test that compression can be offered when never offered before."""
        self.assertTrue(_can_offer_compression())

    def test_cannot_offer_immediately_after(self):
        """Test that compression cannot be offered immediately after."""
        _mark_compression_offered()
        self.assertFalse(_can_offer_compression())

    def test_can_offer_after_cooldown(self):
        """Test that compression can be offered after cooldown expires."""
        import context_compressor

        context_compressor._last_compression_offer = datetime.now() - timedelta(seconds=COMPRESSION_COOLDOWN_SECONDS + 60)
        self.assertTrue(_can_offer_compression())

    def test_reset_cooldown(self):
        """Test that reset_compression_cooldown works."""
        _mark_compression_offered()
        self.assertFalse(_can_offer_compression())

        reset_compression_cooldown()
        self.assertTrue(_can_offer_compression())


class TestTokenEstimation(unittest.TestCase):
    """Test token estimation."""

    def test_estimate_tokens(self):
        """Test that token estimation works."""
        text = "a" * 100
        tokens = _estimate_tokens(text)
        self.assertEqual(tokens, 25)  # 100 / 4

    def test_estimate_tokens_empty(self):
        """Test empty string."""
        self.assertEqual(_estimate_tokens(""), 0)


class TestSegmentIdGeneration(unittest.TestCase):
    """Test segment ID generation."""

    def test_generates_unique_ids(self):
        """Test that IDs are unique for different inputs."""
        id1 = _generate_segment_id("file_read", "app.py", "2024-01-01")
        id2 = _generate_segment_id("file_read", "other.py", "2024-01-01")
        id3 = _generate_segment_id("bash_output", "app.py", "2024-01-01")

        self.assertNotEqual(id1, id2)
        self.assertNotEqual(id1, id3)

    def test_same_inputs_same_id(self):
        """Test that same inputs produce same ID."""
        id1 = _generate_segment_id("file_read", "app.py", "2024-01-01")
        id2 = _generate_segment_id("file_read", "app.py", "2024-01-01")

        self.assertEqual(id1, id2)


class TestContextSegment(unittest.TestCase):
    """Test ContextSegment data structure."""

    def test_to_dict(self):
        """Test to_dict method."""
        segment = ContextSegment(
            segment_id="test-001",
            segment_type=SEGMENT_TYPE_FILE_READ,
            content="test content",
            estimated_tokens=100,
            timestamp="2024-01-01T00:00:00",
            source="test.py",
        )

        d = segment.to_dict()

        self.assertEqual(d["segment_id"], "test-001")
        self.assertEqual(d["segment_type"], SEGMENT_TYPE_FILE_READ)
        self.assertEqual(d["estimated_tokens"], 100)
        self.assertNotIn("content", d)  # Content not in dict


class TestCompressionResult(unittest.TestCase):
    """Test CompressionResult data structure."""

    def test_to_dict(self):
        """Test to_dict method."""
        result = CompressionResult(
            segment_id="test-001",
            original_tokens=1000,
            compressed_tokens=200,
            compression_ratio=0.2,
            summary="Test summary",
            snapshot_path=Path("/tmp/snapshot.json"),
        )

        d = result.to_dict()

        self.assertEqual(d["original_tokens"], 1000)
        self.assertEqual(d["compressed_tokens"], 200)
        self.assertEqual(d["compression_ratio"], 0.2)
        self.assertIn("/tmp/snapshot.json", d["snapshot_path"])


class TestPythonStructureExtraction(unittest.TestCase):
    """Test Python structure extraction."""

    def test_extracts_imports(self):
        """Test import extraction."""
        content = """import os
import sys
from pathlib import Path

def main():
    pass
"""
        result = _extract_python_structure(content)
        self.assertIn("Imports:", result)
        self.assertIn("3", result)  # 3 imports

    def test_extracts_classes(self):
        """Test class extraction."""
        content = """class MyClass:
    pass

class AnotherClass:
    pass
"""
        result = _extract_python_structure(content)
        self.assertIn("Classes:", result)
        self.assertIn("MyClass", result)
        self.assertIn("AnotherClass", result)

    def test_extracts_functions(self):
        """Test function extraction."""
        content = """def func_one():
    pass

def func_two():
    pass
"""
        result = _extract_python_structure(content)
        self.assertIn("Functions:", result)
        self.assertIn("func_one", result)
        self.assertIn("func_two", result)


class TestJsStructureExtraction(unittest.TestCase):
    """Test JavaScript structure extraction."""

    def test_extracts_imports(self):
        """Test import extraction."""
        content = """import React from 'react';
import { useState } from 'react';
"""
        result = _extract_js_structure(content)
        self.assertIn("Imports:", result)

    def test_extracts_exports(self):
        """Test export extraction."""
        content = """export default App;
export const helper = () => {};
"""
        result = _extract_js_structure(content)
        self.assertIn("Exports:", result)


class TestJsonStructureExtraction(unittest.TestCase):
    """Test JSON structure extraction."""

    def test_extracts_object_keys(self):
        """Test object key extraction."""
        content = '{"name": "test", "version": "1.0", "dependencies": {}}'
        result = _extract_json_structure(content)
        self.assertIn("Top-level keys:", result)
        self.assertIn("name", result)
        self.assertIn("version", result)

    def test_extracts_array_length(self):
        """Test array length extraction."""
        content = '[1, 2, 3, 4, 5]'
        result = _extract_json_structure(content)
        self.assertIn("Array with 5 items", result)

    def test_handles_invalid_json(self):
        """Test invalid JSON handling."""
        content = 'not valid json'
        result = _extract_json_structure(content)
        self.assertIn("Invalid JSON", result)


class TestYamlStructureExtraction(unittest.TestCase):
    """Test YAML structure extraction."""

    def test_extracts_top_level_keys(self):
        """Test top-level key extraction."""
        content = """name: test
version: 1.0
dependencies:
  - foo
  - bar
"""
        result = _extract_yaml_structure(content)
        self.assertIn("Top-level keys:", result)
        self.assertIn("name", result)
        self.assertIn("version", result)


class TestMarkdownStructureExtraction(unittest.TestCase):
    """Test Markdown structure extraction."""

    def test_extracts_headers(self):
        """Test header extraction."""
        content = """# Main Title

## Section One

### Subsection

## Section Two
"""
        result = _extract_markdown_structure(content)
        self.assertIn("Headers:", result)
        self.assertIn("4", result)  # 4 headers


class TestGenericStructureExtraction(unittest.TestCase):
    """Test generic structure extraction."""

    def test_short_file(self):
        """Test short file handling."""
        content = "line 1\nline 2\nline 3"
        result = _extract_generic_structure(content)
        self.assertIn("Short file", result)

    def test_shows_first_and_last_lines(self):
        """Test first/last lines for long files."""
        lines = [f"line {i}" for i in range(100)]
        content = "\n".join(lines)
        result = _extract_generic_structure(content)
        self.assertIn("First 3 lines", result)
        self.assertIn("Last 2 lines", result)


class TestFileReadCompression(unittest.TestCase):
    """Test file read compression."""

    def test_compresses_python_file(self):
        """Test Python file compression."""
        segment = ContextSegment(
            segment_id="test-001",
            segment_type=SEGMENT_TYPE_FILE_READ,
            content="import os\n\nclass Foo:\n    pass\n\ndef bar():\n    pass",
            estimated_tokens=100,
            timestamp="2024-01-01",
            source="test.py",
        )

        summary = compress_file_read(segment)
        self.assertIn("test.py", summary)
        self.assertIn("lines", summary)

    def test_compresses_json_file(self):
        """Test JSON file compression."""
        segment = ContextSegment(
            segment_id="test-002",
            segment_type=SEGMENT_TYPE_FILE_READ,
            content='{"name": "test", "version": "1.0"}',
            estimated_tokens=50,
            timestamp="2024-01-01",
            source="package.json",
        )

        summary = compress_file_read(segment)
        self.assertIn("package.json", summary)


class TestBashOutputCompression(unittest.TestCase):
    """Test bash output compression."""

    def test_detects_errors(self):
        """Test error detection."""
        segment = ContextSegment(
            segment_id="test-001",
            segment_type=SEGMENT_TYPE_BASH_OUTPUT,
            content="Running tests...\nERROR: Test failed\nDone",
            estimated_tokens=50,
            timestamp="2024-01-01",
            source="pytest tests/",
        )

        summary = compress_bash_output(segment)
        self.assertIn("Errors detected", summary)

    def test_detects_success(self):
        """Test success indicator detection."""
        segment = ContextSegment(
            segment_id="test-002",
            segment_type=SEGMENT_TYPE_BASH_OUTPUT,
            content="Running tests...\nAll tests passed\nDone",
            estimated_tokens=50,
            timestamp="2024-01-01",
            source="pytest tests/",
        )

        summary = compress_bash_output(segment)
        self.assertIn("Success indicators", summary)


class TestCompressSegment(unittest.TestCase):
    """Test segment compression."""

    def test_returns_compression_result(self):
        """Test that compress_segment returns CompressionResult."""
        segment = ContextSegment(
            segment_id="test-001",
            segment_type=SEGMENT_TYPE_FILE_READ,
            content="test content " * 100,
            estimated_tokens=300,
            timestamp="2024-01-01",
            source="test.py",
        )

        result = compress_segment(segment, save_full=False)

        self.assertIsInstance(result, CompressionResult)
        self.assertEqual(result.segment_id, "test-001")
        self.assertEqual(result.original_tokens, 300)
        self.assertIsNotNone(result.summary)

    def test_calculates_compression_ratio(self):
        """Test compression ratio calculation."""
        segment = ContextSegment(
            segment_id="test-001",
            segment_type=SEGMENT_TYPE_FILE_READ,
            content="a" * 10000,
            estimated_tokens=2500,
            timestamp="2024-01-01",
            source="big_file.txt",
        )

        result = compress_segment(segment, save_full=False)

        self.assertLess(result.compression_ratio, 1.0)


class TestSnapshotStorage(unittest.TestCase):
    """Test snapshot storage."""

    def test_save_and_load_snapshot(self):
        """Test saving and loading snapshots."""
        segment = ContextSegment(
            segment_id="test-snapshot",
            segment_type=SEGMENT_TYPE_FILE_READ,
            content="test content for snapshot",
            estimated_tokens=10,
            timestamp="2024-01-01",
            source="test.py",
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            snapshots_dir = Path(tmpdir) / "snapshots"
            snapshots_dir.mkdir(parents=True, exist_ok=True)  # Create the directory

            with patch('context_compressor._get_snapshots_dir', return_value=snapshots_dir):
                path = save_snapshot(segment)

                self.assertTrue(path.exists())

                loaded = load_snapshot(path)
                self.assertIsNotNone(loaded)
                self.assertEqual(loaded["content"], "test content for snapshot")
                self.assertEqual(loaded["segment_id"], "test-snapshot")


class TestGetLargestSegments(unittest.TestCase):
    """Test getting largest segments."""

    def test_returns_sorted_by_tokens(self):
        """Test that segments are sorted by token count."""
        segments = [
            ContextSegment("s1", "file", "a", 100, "", ""),
            ContextSegment("s2", "file", "b", 500, "", ""),
            ContextSegment("s3", "file", "c", 200, "", ""),
        ]

        largest = get_largest_segments(segments, limit=2)

        self.assertEqual(len(largest), 2)
        self.assertEqual(largest[0].segment_id, "s2")  # 500 tokens
        self.assertEqual(largest[1].segment_id, "s3")  # 200 tokens

    def test_respects_limit(self):
        """Test that limit is respected."""
        segments = [
            ContextSegment(f"s{i}", "file", "a", i * 100, "", "")
            for i in range(10)
        ]

        largest = get_largest_segments(segments, limit=3)
        self.assertEqual(len(largest), 3)


class TestFormatCompressionOffer(unittest.TestCase):
    """Test compression offer formatting."""

    def test_suggestion_format(self):
        """Test suggestion urgency format."""
        segment = ContextSegment("s1", SEGMENT_TYPE_FILE_READ, "a", 1000, "", "test.py")
        result = CompressionResult("s1", 1000, 100, 0.1, "Summary")

        offer = format_compression_offer([segment], [result], "suggestion")

        self.assertIn("COMPRESSION SUGGESTION", offer)
        self.assertIn("╭", offer)

    def test_recommendation_format(self):
        """Test recommendation urgency format."""
        segment = ContextSegment("s1", SEGMENT_TYPE_FILE_READ, "a", 1000, "", "test.py")
        result = CompressionResult("s1", 1000, 100, 0.1, "Summary")

        offer = format_compression_offer([segment], [result], "recommendation")

        self.assertIn("COMPRESSION AVAILABLE", offer)

    def test_urgent_format(self):
        """Test urgent urgency format."""
        segment = ContextSegment("s1", SEGMENT_TYPE_FILE_READ, "a", 1000, "", "test.py")
        result = CompressionResult("s1", 1000, 100, 0.1, "Summary")

        offer = format_compression_offer([segment], [result], "urgent")

        self.assertIn("URGENT", offer)
        self.assertIn("⚠️", offer)

    def test_shows_savings(self):
        """Test that savings are shown."""
        segment = ContextSegment("s1", SEGMENT_TYPE_FILE_READ, "a", 1000, "", "test.py")
        result = CompressionResult("s1", 1000, 100, 0.1, "Summary")

        offer = format_compression_offer([segment], [result], "recommendation")

        self.assertIn("savings", offer.lower())


class TestCheckAndOfferCompression(unittest.TestCase):
    """Test check_and_offer_compression integration."""

    def setUp(self):
        reset_compression_cooldown()

    def test_returns_none_in_observe_mode(self):
        """Test returns None in observe mode."""
        result = check_and_offer_compression(intervention_level="observe")
        self.assertIsNone(result)

    def test_returns_none_on_cooldown(self):
        """Test returns None when on cooldown."""
        _mark_compression_offered()
        result = check_and_offer_compression(intervention_level="guide")
        self.assertIsNone(result)


class TestEdgeCases(unittest.TestCase):
    """Test edge cases."""

    def test_empty_content_compression(self):
        """Test compression of empty content."""
        segment = ContextSegment("s1", SEGMENT_TYPE_FILE_READ, "", 0, "", "empty.py")
        result = compress_segment(segment, save_full=False)

        self.assertIsNotNone(result.summary)
        self.assertEqual(result.original_tokens, 0)

    def test_handles_unicode_content(self):
        """Test handling of unicode content."""
        segment = ContextSegment(
            "s1",
            SEGMENT_TYPE_FILE_READ,
            "def greet():\n    print('こんにちは')\n    print('🎉')",
            50,
            "",
            "unicode.py",
        )

        result = compress_segment(segment, save_full=False)
        self.assertIsNotNone(result.summary)


if __name__ == "__main__":
    unittest.main()
