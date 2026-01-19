#!/usr/bin/env python3
"""
Operator's Edge v7.1 - Pattern Recognition

DEPRECATED (v8.0): This module is superseded by context engineering.

The v7.1 pattern recognition system attempted to teach Claude software
methodology patterns (test-first, extract-then-integrate, etc.). However,
Claude already knows these patterns from training data.

v8.0 pivots to "Context Engineering" - keeping Claude on track through
supervision (drift detection, context compression) rather than training.

This module is preserved for backward compatibility but will not be
extended. See docs/v8-strategic-pivot.md for the rationale.

Original Purpose (Phase 2 of Learned Track Guidance):
- find_similar_objectives() - Match new objective to past completions
- compute_approach_similarity() - Compare verb sequences
- build_learned_pattern() - Aggregate completions into pattern
- get_pattern_suggestion() - Surface best match for planning
"""
import os
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Add hooks directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


# =============================================================================
# DATA STRUCTURES
# =============================================================================

@dataclass
class PatternMatch:
    """Result of matching an objective to a pattern."""
    pattern_id: str
    pattern_name: str
    source: str  # "learned" | "seed"
    confidence: float
    approach: List[Dict[str, str]]  # [{"verb": "scope", "description": "..."}]
    match_reasons: List[str]  # Why this matched
    samples: int  # How many completions contributed (0 for seed)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "pattern_id": self.pattern_id,
            "pattern_name": self.pattern_name,
            "source": self.source,
            "confidence": self.confidence,
            "approach": self.approach,
            "match_reasons": self.match_reasons,
            "samples": self.samples
        }


@dataclass
class LearnedPattern:
    """A pattern learned from objective completions."""
    id: str
    name: str
    source: str = "learned"
    tags: List[str] = field(default_factory=list)
    trigger_keywords: List[str] = field(default_factory=list)
    approach_verbs: List[str] = field(default_factory=list)
    approach: List[Dict[str, str]] = field(default_factory=list)
    confidence: float = 0.5
    samples: int = 0
    avg_steps: float = 0.0
    success_rate: float = 1.0
    last_used: str = ""
    source_objectives: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "source": self.source,
            "tags": self.tags,
            "trigger_keywords": self.trigger_keywords,
            "approach_verbs": self.approach_verbs,
            "approach": self.approach,
            "confidence": self.confidence,
            "samples": self.samples,
            "avg_steps": self.avg_steps,
            "success_rate": self.success_rate,
            "last_used": self.last_used,
            "source_objectives": self.source_objectives
        }


# =============================================================================
# CONFIGURATION LOADING
# =============================================================================

def _load_guidance_config() -> Dict[str, Any]:
    """Load the guidance configuration."""
    import yaml

    config_file = Path(__file__).parent / "guidance_config.yaml"
    if not config_file.exists():
        return {}

    try:
        with open(config_file) as f:
            return yaml.safe_load(f) or {}
    except Exception:
        return {}


def _get_seed_patterns() -> List[Dict[str, Any]]:
    """Get seed patterns from config."""
    config = _load_guidance_config()
    return config.get("seed_patterns", [])


def _get_confidence_settings() -> Dict[str, Any]:
    """Get confidence settings from config."""
    config = _load_guidance_config()
    return config.get("confidence", {
        "min_to_suggest": 0.4,
        "min_samples": 2
    })


def _get_matching_settings() -> Dict[str, Any]:
    """Get matching settings from config."""
    config = _load_guidance_config()
    return config.get("matching", {
        "strategy": "highest_confidence",
        "max_suggestions": 1,
        "keywords": {"min_matches": 1, "exclude_is_hard": True}
    })


# =============================================================================
# SIMILARITY FUNCTIONS
# =============================================================================

def compute_keyword_similarity(
    objective: str,
    keywords: List[str],
    exclude_keywords: List[str] = None
) -> Tuple[float, List[str]]:
    """
    Compute how well an objective matches keyword triggers.

    Returns (score 0-1, list of matched keywords).
    """
    if not objective or not keywords:
        return 0.0, []

    objective_lower = objective.lower()
    exclude_keywords = exclude_keywords or []

    # Check exclusions first
    settings = _get_matching_settings()
    if settings.get("keywords", {}).get("exclude_is_hard", True):
        for excl in exclude_keywords:
            if excl.lower() in objective_lower:
                return 0.0, []

    # Count keyword matches
    matches = []
    for kw in keywords:
        if kw.lower() in objective_lower:
            matches.append(kw)

    if not matches:
        return 0.0, []

    # Score: 1+ match gives base 0.6, each additional adds 0.15
    # This ensures a single strong keyword match still suggests the pattern
    base_score = 0.6
    additional = (len(matches) - 1) * 0.15
    score = min(base_score + additional, 1.0)
    return score, matches


