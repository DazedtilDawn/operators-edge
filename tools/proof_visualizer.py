#!/usr/bin/env python3
"""
Proof Visualizer - Session Analysis Tool
Facade module that re-exports from focused submodules.

Usage:
    python3 tools/proof_visualizer.py [log_path] [--out output.html] [--history]

Submodules:
    proof_viz_config   - Constants, thresholds, tool classifications
    proof_viz_loaders  - File I/O, data loading
    proof_viz_builders - Timeline, graph, diff cache building
    proof_viz_analysis - Stats, insights, phases, anomalies
    proof_viz_export   - Report generation, CTI history
    proof_viz_render   - HTML generation with external assets
"""
import sys
import json
from pathlib import Path
from typing import List, Dict, Any, Optional

# Re-export from submodules for backward compatibility
from proof_viz_config import (
    READ_TOOLS,
    EDIT_TOOLS,
    RUN_TOOLS,
    DEFAULT_MIN_STREAK,
    DEFAULT_MIN_PHASE_SIZE,
    ANOMALY_SIGMA,
    CTI_DRIFT_THRESHOLD,
    CONSTELLATION_STARS,
    CONSTELLATION_CONTEXT,
    HOVER_REVEAL_RADIUS,
    get_action_type,
)

from proof_viz_loaders import (
    load_proof_log,
    extract_file_path,
    load_cti_history,
)

from proof_viz_builders import (
    build_timeline,
    build_diff_cache,
    build_dependency_graph,
    compute_nebula_clusters,
    compute_nebula_clusters_topology,
)

from proof_viz_analysis import (
    compute_stats,
    compute_insights,
    compute_phase_cti,
    compute_phase_duration,
    format_duration,
    detect_phases,
    generate_phase_summary,
    compute_anomalies,
    compute_beginner_view,
    compute_summary,
)

from proof_viz_export import (
    export_anomaly_report,
    export_phase_summary,
    append_cti_history,
    check_drift,
)

from proof_viz_render import generate_html

# Public API
__all__ = [
    # Config
    'READ_TOOLS', 'EDIT_TOOLS', 'RUN_TOOLS',
    'DEFAULT_MIN_STREAK', 'DEFAULT_MIN_PHASE_SIZE',
    'ANOMALY_SIGMA', 'CTI_DRIFT_THRESHOLD',
    'CONSTELLATION_STARS', 'CONSTELLATION_CONTEXT',
    'HOVER_REVEAL_RADIUS', 'get_action_type',
    # Loaders
    'load_proof_log', 'extract_file_path', 'load_cti_history',
    # Builders
    'build_timeline', 'build_diff_cache', 'build_dependency_graph',
    'compute_nebula_clusters', 'compute_nebula_clusters_topology',
    # Analysis
    'compute_stats', 'compute_insights', 'compute_phase_cti',
    'compute_phase_duration', 'format_duration', 'detect_phases',
    'generate_phase_summary', 'compute_anomalies',
    'compute_beginner_view', 'compute_summary',
    # Export
    'export_anomaly_report', 'export_phase_summary',
    'append_cti_history', 'check_drift',
    # Render
    'generate_html',
    # Main
    'main',
]


