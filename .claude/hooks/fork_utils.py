#!/usr/bin/env python3
"""
Operator's Edge - Fork Utils
Core infrastructure for Smart Forking (/edge-fork).

Provides:
- LM Studio API integration for embeddings
- Cosine similarity calculation
- Index load/save operations
"""
import json
import os
from pathlib import Path
from typing import List, Optional, Tuple, Dict, Any
import urllib.request
import urllib.error

# Try numpy, fallback to pure Python
try:
    import numpy as np
    HAS_NUMPY = True
except ImportError:
    HAS_NUMPY = False

# Try FAISS for Approximate Nearest Neighbor search
try:
    import faiss
    HAS_FAISS = True
except ImportError:
    HAS_FAISS = False


# Default LM Studio configuration
DEFAULT_LMSTUDIO_URL = "http://192.168.254.68:1234"
DEFAULT_EMBEDDING_MODEL = "text-embedding-nomic-embed-text-v1.5"
EMBEDDING_DIMENSION = 768


def get_embeddings_dir() -> Path:
    """Get the embeddings storage directory."""
    project_dir = Path(os.environ.get("CLAUDE_PROJECT_DIR", Path.cwd()))
    embeddings_dir = project_dir / ".claude" / "embeddings"
    embeddings_dir.mkdir(parents=True, exist_ok=True)
    return embeddings_dir


def get_config_path() -> Path:
    """Get the config file path."""
    return get_embeddings_dir() / "config.json"


def load_config() -> Dict[str, Any]:
    """Load fork configuration from file."""
    config_path = get_config_path()
    if config_path.exists():
        with open(config_path) as f:
            return json.load(f)
    return {}


def save_config(config: Dict[str, Any]) -> None:
    """Save fork configuration to file."""
    config_path = get_config_path()
    with open(config_path, "w") as f:
        json.dump(config, f, indent=2)


def get_lmstudio_url() -> str:
    """
    Get the configured LM Studio URL.

    Priority:
    1. Environment variable LMSTUDIO_URL
    2. Config file setting
    3. Default value
    """
    # Check environment
    if os.environ.get("LMSTUDIO_URL"):
        return os.environ["LMSTUDIO_URL"]

    # Check config
    config = load_config()
    if config.get("lmstudio_url"):
        return config["lmstudio_url"]

    return DEFAULT_LMSTUDIO_URL


def check_lmstudio_available() -> Tuple[bool, str]:
    """
    Check if LM Studio is available and responding.

    Returns:
        Tuple of (is_available, message)
    """
    url = get_lmstudio_url()
    try:
        req = urllib.request.Request(
            f"{url}/v1/models",
            headers={"Content-Type": "application/json"},
            method="GET"
        )
        with urllib.request.urlopen(req, timeout=5) as response:
            data = json.loads(response.read().decode())
            models = data.get("data", [])
            model_names = [m.get("id", "unknown") for m in models]
            return True, f"LM Studio available at {url} with models: {', '.join(model_names[:3])}"
    except urllib.error.URLError as e:
        return False, f"Cannot connect to LM Studio at {url}: {e.reason}"
    except Exception as e:
        return False, f"Error checking LM Studio: {e}"


def generate_embedding(text: str, model: str = None) -> Optional[List[float]]:
    """
    Generate embedding vector for text using LM Studio.

    Args:
        text: The text to embed
        model: Embedding model name (default: nomic-embed-text-v1.5)

    Returns:
        List of floats representing the embedding vector, or None on error
    """
    url = get_lmstudio_url()
    model = model or DEFAULT_EMBEDDING_MODEL

    # Truncate very long text (embeddings have context limits)
    max_chars = 8000  # ~2k tokens for most models
    if len(text) > max_chars:
        text = text[:max_chars]

    payload = {
        "model": model,
        "input": text
    }

    try:
        req = urllib.request.Request(
            f"{url}/v1/embeddings",
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=30) as response:
            data = json.loads(response.read().decode())
            embeddings = data.get("data", [])
            if embeddings and "embedding" in embeddings[0]:
                return embeddings[0]["embedding"]
            return None
    except Exception as e:
        # Log error but don't crash
        print(f"Embedding generation error: {e}", file=__import__("sys").stderr)
        return None


def cosine_similarity(vec1: List[float], vec2: List[float]) -> float:
    """
    Calculate cosine similarity between two vectors.

    Uses numpy if available, otherwise pure Python.

    Args:
        vec1: First embedding vector
        vec2: Second embedding vector

    Returns:
        Cosine similarity score between -1 and 1
    """
    if HAS_NUMPY:
        a = np.array(vec1)
        b = np.array(vec2)
        norm_a = np.linalg.norm(a)
        norm_b = np.linalg.norm(b)
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return float(np.dot(a, b) / (norm_a * norm_b))
    else:
        # Pure Python fallback
        dot_product = sum(a * b for a, b in zip(vec1, vec2))
        norm1 = sum(x ** 2 for x in vec1) ** 0.5
        norm2 = sum(x ** 2 for x in vec2) ** 0.5
        if norm1 == 0 or norm2 == 0:
            return 0.0
        return dot_product / (norm1 * norm2)