def compute_tag_similarity(tags1: List[str], tags2: List[str]) -> float:
    """
    Compute Jaccard similarity between tag sets.

    Returns score 0-1.
    """
    if not tags1 or not tags2:
        return 0.0

    set1 = set(t.lower() for t in tags1)
    set2 = set(t.lower() for t in tags2)

    intersection = len(set1 & set2)
    union = len(set1 | set2)

    return intersection / union if union > 0 else 0.0


def compute_approach_similarity(verbs1: List[str], verbs2: List[str]) -> float:
    """
    Compute similarity between two verb sequences.

    Uses a combination of:
    - Set overlap (what verbs are present)
    - Sequence alignment (in what order)

    Returns score 0-1.
    """
    if not verbs1 or not verbs2:
        return 0.0

    # Set overlap score
    set1 = set(verbs1)
    set2 = set(verbs2)
    overlap = len(set1 & set2)
    union = len(set1 | set2)
    set_score = overlap / union if union > 0 else 0.0

    # Sequence alignment score (simplified LCS ratio)
    lcs_len = _longest_common_subsequence_length(verbs1, verbs2)
    max_len = max(len(verbs1), len(verbs2))
    seq_score = lcs_len / max_len if max_len > 0 else 0.0

    # Weight: 60% set overlap, 40% sequence
    return (0.6 * set_score) + (0.4 * seq_score)


def _longest_common_subsequence_length(seq1: List[str], seq2: List[str]) -> int:
    """Compute length of longest common subsequence."""
    m, n = len(seq1), len(seq2)
    if m == 0 or n == 0:
        return 0

    # DP table
    dp = [[0] * (n + 1) for _ in range(m + 1)]

    for i in range(1, m + 1):
        for j in range(1, n + 1):
            if seq1[i - 1] == seq2[j - 1]:
                dp[i][j] = dp[i - 1][j - 1] + 1
            else:
                dp[i][j] = max(dp[i - 1][j], dp[i][j - 1])

    return dp[m][n]


# =============================================================================
# PATTERN MATCHING
# =============================================================================

def find_similar_objectives(
    objective: str,
    completions: List[Dict[str, Any]],
    min_similarity: float = 0.3
) -> List[Tuple[Dict[str, Any], float, List[str]]]:
    """
    Find past objective completions similar to a new objective.

    Args:
        objective: The new objective text
        completions: List of completion records from archive
        min_similarity: Minimum similarity score to include

    Returns:
        List of (completion, score, reasons) tuples, sorted by score descending
    """
    if not objective or not completions:
        return []

    # Infer tags for the new objective
    from archive_utils import _infer_tags_from_objective
    new_tags = _infer_tags_from_objective(objective)

    results = []

    for comp in completions:
        if not isinstance(comp, dict):
            continue

        reasons = []
        scores = []

        # Tag similarity
        comp_tags = comp.get("tags", [])
        if comp_tags:
            tag_sim = compute_tag_similarity(new_tags, comp_tags)
            if tag_sim > 0:
                scores.append(tag_sim)
                reasons.append(f"Tags: {', '.join(set(new_tags) & set(comp_tags))}")

        # Keyword matching from objective text
        comp_obj = comp.get("objective", "")
        if comp_obj:
            # Extract keywords from past objective
            words = set(comp_obj.lower().split())
            new_words = set(objective.lower().split())
            common = words & new_words - {"the", "a", "an", "to", "for", "and", "or", "in", "on"}
            if len(common) >= 2:
                word_score = min(len(common) / 5, 1.0)
                scores.append(word_score)
                reasons.append(f"Keywords: {', '.join(list(common)[:3])}")

        if not scores:
            continue

        # Combined score
        combined = sum(scores) / len(scores)

        if combined >= min_similarity:
            results.append((comp, combined, reasons))

    # Sort by score descending
    results.sort(key=lambda x: x[1], reverse=True)

    return results


def match_seed_pattern(objective: str) -> Optional[PatternMatch]:
    """
    Match an objective against seed patterns.

    Returns best matching seed pattern, or None.
    """
    seed_patterns = _get_seed_patterns()
    if not seed_patterns:
        return None

    best_match = None
    best_score = 0.0

    for pattern in seed_patterns:
        keywords = pattern.get("trigger_keywords", [])
        excludes = pattern.get("exclude_keywords", [])

        score, matched = compute_keyword_similarity(objective, keywords, excludes)

        if score > best_score:
            best_score = score
            # Combine pattern's base confidence with match score
            # Score drives the match, base confidence is a floor
            base_conf = pattern.get("confidence", 0.5)
            combined_conf = max(base_conf, score * 0.8)  # 80% of match score
            best_match = PatternMatch(
                pattern_id=pattern.get("id", "unknown"),
                pattern_name=pattern.get("name", "Unknown Pattern"),
                source="seed",
                confidence=combined_conf,
                approach=pattern.get("approach", []),
                match_reasons=[f"Matched keywords: {', '.join(matched)}"],
                samples=0
            )

    settings = _get_confidence_settings()
    if best_match and best_match.confidence >= settings.get("min_to_suggest", 0.4):
        return best_match

    return None