def main():
    """Main entry point for proof visualization generation."""
    # Parse args
    args = sys.argv[1:]
    log_path = Path('.proof/session_log.jsonl')
    out_path = Path('proof_viz.html')
    history_path = Path('.proof/cti_history.csv')
    track_history = False
    inline_assets = False

    i = 0
    while i < len(args):
        if args[i] == '--out' and i + 1 < len(args):
            out_path = Path(args[i + 1])
            i += 2
        elif args[i] == '--history':
            track_history = True
            i += 1
        elif args[i] == '--inline':
            inline_assets = True
            i += 1
        elif not args[i].startswith('-'):
            log_path = Path(args[i])
            i += 1
        else:
            i += 1

    if not log_path.exists():
        print(f"Error: {log_path} not found")
        sys.exit(1)

    print(f"Loading {log_path}...")
    entries = load_proof_log(log_path)
    print(f"Loaded {len(entries)} entries")

    timeline = build_timeline(entries)
    graph = build_dependency_graph(entries)
    stats = compute_stats(entries)
    insights = compute_insights(graph, stats)

    cti_val = float(stats['cti'].rstrip('%'))
    print(f"Stats: {stats['total_events']} events, {stats['success_rate']} success, CTI={stats['cti']}")
    print(f"Insights: {len(insights)} generated")

    # Drift detection (compute before summary so we can include it)
    drift_msg = None
    if track_history:
        history = load_cti_history(history_path)
        drift_msg = check_drift(history, cti_val)
        if drift_msg:
            print(f"Drift: {drift_msg}")
        append_cti_history(history_path, stats)
        print(f"History: {len(history) + 1} runs tracked in {history_path}")

    summary = compute_summary(graph, stats, insights, drift_msg)
    print(f"Summary: generated")

    beginner_view = compute_beginner_view(stats, graph)
    print(f"Quick View: {beginner_view['status_text']} (Health: {beginner_view['health_score']}%)")

    # Export anomaly report
    anomalies = compute_anomalies(graph)
    if anomalies:
        anomaly_path = Path('.proof/anomaly_report.json')
        export_anomaly_report(anomalies, anomaly_path)
        print(f"Anomalies: {len(anomalies)} detected (>{ANOMALY_SIGMA}σ)")

    # Detect phases for Story Mode
    phases = detect_phases(entries)
    phase_summary_text = generate_phase_summary(phases, entries)
    print(f"Phases: {len(phases)} detected")

    # Export phase summary JSON
    phase_summary_path = Path('.proof/phase_summary.json')
    phase_summary = export_phase_summary(phases, entries, phase_summary_path)
    print(f"Phase summary: exported to {phase_summary_path}")

    # Load dependencies for Explorer Mode
    deps_path = Path('.proof/dependencies.json')
    explorer_data = None
    if deps_path.exists():
        try:
            explorer_data = json.loads(deps_path.read_text())
            # Mark existing edges as co-occurrence type
            for edge in explorer_data.get('edges', []):
                edge['edgeType'] = 'cooccur'
            print(f"Explorer: {explorer_data['stats']['total_files']} files, {explorer_data['stats']['total_edges']} co-occur edges")
        except Exception:
            pass

    # Load import graph and merge into explorer data
    import_graph_path = Path('.proof/import_graph.json')
    if import_graph_path.exists() and explorer_data:
        try:
            import_graph = json.loads(import_graph_path.read_text())
            import_edges = import_graph.get('edges', [])

            # Get existing node IDs
            existing_node_ids = {n['id'] for n in explorer_data.get('nodes', [])}

            # Add import edges (only for files that exist in explorer_data)
            added_edges = 0
            for edge in import_edges:
                if edge['source'] in existing_node_ids and edge['target'] in existing_node_ids:
                    explorer_data['edges'].append({
                        'source': edge['source'],
                        'target': edge['target'],
                        'type': 'import',
                        'edgeType': 'import',
                        'weight': edge.get('weight', 1)
                    })
                    added_edges += 1

            explorer_data['stats']['import_edges'] = added_edges
            print(f"Explorer: added {added_edges} import edges")
        except Exception as e:
            print(f"Warning: Could not load import graph: {e}")

    # Compute nebula clusters (directory default + semantic topology)
    if explorer_data:
        cluster_map_dir = compute_nebula_clusters(
            explorer_data.get('nodes', []),
            explorer_data.get('edges', []),
            min_cluster_size=3
        )
        cluster_map_semantic = compute_nebula_clusters_topology(
            explorer_data.get('nodes', []),
            explorer_data.get('edges', []),
            min_cluster_size=3
        )

        # Add cluster assignments to nodes (directory is default)
        for node in explorer_data.get('nodes', []):
            node_id = node.get('id')
            node['cluster_dir'] = cluster_map_dir.get(node_id, -1)
            node['cluster_semantic'] = cluster_map_semantic.get(node_id, -1)
            node['cluster'] = node['cluster_dir']

        # Count clusters for stats
        dir_cluster_ids = set(c for c in cluster_map_dir.values() if c >= 0)
        semantic_cluster_ids = set(c for c in cluster_map_semantic.values() if c >= 0)
        explorer_data['stats']['nebula_clusters'] = len(dir_cluster_ids)
        explorer_data['stats']['nebula_clusters_dir'] = len(dir_cluster_ids)
        explorer_data['stats']['nebula_clusters_semantic'] = len(semantic_cluster_ids)
        print(
            f"Explorer: {len(dir_cluster_ids)} directory clusters, "
            f"{len(semantic_cluster_ids)} semantic clusters detected"
        )

    # Load saved layout positions if available
    layout_path = Path('.proof/layout.json')
    saved_layout = None
    if layout_path.exists():
        try:
            saved_layout = json.loads(layout_path.read_text())
            print(f"Layout: loaded {len(saved_layout.get('story', {}))} story + {len(saved_layout.get('explorer', {}))} explorer positions")
        except Exception:
            pass

    # Build diff cache from Edit entries
    diff_cache = build_diff_cache(entries)
    if diff_cache:
        diff_cache_path = Path('.proof/diff_cache.json')
        diff_cache_path.write_text(json.dumps(diff_cache, indent=2))
        total_diffs = sum(len(v) for v in diff_cache.values())
        print(f"Diff cache: {len(diff_cache)} files, {total_diffs} diffs")

    html = generate_html(
        timeline, graph, stats, insights, summary, beginner_view,
        phases, explorer_data, saved_layout, diff_cache,
        inline_assets=inline_assets
    )
    out_path.write_text(html)
    print(f"Generated {out_path}")


if __name__ == '__main__':
    main()
