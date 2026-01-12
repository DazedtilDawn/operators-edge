#!/usr/bin/env python3
"""
Proof Visualizer - Analysis Functions
Stats, insights, phase detection, anomaly detection, and summaries.
"""
from pathlib import Path
from datetime import datetime
from collections import defaultdict
from typing import List, Dict, Optional

from proof_viz_loaders import extract_file_path
from proof_viz_config import ANOMALY_SIGMA, DEFAULT_MIN_STREAK, DEFAULT_MIN_PHASE_SIZE


def compute_stats(entries: List[Dict]) -> Dict:
    """Compute summary statistics."""
    total = len(entries)
    successes = sum(1 for e in entries if e.get('success', True))
    failures = total - successes

    tool_counts = defaultdict(int)
    for e in entries:
        tool_counts[e.get('tool', 'unknown')] += 1

    # CTI: entries with traceable file paths
    with_cause = sum(1 for e in entries if extract_file_path(e.get('input_preview')))
    cti = with_cause / total if total > 0 else 1.0

    # Time range
    timestamps = [e.get('timestamp', '') for e in entries if e.get('timestamp')]
    if timestamps:
        first = min(timestamps)
        last = max(timestamps)
    else:
        first = last = 'unknown'

    return {
        'total_events': total,
        'successes': successes,
        'failures': failures,
        'success_rate': f"{100 * successes / total:.1f}%" if total > 0 else "N/A",
        'cti': f"{100 * cti:.1f}%",
        'tool_counts': dict(tool_counts),
        'time_range': {'start': first, 'end': last},
    }


def compute_insights(graph: Dict, stats: Dict) -> List[Dict]:
    """Generate actionable insights from graph and stats."""
    insights = []
    nodes = graph.get('nodes', [])
    clusters = graph.get('clusters', [])

    # Find hottest files (most touched, excluding tools)
    file_nodes = [n for n in nodes if n['type'] == 'file']
    if file_nodes:
        hottest = sorted(file_nodes, key=lambda n: -n['count'])[:3]
        for f in hottest:
            name = f['id'].split(':')[1]
            insights.append({
                'type': 'hot',
                'icon': '🔥',
                'title': f'Hot: {name}',
                'detail': f"{f['count']} touches",
                'node_id': f['id'],
            })

    # Find stale files (touched but not recently - recency > 24h)
    stale = [n for n in file_nodes if n.get('recency', 0) > 24]
    stale = sorted(stale, key=lambda n: -n.get('recency', 0))[:2]
    for f in stale:
        name = f['id'].split(':')[1]
        hours = f.get('recency', 0)
        insights.append({
            'type': 'stale',
            'icon': '⏰',
            'title': f'Stale: {name}',
            'detail': f"{int(hours)}h ago",
            'node_id': f['id'],
        })

    # Find focus directories
    if clusters and len(clusters) > 0:
        top_dir = clusters[0]
        insights.append({
            'type': 'focus',
            'icon': '📁',
            'title': f"Focus: {top_dir['name']}/",
            'detail': f"{top_dir['count']} files",
            'cluster': top_dir['name'],
        })

    # Tool dominance
    tool_counts = stats.get('tool_counts', {})
    if tool_counts:
        dominant = max(tool_counts.items(), key=lambda x: x[1])
        pct = 100 * dominant[1] / stats['total_events'] if stats['total_events'] > 0 else 0
        if pct > 40:
            insights.append({
                'type': 'pattern',
                'icon': '🔧',
                'title': f'{dominant[0]} heavy',
                'detail': f"{pct:.0f}% of actions",
                'node_id': f'tool:{dominant[0]}',
            })

    # Failure hotspots
    if stats['failures'] > 0:
        fail_rate = 100 - float(stats['success_rate'].rstrip('%'))
        if fail_rate > 5:
            insights.append({
                'type': 'warning',
                'icon': '⚠️',
                'title': 'Failure rate high',
                'detail': f"{stats['failures']} failures ({fail_rate:.1f}%)",
            })

    return insights[:6]  # Max 6 insights