# =============================================================================
# PATTERN BUILDING
# =============================================================================

def build_learned_pattern(
    completions: List[Dict[str, Any]],
    pattern_id: str = None
) -> Optional[LearnedPattern]:
    """
    Build a learned pattern from a cluster of similar completions.

    Aggregates:
    - Common tags → trigger keywords
    - Most common verb sequence → approach
    - Success rate and average steps

    Args:
        completions: List of similar completion records
        pattern_id: Optional ID override

    Returns:
        LearnedPattern if enough samples, None otherwise
    """
    settings = _get_confidence_settings()
    min_samples = settings.get("min_samples", 2)

    if len(completions) < min_samples:
        return None

    # Aggregate tags
    all_tags = []
    for comp in completions:
        all_tags.extend(comp.get("tags", []))

    # Find most common tags
    tag_counts = {}
    for tag in all_tags:
        tag_counts[tag] = tag_counts.get(tag, 0) + 1

    common_tags = [t for t, c in sorted(tag_counts.items(), key=lambda x: -x[1])
                   if c >= len(completions) * 0.5]  # Present in at least 50%

    # Aggregate approach verbs
    all_verb_seqs = [comp.get("approach_verbs", []) for comp in completions]

    # Find canonical verb sequence (most common length, then most common verbs at each position)
    if not all_verb_seqs or not any(all_verb_seqs):
        return None

    # Use the most common sequence length
    lengths = [len(s) for s in all_verb_seqs if s]
    if not lengths:
        return None

    common_length = max(set(lengths), key=lengths.count)

    # Build canonical sequence
    canonical_verbs = []
    for i in range(common_length):
        verbs_at_pos = [s[i] for s in all_verb_seqs if len(s) > i]
        if verbs_at_pos:
            most_common = max(set(verbs_at_pos), key=verbs_at_pos.count)
            canonical_verbs.append(most_common)

    # Build approach with descriptions from completions
    approach = []
    for verb in canonical_verbs:
        # Find a description from completions
        desc = ""
        for comp in completions:
            for step in comp.get("approach_summary", []):
                if step.get("verb") == verb and step.get("description"):
                    desc = step.get("description", "")
                    break
            if desc:
                break

        approach.append({"verb": verb, "description": desc or f"{verb.capitalize()} step"})

    # Compute metrics
    step_counts = [comp.get("metrics", {}).get("steps_completed", 0) for comp in completions]
    avg_steps = sum(step_counts) / len(step_counts) if step_counts else 0

    success_count = sum(1 for comp in completions if comp.get("outcome", {}).get("success", False))
    success_rate = success_count / len(completions) if completions else 0

    # Compute confidence based on samples and success rate
    base_confidence = min(0.5 + (len(completions) * 0.1), 0.9)  # More samples = more confidence
    confidence = base_confidence * success_rate

    # Extract keywords from objectives
    keywords = set()
    for comp in completions:
        obj = comp.get("objective", "").lower()
        for tag in common_tags:
            if tag in obj:
                keywords.add(tag)

    # Generate ID if not provided
    if not pattern_id:
        pattern_id = f"learned-{'-'.join(common_tags[:2]) if common_tags else 'pattern'}-{len(completions)}"

    # Generate name
    name = " + ".join(t.capitalize() for t in common_tags[:2]) if common_tags else "Learned Pattern"

    return LearnedPattern(
        id=pattern_id,
        name=name,
        source="learned",
        tags=common_tags,
        trigger_keywords=list(keywords),
        approach_verbs=canonical_verbs,
        approach=approach,
        confidence=confidence,
        samples=len(completions),
        avg_steps=avg_steps,
        success_rate=success_rate,
        last_used=datetime.now().isoformat(),
        source_objectives=[comp.get("objective", "")[:100] for comp in completions]
    )


# =============================================================================
# PATTERN SUGGESTION
# =============================================================================

