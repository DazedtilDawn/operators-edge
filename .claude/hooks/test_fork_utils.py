#!/usr/bin/env python3
"""
Tests for fork_utils.py - Smart Forking core utilities.
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

from fork_utils import (
    get_embeddings_dir,
    get_lmstudio_url,
    check_lmstudio_available,
    generate_embedding,
    cosine_similarity,
    load_index,
    save_index,
    search_similar,
    get_index_stats,
    get_search_backend,
    DEFAULT_LMSTUDIO_URL,
    EMBEDDING_DIMENSION,
)


class TestConfiguration(unittest.TestCase):
    """Test configuration loading."""

    def test_default_lmstudio_url(self):
        """Default URL is returned when no config exists."""
        with patch.dict(os.environ, {}, clear=True):
            with patch("fork_utils.load_config", return_value={}):
                url = get_lmstudio_url()
                self.assertEqual(url, DEFAULT_LMSTUDIO_URL)

    def test_env_var_overrides_default(self):
        """Environment variable overrides default URL."""
        with patch.dict(os.environ, {"LMSTUDIO_URL": "http://custom:5000"}):
            url = get_lmstudio_url()
            self.assertEqual(url, "http://custom:5000")

    def test_config_file_used(self):
        """Config file URL is used when no env var."""
        with patch.dict(os.environ, {}, clear=True):
            with patch("fork_utils.load_config", return_value={"lmstudio_url": "http://config:6000"}):
                url = get_lmstudio_url()
                self.assertEqual(url, "http://config:6000")


class TestCosineSimilarity(unittest.TestCase):
    """Test cosine similarity calculation."""

    def test_identical_vectors(self):
        """Identical vectors have similarity 1.0."""
        vec = [1.0, 2.0, 3.0]
        sim = cosine_similarity(vec, vec)
        self.assertAlmostEqual(sim, 1.0, places=5)

    def test_orthogonal_vectors(self):
        """Orthogonal vectors have similarity 0.0."""
        vec1 = [1.0, 0.0, 0.0]
        vec2 = [0.0, 1.0, 0.0]
        sim = cosine_similarity(vec1, vec2)
        self.assertAlmostEqual(sim, 0.0, places=5)

    def test_opposite_vectors(self):
        """Opposite vectors have similarity -1.0."""
        vec1 = [1.0, 2.0, 3.0]
        vec2 = [-1.0, -2.0, -3.0]
        sim = cosine_similarity(vec1, vec2)
        self.assertAlmostEqual(sim, -1.0, places=5)

    def test_zero_vector(self):
        """Zero vector returns similarity 0.0."""
        vec1 = [0.0, 0.0, 0.0]
        vec2 = [1.0, 2.0, 3.0]
        sim = cosine_similarity(vec1, vec2)
        self.assertEqual(sim, 0.0)

    def test_partial_similarity(self):
        """Partially similar vectors have intermediate similarity."""
        vec1 = [1.0, 1.0, 0.0]
        vec2 = [1.0, 0.0, 0.0]
        sim = cosine_similarity(vec1, vec2)
        # cos(45°) ≈ 0.707
        self.assertGreater(sim, 0.5)
        self.assertLess(sim, 1.0)


class TestIndexOperations(unittest.TestCase):
    """Test index save/load operations."""

    def setUp(self):
        """Create temporary directory for tests."""
        self.temp_dir = tempfile.mkdtemp()
        self.original_func = None

    def tearDown(self):
        """Clean up temporary directory."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_save_and_load_index(self):
        """Index can be saved and loaded correctly."""
        with patch("fork_utils.get_embeddings_dir", return_value=Path(self.temp_dir)):
            metadata = {
                "version": "1.0",
                "sessions": [{"session_id": "test123"}],
                "last_updated": "2026-01-20",
            }
            vectors = [[0.1, 0.2, 0.3], [0.4, 0.5, 0.6]]

            save_index(metadata, vectors)

            loaded_meta, loaded_vecs = load_index()

            self.assertEqual(loaded_meta["version"], "1.0")
            self.assertEqual(len(loaded_meta["sessions"]), 1)
            # Vectors may be in metadata fallback if numpy not available
            if loaded_vecs is not None:
                self.assertEqual(len(loaded_vecs), 2)
            else:
                # Check fallback storage
                self.assertEqual(len(loaded_meta.get("_vectors_fallback", [])), 2)

    def test_load_nonexistent_index(self):
        """Loading nonexistent index returns None."""
        with patch("fork_utils.get_embeddings_dir", return_value=Path(self.temp_dir)):
            meta, vecs = load_index()
            self.assertIsNone(meta)
            self.assertIsNone(vecs)


