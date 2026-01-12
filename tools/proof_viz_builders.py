#!/usr/bin/env python3
"""
Proof Visualizer - Data Builders
Functions for building timeline, graph, and diff cache data structures.
"""
from pathlib import Path
from datetime import datetime
from collections import defaultdict
from typing import List, Dict, Any

from proof_viz_config import get_action_type
from proof_viz_loaders import extract_file_path


def build_timeline(entries: List[Dict]) -> List[Dict]:
    """Build timeline data for visualization with action types."""
    timeline = []
    for entry in entries:
        ts = entry.get('timestamp', '')
        tool = entry.get('tool', 'unknown')
        success = entry.get('success', True)
        file_path = extract_file_path(entry.get('input_preview'))
        action_type = get_action_type(tool, success)

        timeline.append({
            'timestamp': ts,
            'tool': tool,
            'success': success,
            'file': Path(file_path).name if file_path else None,
            'full_path': file_path,
            'action': action_type,
        })
    return timeline


def build_diff_cache(entries: List[Dict], max_diff_chars: int = 2000) -> Dict[str, List[Dict]]:
    """Build diff cache from Edit entries that have old_string/new_string.

    Args:
        entries: List of log entries
        max_diff_chars: Maximum characters per diff (old/new). Diffs larger than this are truncated.

    Returns: dict mapping file path -> list of {timestamp, old, new, truncated} dicts
    """
    def truncate(s: str) -> tuple:
        """Truncate string if too long, return (string, was_truncated)."""
        if len(s) <= max_diff_chars:
            return s, False
        return s[:max_diff_chars] + "\n… (truncated)", True

    diff_cache = defaultdict(list)

    for entry in entries:
        tool = entry.get('tool', '')
        if tool != 'Edit':
            continue

        input_preview = entry.get('input_preview', {})
        if not isinstance(input_preview, dict):
            continue

        file_path = input_preview.get('file', '')
        old_string = input_preview.get('old_string', '')
        new_string = input_preview.get('new_string', '')

        # Only include entries with actual diff content
        if not file_path or not old_string or not new_string:
            continue

        # Skip if old and new are the same (shouldn't happen, but be safe)
        if old_string == new_string:
            continue

        # Truncate large diffs to prevent HTML bloat
        old_truncated, old_was_truncated = truncate(old_string)
        new_truncated, new_was_truncated = truncate(new_string)

        timestamp = entry.get('timestamp', '')
        diff_cache[file_path].append({
            'timestamp': timestamp,
            'old': old_truncated,
            'new': new_truncated,
            'truncated': old_was_truncated or new_was_truncated
        })

    # Sort each file's diffs by timestamp (most recent first)
    for file_path in diff_cache:
        diff_cache[file_path].sort(key=lambda x: x['timestamp'], reverse=True)

    return dict(diff_cache)


def build_dependency_graph(entries: List[Dict]) -> Dict:
    """Build tool → file dependency graph with touch counts, action breakdown, and directory clustering."""
    node_counts = defaultdict(int)  # node_id → touch count
    edge_counts = defaultdict(int)  # (source, target) → count
    node_types = {}  # node_id → type
    node_paths = {}  # node_id → full path (for files)
    node_timestamps = defaultdict(list)  # node_id → list of timestamps
    node_dirs = {}  # node_id → directory name (for clustering)
    node_actions = defaultdict(lambda: defaultdict(int))  # node_id → {action → count}

    for entry in entries:
        tool = entry.get('tool', 'unknown')
        file_path = extract_file_path(entry.get('input_preview'))
        timestamp = entry.get('timestamp', '')
        success = entry.get('success', True)
        action_type = get_action_type(tool, success)

        tool_id = f"tool:{tool}"
        node_counts[tool_id] += 1
        node_types[tool_id] = 'tool'
        node_actions[tool_id][action_type] += 1
        if timestamp:
            node_timestamps[tool_id].append(timestamp)

        if file_path:
            short_name = Path(file_path).name
            file_id = f"file:{short_name}"
            node_counts[file_id] += 1
            node_types[file_id] = 'file'
            node_paths[file_id] = file_path
            node_actions[file_id][action_type] += 1
            # Extract directory for clustering
            dir_path = str(Path(file_path).parent)
            dir_name = Path(dir_path).name or 'root'
            node_dirs[file_id] = dir_name
            if timestamp:
                node_timestamps[file_id].append(timestamp)
            edge_counts[(tool_id, file_id)] += 1

    nodes = []
    for node_id, count in node_counts.items():
        # Get action breakdown for this node
        actions = dict(node_actions[node_id])
        # Determine dominant action (most common)
        dominant = max(actions.keys(), key=lambda a: actions[a]) if actions else 'other'

        node = {
            'id': node_id,
            'type': node_types[node_id],
            'count': count,
            'timestamps': node_timestamps[node_id][-10:],  # Last 10
            'actions': actions,  # {read: N, edit: N, run: N, fail: N}
            'dominant': dominant,  # Most common action type
        }
        if node_id in node_paths:
            node['path'] = node_paths[node_id]
        if node_id in node_dirs:
            node['dir'] = node_dirs[node_id]
        # Compute recency score (hours since last touch)
        if node_timestamps[node_id]:
            try:
                last_ts = node_timestamps[node_id][-1]
                last_dt = datetime.fromisoformat(last_ts.replace('Z', '+00:00'))
                hours_ago = (datetime.now() - last_dt.replace(tzinfo=None)).total_seconds() / 3600
                node['recency'] = round(hours_ago, 1)
            except:
                node['recency'] = 999
        nodes.append(node)

    edges = [
        {'source': src, 'target': tgt, 'count': cnt}
        for (src, tgt), cnt in edge_counts.items()
    ]

    # Compute directory clusters
    dir_counts = defaultdict(int)
    for node in nodes:
        if node.get('dir'):
            dir_counts[node['dir']] += 1

    clusters = [
        {'name': d, 'count': c}
        for d, c in sorted(dir_counts.items(), key=lambda x: -x[1])
    ]

    return {'nodes': nodes, 'edges': edges, 'clusters': clusters}