def get_pattern_suggestion(
    objective: str,
    include_seeds: bool = True
) -> Optional[PatternMatch]:
    """
    Get the best pattern suggestion for a new objective.

    Process:
    1. Load past completions from archive
    2. Find similar completions
    3. If enough similar, build learned pattern
    4. Compare against seed patterns
    5. Return best match above confidence threshold

    Args:
        objective: The new objective text
        include_seeds: Whether to consider seed patterns

    Returns:
        PatternMatch if a good suggestion found, None otherwise
    """
    from archive_utils import get_objective_completions

    settings = _get_confidence_settings()
    min_confidence = settings.get("min_to_suggest", 0.4)
    min_samples = settings.get("min_samples", 2)

    # Get past completions
    completions = get_objective_completions(limit=100)

    candidates = []

    # Try to build learned pattern from similar completions
    if completions:
        similar = find_similar_objectives(objective, completions, min_similarity=0.3)

        if len(similar) >= min_samples:
            # Extract just the completions
            similar_comps = [s[0] for s in similar[:10]]  # Top 10 most similar

            learned = build_learned_pattern(similar_comps)
            if learned:
                # Compute match confidence
                match_reasons = [f"Similar to {learned.samples} past objectives"]
                if similar[0][2]:  # Reasons from top match
                    match_reasons.extend(similar[0][2])

                candidates.append(PatternMatch(
                    pattern_id=learned.id,
                    pattern_name=learned.name,
                    source="learned",
                    confidence=learned.confidence,
                    approach=learned.approach,
                    match_reasons=match_reasons,
                    samples=learned.samples
                ))

    # Try seed patterns
    if include_seeds:
        seed_match = match_seed_pattern(objective)
        if seed_match:
            candidates.append(seed_match)

    if not candidates:
        return None

    # Sort by confidence
    candidates.sort(key=lambda x: x.confidence, reverse=True)

    # Return best if above threshold
    best = candidates[0]
    if best.confidence >= min_confidence:
        return best

    return None


def get_all_pattern_suggestions(
    objective: str,
    max_suggestions: int = 3
) -> List[PatternMatch]:
    """
    Get all pattern suggestions above threshold.

    Useful for showing user multiple options.
    """
    from archive_utils import get_objective_completions

    settings = _get_confidence_settings()
    min_confidence = settings.get("min_to_suggest", 0.4)

    completions = get_objective_completions(limit=100)
    candidates = []

    # Learned pattern
    if completions:
        similar = find_similar_objectives(objective, completions, min_similarity=0.3)

        if len(similar) >= 2:
            similar_comps = [s[0] for s in similar[:10]]
            learned = build_learned_pattern(similar_comps)
            if learned:
                candidates.append(PatternMatch(
                    pattern_id=learned.id,
                    pattern_name=learned.name,
                    source="learned",
                    confidence=learned.confidence,
                    approach=learned.approach,
                    match_reasons=[f"Similar to {learned.samples} past objectives"],
                    samples=learned.samples
                ))

    # All matching seed patterns
    seed_patterns = _get_seed_patterns()
    for pattern in seed_patterns:
        keywords = pattern.get("trigger_keywords", [])
        excludes = pattern.get("exclude_keywords", [])

        score, matched = compute_keyword_similarity(objective, keywords, excludes)
        if score > 0:
            conf = pattern.get("confidence", 0.5) * score
            if conf >= min_confidence:
                candidates.append(PatternMatch(
                    pattern_id=pattern.get("id", "unknown"),
                    pattern_name=pattern.get("name", "Unknown"),
                    source="seed",
                    confidence=conf,
                    approach=pattern.get("approach", []),
                    match_reasons=[f"Keywords: {', '.join(matched)}"],
                    samples=0
                ))

    # Sort and limit
    candidates.sort(key=lambda x: x.confidence, reverse=True)
    return candidates[:max_suggestions]


# =============================================================================
# PATTERN DISPLAY
# =============================================================================

def format_pattern_suggestion(match: PatternMatch) -> str:
    """
    Format a pattern suggestion for display to user.

    Returns markdown-formatted suggestion.
    """
    lines = []

    # Header
    source_emoji = "📚" if match.source == "learned" else "📋"
    confidence_pct = int(match.confidence * 100)

    lines.append(f"### {source_emoji} Suggested Approach: {match.pattern_name}")
    lines.append(f"*Confidence: {confidence_pct}%* | *Source: {match.source}*")

    if match.samples > 0:
        lines.append(f"*Based on {match.samples} similar objectives*")

    lines.append("")

    # Approach steps
    lines.append("**Recommended Steps:**")
    for i, step in enumerate(match.approach, 1):
        verb = step.get("verb", "?")
        desc = step.get("description", "")
        lines.append(f"{i}. **{verb.upper()}**: {desc}")

    lines.append("")

    # Match reasons
    if match.match_reasons:
        lines.append(f"*Why this matched: {'; '.join(match.match_reasons)}*")

    return "\n".join(lines)


# =============================================================================
# CONVENIENCE FUNCTION FOR PLANNING
# =============================================================================

def suggest_approach_for_objective(objective: str) -> Tuple[Optional[str], Optional[PatternMatch]]:
    """
    Main entry point for pattern suggestion during planning.

    Returns:
        (formatted_suggestion, pattern_match) or (None, None) if no suggestion
    """
    match = get_pattern_suggestion(objective, include_seeds=True)

    if match:
        formatted = format_pattern_suggestion(match)
        return formatted, match

    return None, None
