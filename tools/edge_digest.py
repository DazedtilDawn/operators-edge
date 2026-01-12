#!/usr/bin/env python3
"""
Edge Digest v0.9 - Automated reflection that turns visualization into a teacher.

Generates an actionable daily digest that summarizes:
- What happened (activity & structure)
- How quality changed (CTI, health trends)
- What to focus on next (3 concrete recommendations)

Output:
- reports/edge_digest.md - Narrative markdown summary
- active_context.yaml → next_focus - Top 3 recommendations

Usage:
    python3 tools/edge_digest.py
"""
import json
import csv
import re
from pathlib import Path
from datetime import datetime, timedelta
from collections import Counter, defaultdict
from typing import Dict, List, Any, Tuple

PROJECT_ROOT = Path(__file__).parent.parent
PROOF_DIR = PROJECT_ROOT / '.proof'
REPORTS_DIR = PROJECT_ROOT / 'reports'

# Performance limits
MAX_EVENTS = 500
MAX_AGE_HOURS = 24

# Recommendation thresholds
CTI_DROP_THRESHOLD = 5.0
DEBUG_PHASE_THRESHOLD = 20.0
EDIT_CONCENTRATION_THRESHOLD = 25.0
MIN_TOUCHES = 3


# =============================================================================
# Data Loading
# =============================================================================