def compute_nebula_clusters(nodes: List[Dict], edges: List[Dict], min_cluster_size: int = 3) -> Dict[str, int]:
    """
    Compute directory clusters.
    Returns mapping of node_id -> cluster_id.

    Files in the same directory belong to the same cluster.
    Small clusters (< min_cluster_size) are assigned to cluster -1 (unclustered).
    """
    if not nodes:
        return {}

    # Group nodes by directory
    dir_groups = {}
    for node in nodes:
        # Extract directory from node path
        node_id = node.get('id', '')
        # node_id format: "path/to/file.py" - get directory
        if '/' in node_id:
            directory = '/'.join(node_id.split('/')[:-1]) or 'root'
        else:
            directory = 'root'

        if directory not in dir_groups:
            dir_groups[directory] = []
        dir_groups[directory].append(node_id)

    # Assign cluster IDs, filtering small clusters
    cluster_id_map = {}
    cluster_id = 0

    # Sort directories by size (largest first) for consistent coloring
    sorted_dirs = sorted(dir_groups.items(), key=lambda x: len(x[1]), reverse=True)

    for directory, node_ids in sorted_dirs:
        if len(node_ids) >= min_cluster_size:
            for nid in node_ids:
                cluster_id_map[nid] = cluster_id
            cluster_id += 1
        else:
            # Small clusters get -1 (unclustered)
            for nid in node_ids:
                cluster_id_map[nid] = -1

    return cluster_id_map


def compute_nebula_clusters_topology(nodes: List[Dict], edges: List[Dict], min_cluster_size: int = 3) -> Dict[str, int]:
    """
    Compute semantic clusters using graph topology (connected components).
    Returns mapping of node_id -> cluster_id.

    Components smaller than min_cluster_size are assigned to cluster -1.
    """
    if not nodes:
        return {}

    node_ids = {node.get('id') for node in nodes if node.get('id')}
    adjacency = {node_id: set() for node_id in node_ids}

    for edge in edges or []:
        src = edge.get('source')
        tgt = edge.get('target')
        if isinstance(src, dict):
            src = src.get('id')
        if isinstance(tgt, dict):
            tgt = tgt.get('id')
        if not src or not tgt:
            continue
        if src not in adjacency or tgt not in adjacency:
            continue
        adjacency[src].add(tgt)
        adjacency[tgt].add(src)

    visited = set()
    cluster_id_map: Dict[str, int] = {}
    cluster_id = 0

    for node_id in adjacency:
        if node_id in visited:
            continue
        stack = [node_id]
        component = []
        visited.add(node_id)
        while stack:
            current = stack.pop()
            component.append(current)
            for neighbor in adjacency[current]:
                if neighbor not in visited:
                    visited.add(neighbor)
                    stack.append(neighbor)

        if len(component) >= min_cluster_size:
            for nid in component:
                cluster_id_map[nid] = cluster_id
            cluster_id += 1
        else:
            for nid in component:
                cluster_id_map[nid] = -1

    return cluster_id_map