class TestSearchSimilar(unittest.TestCase):
    """Test similarity search."""

    def test_search_returns_sorted_results(self):
        """Search returns results sorted by similarity."""
        query = [1.0, 0.0, 0.0]
        vectors = [
            [0.5, 0.5, 0.0],  # Partial match
            [1.0, 0.0, 0.0],  # Exact match
            [0.0, 1.0, 0.0],  # No match
        ]

        results = search_similar(query, vectors, top_k=3)

        # Index 1 (exact match) should be first
        self.assertEqual(results[0][0], 1)
        self.assertAlmostEqual(results[0][1], 1.0, places=5)

        # Index 0 (partial) should be second
        self.assertEqual(results[1][0], 0)

        # Index 2 (orthogonal) should be last
        self.assertEqual(results[2][0], 2)

    def test_search_respects_top_k(self):
        """Search returns at most top_k results."""
        query = [1.0, 0.0, 0.0]
        vectors = [[1.0, 0.0, 0.0] for _ in range(10)]

        results = search_similar(query, vectors, top_k=3)
        self.assertEqual(len(results), 3)

    def test_search_empty_vectors(self):
        """Search with empty vectors returns empty list."""
        query = [1.0, 0.0, 0.0]
        results = search_similar(query, [], top_k=5)
        self.assertEqual(results, [])


class TestIndexStats(unittest.TestCase):
    """Test index statistics."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_stats_no_index(self):
        """Stats indicate when no index exists."""
        with patch("fork_utils.get_embeddings_dir", return_value=Path(self.temp_dir)):
            stats = get_index_stats()
            self.assertFalse(stats["exists"])
            self.assertEqual(stats["sessions"], 0)

    def test_stats_with_index(self):
        """Stats show correct info when index exists."""
        with patch("fork_utils.get_embeddings_dir", return_value=Path(self.temp_dir)):
            metadata = {
                "version": "1.0",
                "model": "test-model",
                "sessions": [{"id": "1"}, {"id": "2"}],
                "last_updated": "2026-01-20",
            }
            save_index(metadata, [[0.1], [0.2]])

            stats = get_index_stats()
            self.assertTrue(stats["exists"])
            self.assertEqual(stats["sessions"], 2)
            self.assertEqual(stats["model"], "test-model")


class TestLMStudioIntegration(unittest.TestCase):
    """Test LM Studio API integration (mocked)."""

    def test_check_available_success(self):
        """check_lmstudio_available returns True when API responds."""
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps({
            "data": [{"id": "nomic-embed-text-v1.5"}]
        }).encode()
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)

        with patch("urllib.request.urlopen", return_value=mock_response):
            available, msg = check_lmstudio_available()
            self.assertTrue(available)
            self.assertIn("nomic-embed-text-v1.5", msg)

    def test_check_available_failure(self):
        """check_lmstudio_available returns False when API fails."""
        import urllib.error
        with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("Connection refused")):
            available, msg = check_lmstudio_available()
            self.assertFalse(available)
            self.assertIn("Cannot connect", msg)

    def test_generate_embedding_success(self):
        """generate_embedding returns vector on success."""
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps({
            "data": [{"embedding": [0.1, 0.2, 0.3]}]
        }).encode()
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)

        with patch("urllib.request.urlopen", return_value=mock_response):
            embedding = generate_embedding("test text")
            self.assertEqual(embedding, [0.1, 0.2, 0.3])

    def test_generate_embedding_truncates_long_text(self):
        """generate_embedding truncates very long text."""
        long_text = "x" * 10000  # Longer than max_chars

        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps({
            "data": [{"embedding": [0.1]}]
        }).encode()
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)

        with patch("urllib.request.urlopen", return_value=mock_response) as mock_url:
            generate_embedding(long_text)
            # Verify the request was made (text truncated internally)
            mock_url.assert_called_once()


class TestSearchBackends(unittest.TestCase):
    """Test search backend selection and fallbacks (v1.1)."""

    def test_search_similar_uses_linear_fallback(self):
        """search_similar falls back to linear search when FAISS disabled."""
        query = [1.0, 0.0, 0.0]
        vectors = [
            [1.0, 0.0, 0.0],  # Exact match
            [0.0, 1.0, 0.0],  # Orthogonal
            [0.5, 0.5, 0.0],  # Partial
        ]

        # Force use_faiss=False to use fallback
        results = search_similar(query, vectors, top_k=3, use_faiss=False)

        # First result should be exact match
        self.assertEqual(results[0][0], 0)
        self.assertAlmostEqual(results[0][1], 1.0, places=3)

    def test_search_similar_respects_top_k(self):
        """search_similar respects top_k limit."""
        query = [1.0, 0.0, 0.0]
        vectors = [[1.0, 0.0, 0.0] for _ in range(10)]

        results = search_similar(query, vectors, top_k=3, use_faiss=False)
        self.assertEqual(len(results), 3)

    def test_search_similar_handles_empty_input(self):
        """search_similar handles empty vectors."""
        query = [1.0, 0.0, 0.0]
        results = search_similar(query, [], top_k=5)
        self.assertEqual(results, [])

    def test_search_similar_handles_empty_query(self):
        """search_similar handles empty query."""
        vectors = [[1.0, 0.0, 0.0]]
        results = search_similar([], vectors, top_k=5)
        self.assertEqual(results, [])


class TestSearchBackendSelection(unittest.TestCase):
    """Test get_search_backend function (v1.1)."""

    def test_get_search_backend_returns_string(self):
        """get_search_backend returns a descriptive string."""
        backend = get_search_backend()
        self.assertIsInstance(backend, str)
        # Should mention one of: FAISS, numpy, or pure Python
        self.assertTrue(
            any(x in backend.lower() for x in ["faiss", "numpy", "python"]),
            f"Backend '{backend}' doesn't mention expected backends"
        )


if __name__ == "__main__":
    unittest.main()