def load_session_log(limit: int = MAX_EVENTS) -> List[Dict]:
    """Load recent events from session_log.jsonl."""
    log_path = PROOF_DIR / 'session_log.jsonl'
    if not log_path.exists():
        return []

    entries = []
    cutoff_time = datetime.now() - timedelta(hours=MAX_AGE_HOURS)

    with open(log_path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
                ts = entry.get('timestamp', '')
                if ts:
                    try:
                        entry_time = datetime.fromisoformat(ts.replace('Z', '+00:00')).replace(tzinfo=None)
                        if entry_time < cutoff_time:
                            continue
                    except (ValueError, TypeError):
                        pass
                entries.append(entry)
            except json.JSONDecodeError:
                continue

    return entries[-limit:] if len(entries) > limit else entries


def load_dependencies() -> Dict:
    """Load dependency graph from dependencies.json."""
    dep_path = PROOF_DIR / 'dependencies.json'
    if not dep_path.exists():
        return {'nodes': [], 'edges': [], 'stats': {}}

    try:
        return json.loads(dep_path.read_text())
    except (json.JSONDecodeError, IOError):
        return {'nodes': [], 'edges': [], 'stats': {}}


def load_phase_summary() -> List[Dict]:
    """Load phase summary data."""
    phase_path = PROOF_DIR / 'phase_summary.json'
    if not phase_path.exists():
        return []

    try:
        data = json.loads(phase_path.read_text())
        return data.get('phases', []) if isinstance(data, dict) else data
    except (json.JSONDecodeError, IOError):
        return []


def load_cti_history(limit: int = 10) -> List[Dict]:
    """Load CTI history for trend analysis."""
    history_path = PROOF_DIR / 'cti_history.csv'
    if not history_path.exists():
        return []

    history = []
    try:
        with open(history_path) as f:
            for line in f:
                if line.startswith('timestamp'):
                    continue
                parts = line.strip().split(',')
                if len(parts) >= 4:
                    history.append({
                        'timestamp': parts[0],
                        'events': int(parts[1]),
                        'cti': float(parts[2]),
                        'success_rate': float(parts[3]),
                    })
    except (IOError, ValueError):
        pass

    return history[-limit:] if len(history) > limit else history


# =============================================================================
# Analysis Functions
# =============================================================================

def compute_activity_summary(entries: List[Dict]) -> Dict:
    """Compute activity summary from session log entries."""
    if not entries:
        return {
            'total_events': 0,
            'by_action': {},
            'top_files': [],
            'clusters': [],
            'success_rate': 100.0,
        }

    action_counts = Counter()
    file_counts = Counter()
    file_actions = defaultdict(lambda: defaultdict(int))  # file -> action -> count
    cluster_counts = Counter()
    successes = 0

    for entry in entries:
        tool = entry.get('tool', 'unknown')
        success = entry.get('success', True)
        if success:
            successes += 1

        # Classify action
        if tool in ('Read', 'Glob', 'Grep', 'LSP', 'WebFetch', 'WebSearch'):
            action = 'read'
        elif tool in ('Edit', 'Write', 'NotebookEdit'):
            action = 'edit'
        elif tool == 'Bash':
            action = 'run'
        else:
            action = 'other'

        action_counts[action] += 1

        # Extract file info - handle both dict and string formats
        preview = entry.get('input_preview', {})
        file_path = None

        # If preview is a string representation of a dict, extract file path
        if isinstance(preview, str):
            import re
            # Match patterns like 'file': '/path/to/file.py' or "file_path": "/path/to/file.py"
            match = re.search(r"['\"](?:file|file_path|path)['\"]\s*:\s*['\"]([^'\"]+)['\"]", preview)
            if match:
                file_path = match.group(1)
        elif isinstance(preview, dict):
            for key in ('file', 'file_path', 'path'):
                if key in preview:
                    file_path = preview[key]
                    break

        if file_path:
            file_name = Path(file_path).name
            file_counts[file_name] += 1
            file_actions[file_name][action] += 1
            parent = Path(file_path).parent.name
            if parent and parent != '.':
                cluster_counts[parent] += 1

    # Build top files with action breakdown
    top_files = []
    for name, count in file_counts.most_common(10):
        if count >= MIN_TOUCHES:
            actions = dict(file_actions[name])
            top_files.append({'name': name, 'count': count, 'actions': actions})
        if len(top_files) >= 5:
            break

    clusters = [
        {'name': name, 'count': count}
        for name, count in cluster_counts.most_common(5)
    ]

    return {
        'total_events': len(entries),
        'by_action': dict(action_counts),
        'top_files': top_files,
        'clusters': clusters,
        'success_rate': (successes / len(entries) * 100) if entries else 100.0,
    }


def compute_trend_analysis(cti_history: List[Dict], phases: List[Dict]) -> Dict:
    """Compute trend analysis from CTI history and phases."""
    result = {
        'cti_current': 0.0,
        'cti_previous': 0.0,
        'cti_delta': 0.0,
        'cti_trend': 'stable',
        'phase_breakdown': {},
        'phase_shifts': [],
    }

    if len(cti_history) >= 1:
        result['cti_current'] = cti_history[-1].get('cti', 0)
    if len(cti_history) >= 2:
        result['cti_previous'] = cti_history[-2].get('cti', 0)
        result['cti_delta'] = result['cti_current'] - result['cti_previous']

        if result['cti_delta'] > 1:
            result['cti_trend'] = 'improving'
        elif result['cti_delta'] < -1:
            result['cti_trend'] = 'declining'

    if phases:
        phase_counts = Counter(p.get('intent', 'mixed') for p in phases)
        total_phases = sum(phase_counts.values())
        result['phase_breakdown'] = {
            intent: round(count / total_phases * 100, 1)
            for intent, count in phase_counts.items()
        }

    return result


def compute_structural_insights(dependencies: Dict, activity: Dict) -> Dict:
    """Compute structural insights from dependency graph."""
    result = {
        'high_degree_files': [],
        'cross_cluster_links': [],
    }

    nodes = dependencies.get('nodes', [])
    edges = dependencies.get('edges', [])

    if not nodes or not edges:
        return result

    # Compute degree centrality
    degree = defaultdict(int)
    for edge in edges:
        source = edge.get('source', '')
        target = edge.get('target', '')
        degree[source] += 1
        degree[target] += 1

    sorted_by_degree = sorted(degree.items(), key=lambda x: -x[1])
    result['high_degree_files'] = [
        {'id': node_id, 'degree': deg}
        for node_id, deg in sorted_by_degree[:5]
    ]

    # Cross-cluster links
    node_dirs = {n.get('id'): n.get('dir', 'root') for n in nodes}
    cross_links = []
    for edge in edges:
        source_dir = node_dirs.get(edge.get('source'), 'root')
        target_dir = node_dirs.get(edge.get('target'), 'root')
        if source_dir != target_dir and source_dir != 'root' and target_dir != 'root':
            cross_links.append({
                'from': source_dir,
                'to': target_dir,
                'weight': edge.get('weight', 1)
            })

    cluster_pairs = Counter((l['from'], l['to']) for l in cross_links)
    result['cross_cluster_links'] = [
        {'clusters': list(pair), 'count': count}
        for pair, count in cluster_pairs.most_common(5)
    ]

    return result


# =============================================================================
# Recommendation Engine
# =============================================================================

def generate_recommendations(
    activity: Dict,
    trends: Dict,
    structure: Dict
) -> List[Dict]:
    """Generate top 3 actionable recommendations."""
    recommendations = []

    # 1. CTI drop
    if trends.get('cti_delta', 0) < -CTI_DROP_THRESHOLD:
        recommendations.append({
            'priority': 1,
            'icon': '📉',
            'text': 'Increase traceability: ensure all edits reference files',
            'reason': f"CTI dropped {abs(trends['cti_delta']):.1f}%",
        })

    # 2. High debugging activity
    debug_pct = trends.get('phase_breakdown', {}).get('debugging', 0)
    if debug_pct > DEBUG_PHASE_THRESHOLD:
        recommendations.append({
            'priority': 2,
            'icon': '🐛',
            'text': 'Stabilize code - high debugging activity detected',
            'reason': f"{debug_pct:.0f}% of phases were debugging",
        })

    # 3. Edit concentration
    top_files = activity.get('top_files', [])
    total_events = activity.get('total_events', 1)
    if top_files:
        top_file = top_files[0]
        concentration = (top_file['count'] / total_events * 100) if total_events > 0 else 0
        if concentration > EDIT_CONCENTRATION_THRESHOLD:
            recommendations.append({
                'priority': 3,
                'icon': '🔧',
                'text': f"Refactor {top_file['name']} - high edit concentration",
                'reason': f"{top_file['count']} edits ({concentration:.0f}% of activity)",
            })

    # 4. Cross-cluster dependencies
    cross_links = structure.get('cross_cluster_links', [])
    if cross_links:
        top_link = cross_links[0]
        recommendations.append({
            'priority': 4,
            'icon': '🔗',
            'text': f"Review cross-cluster dependencies between {' and '.join(top_link['clusters'])}",
            'reason': f"{top_link['count']} connections across boundaries",
        })

    # 5. Active clusters focus
    clusters = activity.get('clusters', [])
    if clusters:
        active_clusters = [c['name'] for c in clusters[:2]]
        if active_clusters:
            recommendations.append({
                'priority': 5,
                'icon': '📁',
                'text': f"Focus areas: {', '.join(active_clusters)}",
                'reason': 'Most active clusters this session',
            })

    # Sort by priority and return top 3
    recommendations.sort(key=lambda r: r['priority'])
    return recommendations[:3]


# =============================================================================
# Output Functions
# =============================================================================

def generate_sparkline(values: List[float], width: int = 10) -> str:
    """Generate ASCII sparkline from values using block characters."""
    if not values:
        return ""

    # Sparkline characters from lowest to highest
    chars = '▁▂▃▄▅▆▇█'

    # Normalize to 0-7 range
    min_val = min(values)
    max_val = max(values)
    range_val = max_val - min_val if max_val > min_val else 1

    # Take last N values if more than width
    recent = values[-width:] if len(values) > width else values

    sparkline = ''
    for v in recent:
        normalized = (v - min_val) / range_val
        idx = min(int(normalized * 7), 7)
        sparkline += chars[idx]

    return sparkline


def generate_markdown_digest(
    activity: Dict,
    trends: Dict,
    structure: Dict,
    recommendations: List[Dict],
    cti_history: List[Dict],
    timestamp: str
) -> str:
    """Generate markdown digest report."""
    lines = [
        f"# Edge Digest — {timestamp}",
        "",
        "## Summary",
    ]

    total = activity.get('total_events', 0)
    cti = trends.get('cti_current', 0)
    success = activity.get('success_rate', 100)
    lines.append(f"**{total} events** processed ({cti:.1f}% CTI, {success:.0f}% success)")

    phases = trends.get('phase_breakdown', {})
    if phases:
        phase_str = ', '.join(f"{k}: {v:.0f}%" for k, v in phases.items())
        lines.append(f"Phase breakdown: {phase_str}")

    clusters = activity.get('clusters', [])
    if clusters:
        cluster_names = [c['name'] for c in clusters[:3]]
        lines.append(f"Active clusters: **{', '.join(cluster_names)}**")

    top_files = activity.get('top_files', [])
    if top_files:
        top = top_files[0]
        lines.append(f"Most-edited file: **{top['name']}** ({top['count']} edits)")

    lines.append("")
    lines.append("## Trends")

    # CTI with sparkline
    cti_delta = trends.get('cti_delta', 0)
    cti_trend = trends.get('cti_trend', 'stable')
    trend_icon = '📈' if cti_delta > 0 else '📉' if cti_delta < 0 else '➡️'

    # Generate sparkline from CTI history
    if cti_history:
        cti_values = [h.get('cti', 0) for h in cti_history]
        sparkline = generate_sparkline(cti_values)
        lines.append(f"CTI: `{sparkline}` {cti:.1f}% ({trend_icon} {cti_delta:+.1f}% {cti_trend})")
    else:
        lines.append(f"CTI: {cti:.1f}% ({trend_icon} {cti_delta:+.1f}% {cti_trend})")

    # Activity snapshot - top edited files with action breakdown and cross-refs
    if top_files:
        lines.append("")
        lines.append("## Activity Snapshot")
        lines.append("| File | Total | Read | Edit | Run | Explorer |")
        lines.append("|------|-------|------|------|-----|----------|")
        for f in top_files[:5]:
            actions = f.get('actions', {})
            r = actions.get('read', 0)
            e = actions.get('edit', 0)
            run = actions.get('run', 0)
            # Cross-reference link to Explorer mode (node ID format: file:filename)
            explorer_link = f"[View](proof_viz.html#file:{f['name']})"
            lines.append(f"| `{f['name']}` | {f['count']} | {r} | {e} | {run} | {explorer_link} |")

    lines.append("")
    lines.append("## Top Recommendations")

    if recommendations:
        for i, rec in enumerate(recommendations, 1):
            lines.append(f"{i}. {rec['icon']} **{rec['text']}**")
            lines.append(f"   _{rec['reason']}_")
    else:
        lines.append("No immediate concerns - system operating normally.")

    lines.extend([
        "",
        "---",
        "_Generated automatically by Edge Digest v0.9_",
    ])

    return '\n'.join(lines)


def update_active_context(recommendations: List[Dict]) -> bool:
    """Update active_context.yaml with new recommendations."""
    context_path = PROJECT_ROOT / 'active_context.yaml'
    if not context_path.exists():
        print("Warning: active_context.yaml not found")
        return False

    try:
        content = context_path.read_text()

        # Build new next_focus section
        if recommendations:
            focus_items = '\n'.join(f'  - "{rec["text"]}"' for rec in recommendations)
        else:
            focus_items = '  - "No immediate concerns - system operating normally"'

        new_focus = f"next_focus:\n{focus_items}"

        # Replace existing next_focus section
        pattern = r'next_focus:\n(?:  - [^\n]+\n?)+'
        if re.search(pattern, content):
            content = re.sub(pattern, new_focus + '\n', content)

        context_path.write_text(content)
        return True
    except Exception as e:
        print(f"Warning: Failed to update active_context.yaml: {e}")
        return False


def save_digest_report(content: str) -> Path:
    """Save digest report to reports directory."""
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime('%Y-%m-%d')
    output_path = REPORTS_DIR / f'edge_digest_{timestamp}.md'

    output_path.write_text(content)
    return output_path


# =============================================================================
# Main
# =============================================================================

def main():
    """Generate Edge Digest."""
    print("Edge Digest v0.9")
    print("=" * 50)

    # Load all data
    print("Loading data...")
    entries = load_session_log()
    dependencies = load_dependencies()
    phases = load_phase_summary()
    cti_history = load_cti_history()

    print(f"  Session log: {len(entries)} events")
    print(f"  Dependencies: {len(dependencies.get('nodes', []))} nodes")
    print(f"  Phases: {len(phases)} phases")
    print(f"  CTI history: {len(cti_history)} records")

    # Compute analysis
    print("\nAnalyzing...")
    activity = compute_activity_summary(entries)
    trends = compute_trend_analysis(cti_history, phases)
    structure = compute_structural_insights(dependencies, activity)

    print(f"  Events: {activity['total_events']}")
    print(f"  Success rate: {activity['success_rate']:.1f}%")
    print(f"  CTI: {trends['cti_current']:.1f}% ({trends['cti_trend']})")

    # Generate recommendations
    print("\nGenerating recommendations...")
    recommendations = generate_recommendations(activity, trends, structure)

    for rec in recommendations:
        print(f"  {rec['icon']} {rec['text']}")

    # Generate outputs
    print("\nGenerating outputs...")
    timestamp = datetime.now().strftime('%Y-%m-%d')

    # Markdown report
    digest_content = generate_markdown_digest(activity, trends, structure, recommendations, cti_history, timestamp)
    report_path = save_digest_report(digest_content)
    print(f"  Report: {report_path}")

    # Update active_context.yaml
    if update_active_context(recommendations):
        print("  Updated: active_context.yaml → next_focus")

    print("\n" + "=" * 50)
    print("Edge Digest complete!")

    return 0


if __name__ == '__main__':
    exit(main())