def compute_phase_cti(entries: List[Dict], start: int, end: int) -> float:
    """Compute CTI for a slice of entries."""
    phase_entries = entries[start:end + 1]
    if not phase_entries:
        return 0.0
    with_file = sum(1 for e in phase_entries if extract_file_path(e.get('input_preview')))
    return (with_file / len(phase_entries)) * 100


def compute_phase_duration(start_time: str, end_time: str) -> Optional[float]:
    """Compute duration in seconds between two timestamps."""
    if not start_time or not end_time:
        return None
    try:
        start_dt = datetime.fromisoformat(start_time.replace('Z', '+00:00'))
        end_dt = datetime.fromisoformat(end_time.replace('Z', '+00:00'))
        return (end_dt - start_dt).total_seconds()
    except:
        return None


def format_duration(seconds: Optional[float]) -> str:
    """Format seconds into human-readable duration."""
    if seconds is None:
        return "?"
    if seconds < 60:
        return f"{int(seconds)}s"
    elif seconds < 3600:
        return f"{int(seconds // 60)}m {int(seconds % 60)}s"
    else:
        hours = int(seconds // 3600)
        mins = int((seconds % 3600) // 60)
        return f"{hours}h {mins}m"


def detect_phases(entries: List[Dict], min_streak: int = DEFAULT_MIN_STREAK, min_phase_size: int = DEFAULT_MIN_PHASE_SIZE) -> List[Dict]:
    """
    Detect intent phases from operation sequence.

    Phases:
    - exploring: 3+ consecutive Reads or Glob/Grep
    - building: 3+ consecutive Edits or Writes
    - debugging: any failures or error patterns
    - mixed: other activity

    Each phase includes: duration_seconds, duration_formatted, cti
    """
    if not entries:
        return []

    def get_intent(entry: Dict) -> str:
        tool = entry.get('tool', 'unknown')
        success = entry.get('success', True)

        if not success:
            return 'debugging'
        elif tool in ('Read', 'Glob', 'Grep', 'LSP'):
            return 'exploring'
        elif tool in ('Edit', 'Write', 'NotebookEdit'):
            return 'building'
        elif tool == 'Bash':
            return 'executing'
        else:
            return 'mixed'

    phases = []
    current_intent = None
    streak_start = 0
    streak_count = 0

    for i, entry in enumerate(entries):
        intent = get_intent(entry)

        if intent == current_intent:
            streak_count += 1
        else:
            # Close previous phase if it was significant
            if current_intent and streak_count >= min_streak:
                phases.append({
                    'start': streak_start,
                    'end': i - 1,
                    'intent': current_intent,
                    'count': streak_count,
                    'start_time': entries[streak_start].get('timestamp', ''),
                    'end_time': entries[i - 1].get('timestamp', ''),
                })
            elif current_intent and phases:
                # Extend previous phase if too short
                phases[-1]['end'] = i - 1
                phases[-1]['count'] += streak_count
            elif current_intent:
                # First phase, even if short
                phases.append({
                    'start': streak_start,
                    'end': i - 1,
                    'intent': current_intent if streak_count >= min_streak else 'mixed',
                    'count': streak_count,
                    'start_time': entries[streak_start].get('timestamp', ''),
                    'end_time': entries[i - 1].get('timestamp', ''),
                })

            current_intent = intent
            streak_start = i
            streak_count = 1

    # Close final phase
    if current_intent:
        phases.append({
            'start': streak_start,
            'end': len(entries) - 1,
            'intent': current_intent if streak_count >= min_streak else 'mixed',
            'count': streak_count,
            'start_time': entries[streak_start].get('timestamp', ''),
            'end_time': entries[-1].get('timestamp', ''),
        })

    # Merge adjacent phases of same intent
    merged = []
    for phase in phases:
        if merged and merged[-1]['intent'] == phase['intent']:
            merged[-1]['end'] = phase['end']
            merged[-1]['count'] += phase['count']
            merged[-1]['end_time'] = phase['end_time']
        else:
            merged.append(phase)

    # Collapse micro-phases (< min_phase_size) into neighbors
    if min_phase_size > 0 and len(merged) > 1:
        collapsed = []
        for phase in merged:
            if phase['count'] < min_phase_size and collapsed:
                # Absorb into previous phase
                collapsed[-1]['end'] = phase['end']
                collapsed[-1]['count'] += phase['count']
                collapsed[-1]['end_time'] = phase['end_time']
            elif phase['count'] < min_phase_size and not collapsed:
                # First phase is small, just add it (will merge with next)
                collapsed.append(phase)
            else:
                # Large enough phase
                if collapsed and collapsed[-1]['count'] < min_phase_size:
                    # Previous was small, absorb it into this one
                    phase['start'] = collapsed[-1]['start']
                    phase['count'] += collapsed[-1]['count']
                    phase['start_time'] = collapsed[-1]['start_time']
                    collapsed[-1] = phase
                else:
                    collapsed.append(phase)
        merged = collapsed

    # Enrich phases with duration and CTI
    for phase in merged:
        duration = compute_phase_duration(phase['start_time'], phase['end_time'])
        phase['duration_seconds'] = duration
        phase['duration_formatted'] = format_duration(duration)
        phase['cti'] = round(compute_phase_cti(entries, phase['start'], phase['end']), 1)

    return merged


def generate_phase_summary(phases: List[Dict], entries: List[Dict]) -> str:
    """Generate natural language summary of phases."""
    if not phases:
        return "No distinct phases detected."

    parts = []
    for i, phase in enumerate(phases):
        intent = phase['intent']
        count = phase['count']

        # Get files touched in this phase
        phase_entries = entries[phase['start']:phase['end'] + 1]
        files_touched = set()
        for e in phase_entries:
            inp = e.get('input_preview', {})
            if isinstance(inp, dict):
                for key in ('file', 'file_path', 'path'):
                    if key in inp:
                        files_touched.add(Path(inp[key]).name)
                        break

        if intent == 'exploring':
            verb = "explored"
        elif intent == 'building':
            verb = "built/edited"
        elif intent == 'debugging':
            verb = "debugged"
        elif intent == 'executing':
            verb = "executed commands on"
        else:
            verb = "worked on"

        if files_touched:
            top_files = list(files_touched)[:3]
            parts.append(f"Phase {i+1}: Claude {verb} {', '.join(top_files)} ({count} ops)")
        else:
            parts.append(f"Phase {i+1}: Claude {verb} ({count} ops)")

    return " → ".join(parts)


def compute_anomalies(graph: Dict) -> List[Dict]:
    """Identify anomalous nodes (> 3σ above mean)."""
    nodes = graph.get('nodes', [])
    if not nodes:
        return []

    counts = [n['count'] for n in nodes]
    mean = sum(counts) / len(counts)
    variance = sum((c - mean) ** 2 for c in counts) / len(counts)
    std_dev = variance ** 0.5

    threshold = mean + ANOMALY_SIGMA * std_dev
    anomalies = []

    for node in nodes:
        if node['count'] > threshold:
            sigma = (node['count'] - mean) / std_dev if std_dev > 0 else 0
            anomalies.append({
                'id': node['id'],
                'name': node['id'].split(':')[1],
                'type': node['type'],
                'count': node['count'],
                'sigma': round(sigma, 2),
                'dir': node.get('dir'),
            })

    return sorted(anomalies, key=lambda x: -x['sigma'])


def compute_beginner_view(stats: Dict, graph: Dict) -> Dict:
    """Generate beginner-friendly metrics with traffic light status and plain English."""
    # Determine overall health (traffic light)
    success_rate = float(stats['success_rate'].rstrip('%')) if stats['success_rate'] != 'N/A' else 100
    cti = float(stats['cti'].rstrip('%'))
    failures = stats['failures']

    # Health score: weighted average
    health_score = (success_rate * 0.6) + (cti * 0.4)

    if health_score >= 80 and failures <= 5:
        status = 'green'
        status_text = 'Healthy Session'
        status_emoji = '🟢'
    elif health_score >= 60 and failures <= 15:
        status = 'yellow'
        status_text = 'Needs Attention'
        status_emoji = '🟡'
    else:
        status = 'red'
        status_text = 'Review Required'
        status_emoji = '🔴'

    # Plain English breakdown
    tool_counts = stats.get('tool_counts', {})
    total = stats['total_events']

    # What Claude did
    reads = tool_counts.get('Read', 0)
    edits = tool_counts.get('Edit', 0)
    writes = tool_counts.get('Write', 0)
    bashes = tool_counts.get('Bash', 0)

    actions = []
    if reads > 0:
        actions.append(f"Read {reads} files")
    if edits > 0:
        actions.append(f"Edited {edits} times")
    if writes > 0:
        actions.append(f"Created {writes} files")
    if bashes > 0:
        actions.append(f"Ran {bashes} commands")

    what_happened = ", ".join(actions) if actions else "Various operations"

    # File focus
    file_nodes = [n for n in graph.get('nodes', []) if n['type'] == 'file']
    top_files = sorted(file_nodes, key=lambda n: -n['count'])[:3]
    file_focus = [n['id'].split(':')[1] for n in top_files]

    # Simple recommendations
    tips = []
    if failures > 10:
        tips.append(f"⚠️ {failures} operations failed - check for errors")
    if cti < 60:
        tips.append("📊 Many operations aren't linked to files - hard to trace")
    if edits > reads * 2:
        tips.append("📖 Lots of edits, few reads - make sure you understand before changing")
    if len(file_focus) == 1:
        tips.append(f"🎯 Very focused on {file_focus[0]}")
    if not tips:
        tips.append("✅ Session looks good - no issues detected")

    return {
        'status': status,
        'status_text': status_text,
        'status_emoji': status_emoji,
        'health_score': round(health_score),
        'what_happened': what_happened,
        'file_focus': file_focus,
        'tips': tips,
        'stats_simple': {
            'total': total,
            'worked': stats['successes'],
            'failed': failures,
        }
    }


def compute_summary(graph: Dict, stats: Dict, insights: List[Dict], drift_msg: Optional[str] = None) -> str:
    """Generate natural language summary of the session."""
    nodes = graph.get('nodes', [])
    clusters = graph.get('clusters', [])

    file_nodes = [n for n in nodes if n['type'] == 'file']
    tool_nodes = [n for n in nodes if n['type'] == 'tool']

    # Top files
    top_files = sorted(file_nodes, key=lambda n: -n['count'])[:3]
    top_file_names = [n['id'].split(':')[1] for n in top_files]

    # Focus area
    focus_dir = clusters[0]['name'] if clusters else 'various directories'

    # Dominant tool
    tool_counts = stats.get('tool_counts', {})
    if tool_counts:
        dominant_tool = max(tool_counts.items(), key=lambda x: x[1])[0]
    else:
        dominant_tool = 'various tools'

    # Build summary
    parts = []
    parts.append(f"This session involved {stats['total_events']} operations")
    parts.append(f"focusing primarily on the **{focus_dir}/** directory.")

    if top_file_names:
        if len(top_file_names) == 1:
            parts.append(f"The most active file was **{top_file_names[0]}**.")
        else:
            parts.append(f"Key files included **{', '.join(top_file_names[:2])}**.")

    parts.append(f"The dominant operation was **{dominant_tool}** ({tool_counts.get(dominant_tool, 0)} times).")

    cti_val = float(stats['cti'].rstrip('%'))
    if cti_val >= 80:
        parts.append("Traceability is excellent—most actions are well-documented.")
    elif cti_val >= 60:
        parts.append("Traceability is good with most operations linked to files.")
    else:
        parts.append("Consider improving traceability—many operations lack file context.")

    # Add drift info if available
    if drift_msg:
        if 'up' in drift_msg.lower():
            parts.append(f"📈 CTI trending up from last run.")
        elif 'down' in drift_msg.lower() or 'WARNING' in drift_msg:
            parts.append(f"📉 CTI trending down—review recent changes.")

    return ' '.join(parts)