def load_index() -> Tuple[Optional[Dict], Optional[List[List[float]]]]:
    """
    Load the embedding index from disk.

    Returns:
        Tuple of (metadata dict, vectors list) or (None, None) if not found
    """
    embeddings_dir = get_embeddings_dir()
    index_path = embeddings_dir / "index.json"
    vectors_path = embeddings_dir / "vectors.npy"

    if not index_path.exists():
        return None, None

    # Load metadata
    with open(index_path) as f:
        metadata = json.load(f)

    # Load vectors
    vectors = None
    if vectors_path.exists() and HAS_NUMPY:
        vectors = np.load(str(vectors_path)).tolist()
    else:
        # Fallback: vectors stored in metadata
        vectors = metadata.get("_vectors_fallback", [])

    return metadata, vectors


def save_index(metadata: Dict, vectors: List[List[float]]) -> None:
    """
    Save the embedding index to disk.

    Args:
        metadata: Index metadata including session info
        vectors: List of embedding vectors
    """
    embeddings_dir = get_embeddings_dir()
    index_path = embeddings_dir / "index.json"
    vectors_path = embeddings_dir / "vectors.npy"

    # Save vectors
    if HAS_NUMPY and vectors:
        np.save(str(vectors_path), np.array(vectors))
    else:
        # Fallback: store in metadata
        metadata["_vectors_fallback"] = vectors

    # Save metadata
    with open(index_path, "w") as f:
        json.dump(metadata, f, indent=2)


def search_similar(
    query_vector: List[float],
    vectors: List[List[float]],
    top_k: int = 5,
    use_faiss: bool = True
) -> List[Tuple[int, float]]:
    """
    Search for most similar vectors.

    Uses FAISS for Approximate Nearest Neighbor search if available,
    falls back to numpy/pure Python linear search otherwise.

    Args:
        query_vector: Query embedding
        vectors: List of indexed embeddings
        top_k: Number of results to return
        use_faiss: If True and FAISS is available, use FAISS search

    Returns:
        List of (index, similarity_score) tuples, sorted by score descending
    """
    if not vectors or not query_vector:
        return []

    # FAISS search (fast for large indexes)
    if use_faiss and HAS_FAISS and HAS_NUMPY and len(vectors) > 10:
        return _search_faiss(query_vector, vectors, top_k)

    # Numpy linear search (fast enough for < 1000 vectors)
    if HAS_NUMPY:
        return _search_numpy(query_vector, vectors, top_k)

    # Pure Python fallback
    return _search_linear(query_vector, vectors, top_k)


def _search_faiss(
    query_vector: List[float],
    vectors: List[List[float]],
    top_k: int
) -> List[Tuple[int, float]]:
    """FAISS-based search using cosine similarity (via inner product on normalized vectors)."""
    # Convert to numpy arrays
    query_np = np.array([query_vector], dtype=np.float32)
    vectors_np = np.array(vectors, dtype=np.float32)

    # Normalize vectors for cosine similarity
    faiss.normalize_L2(query_np)
    faiss.normalize_L2(vectors_np)

    # Create index (Inner Product = cosine similarity for normalized vectors)
    dimension = len(query_vector)
    index = faiss.IndexFlatIP(dimension)
    index.add(vectors_np)

    # Search
    k = min(top_k, len(vectors))
    distances, indices = index.search(query_np, k)

    # Convert to (index, score) tuples
    results = []
    for i, (idx, score) in enumerate(zip(indices[0], distances[0])):
        if idx >= 0:  # FAISS returns -1 for unfilled slots
            results.append((int(idx), float(score)))

    return results


def _search_numpy(
    query_vector: List[float],
    vectors: List[List[float]],
    top_k: int
) -> List[Tuple[int, float]]:
    """Numpy-based vectorized cosine similarity search."""
    query_np = np.array(query_vector)
    vectors_np = np.array(vectors)

    # Compute cosine similarity for all vectors at once
    query_norm = np.linalg.norm(query_np)
    if query_norm == 0:
        return []

    vectors_norm = np.linalg.norm(vectors_np, axis=1)
    # Avoid division by zero
    vectors_norm = np.where(vectors_norm == 0, 1, vectors_norm)

    similarities = np.dot(vectors_np, query_np) / (vectors_norm * query_norm)

    # Get top_k indices
    top_indices = np.argsort(similarities)[::-1][:top_k]

    return [(int(idx), float(similarities[idx])) for idx in top_indices]


def _search_linear(
    query_vector: List[float],
    vectors: List[List[float]],
    top_k: int
) -> List[Tuple[int, float]]:
    """Pure Python linear search fallback."""
    scores = []
    for i, vec in enumerate(vectors):
        similarity = cosine_similarity(query_vector, vec)
        scores.append((i, similarity))

    # Sort by similarity descending
    scores.sort(key=lambda x: x[1], reverse=True)

    return scores[:top_k]


def get_index_stats() -> Dict[str, Any]:
    """
    Get statistics about the current index.

    Returns:
        Dict with index statistics
    """
    metadata, vectors = load_index()

    if metadata is None:
        return {
            "exists": False,
            "sessions": 0,
            "last_updated": None,
            "model": None,
            "search_backend": get_search_backend(),
        }

    return {
        "exists": True,
        "sessions": len(metadata.get("sessions", [])),
        "last_updated": metadata.get("last_updated"),
        "model": metadata.get("model", DEFAULT_EMBEDDING_MODEL),
        "dimension": metadata.get("dimension", EMBEDDING_DIMENSION),
        "version": metadata.get("version", "1.0"),
        "search_backend": get_search_backend(),
    }


def get_search_backend() -> str:
    """
    Get the current search backend being used.

    Returns:
        String describing the search backend
    """
    if HAS_FAISS and HAS_NUMPY:
        return "FAISS (ANN)"
    elif HAS_NUMPY:
        return "numpy (linear)"
    else:
        return "pure Python (linear)"
