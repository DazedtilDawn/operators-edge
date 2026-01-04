#!/usr/bin/env python3
"""
Proof Visualizer v0.1
Transforms .proof/session_log.jsonl into an interactive HTML dashboard.

Usage:
    python proof_visualizer.py                    # Uses default .proof/session_log.jsonl
    python proof_visualizer.py path/to/log.jsonl  # Custom log file
    python proof_visualizer.py --out report.html  # Custom output file
"""
import json
import sys
import re
from pathlib import Path
from datetime import datetime
from collections import defaultdict
from typing import List, Dict, Any, Optional


def load_proof_log(path: Path) -> List[Dict[str, Any]]:
    """Load JSONL proof log."""
    entries = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    entries.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    return entries


def extract_file_path(input_preview: Any) -> Optional[str]:
    """Extract file path from various input_preview formats."""
    if isinstance(input_preview, dict):
        for key in ('file', 'file_path', 'path'):
            if key in input_preview:
                return input_preview[key]
    elif isinstance(input_preview, str):
        # Check if it looks like a file path
        if '/' in input_preview or '\\' in input_preview:
            # Extract path from string like "{'file': '/path/to/file'}"
            match = re.search(r"['\"]?(?:file|file_path|path)['\"]?\s*:\s*['\"]([^'\"]+)['\"]", input_preview)
            if match:
                return match.group(1)
            # Or just return if it looks like a path
            if input_preview.startswith('/') or input_preview.startswith('C:'):
                return input_preview
    return None


def build_timeline(entries: List[Dict]) -> List[Dict]:
    """Build timeline data for visualization."""
    timeline = []
    for entry in entries:
        ts = entry.get('timestamp', '')
        tool = entry.get('tool', 'unknown')
        success = entry.get('success', True)
        file_path = extract_file_path(entry.get('input_preview'))

        timeline.append({
            'timestamp': ts,
            'tool': tool,
            'success': success,
            'file': Path(file_path).name if file_path else None,
            'full_path': file_path,
        })
    return timeline


def build_dependency_graph(entries: List[Dict]) -> Dict:
    """Build tool → file dependency graph."""
    nodes = set()
    edges = []
    file_tools = defaultdict(set)  # file → tools that touched it

    for entry in entries:
        tool = entry.get('tool', 'unknown')
        file_path = extract_file_path(entry.get('input_preview'))

        nodes.add(f"tool:{tool}")

        if file_path:
            short_name = Path(file_path).name
            nodes.add(f"file:{short_name}")
            edge_key = (f"tool:{tool}", f"file:{short_name}")
            if edge_key not in [(e['source'], e['target']) for e in edges]:
                edges.append({
                    'source': f"tool:{tool}",
                    'target': f"file:{short_name}",
                })
            file_tools[short_name].add(tool)

    return {
        'nodes': [{'id': n, 'type': n.split(':')[0]} for n in nodes],
        'edges': edges,
    }


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


def generate_html(timeline: List[Dict], graph: Dict, stats: Dict) -> str:
    """Generate HTML with embedded D3.js visualization."""
    return f'''<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>Proof Visualizer - Operator's Edge</title>
    <script src="https://d3js.org/d3.v7.min.js"></script>
    <style>
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, monospace; background: #0d1117; color: #c9d1d9; padding: 20px; }}
        h1 {{ color: #58a6ff; margin-bottom: 10px; }}
        h2 {{ color: #8b949e; font-size: 14px; margin: 20px 0 10px; text-transform: uppercase; letter-spacing: 1px; }}
        .stats {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 15px; margin-bottom: 30px; }}
        .stat {{ background: #161b22; padding: 15px; border-radius: 6px; border: 1px solid #30363d; }}
        .stat-value {{ font-size: 24px; font-weight: bold; color: #58a6ff; }}
        .stat-label {{ font-size: 12px; color: #8b949e; margin-top: 5px; }}
        .container {{ display: grid; grid-template-columns: 1fr 1fr; gap: 20px; }}
        .panel {{ background: #161b22; border-radius: 6px; border: 1px solid #30363d; padding: 15px; min-height: 400px; }}
        .timeline-item {{ padding: 8px 12px; border-left: 3px solid #30363d; margin: 5px 0; font-size: 12px; }}
        .timeline-item.success {{ border-color: #238636; }}
        .timeline-item.failure {{ border-color: #da3633; background: #1f1315; }}
        .tool {{ color: #d2a8ff; font-weight: bold; }}
        .file {{ color: #7ee787; }}
        .time {{ color: #6e7681; font-size: 10px; }}
        #graph {{ width: 100%; height: 400px; }}
        .node-tool {{ fill: #d2a8ff; }}
        .node-file {{ fill: #7ee787; }}
        .link {{ stroke: #30363d; stroke-opacity: 0.6; }}
        text {{ fill: #c9d1d9; font-size: 10px; }}
    </style>
</head>
<body>
    <h1>Proof Visualizer</h1>
    <p style="color: #8b949e; margin-bottom: 20px;">Operator's Edge - Session Analysis</p>

    <h2>Summary</h2>
    <div class="stats">
        <div class="stat">
            <div class="stat-value">{stats['total_events']}</div>
            <div class="stat-label">Total Events</div>
        </div>
        <div class="stat">
            <div class="stat-value">{stats['success_rate']}</div>
            <div class="stat-label">Success Rate</div>
        </div>
        <div class="stat">
            <div class="stat-value">{stats['cti']}</div>
            <div class="stat-label">Traceability (CTI)</div>
        </div>
        <div class="stat">
            <div class="stat-value">{stats['failures']}</div>
            <div class="stat-label">Failures</div>
        </div>
    </div>

    <h2>Tool Distribution</h2>
    <div class="stats">
        {"".join(f'<div class="stat"><div class="stat-value">{count}</div><div class="stat-label">{tool}</div></div>' for tool, count in sorted(stats['tool_counts'].items(), key=lambda x: -x[1]))}
    </div>

    <div class="container">
        <div class="panel">
            <h2>Timeline (Recent 100)</h2>
            <div id="timeline">
                {"".join(f'''<div class="timeline-item {'success' if e['success'] else 'failure'}">
                    <span class="tool">{e['tool']}</span>
                    {f'<span class="file"> → {e["file"]}</span>' if e['file'] else ''}
                    <div class="time">{e['timestamp']}</div>
                </div>''' for e in timeline[-100:][::-1])}
            </div>
        </div>
        <div class="panel">
            <h2>Dependency Graph</h2>
            <svg id="graph"></svg>
        </div>
    </div>

    <script>
        const graphData = {json.dumps(graph)};

        const svg = d3.select("#graph");
        const width = svg.node().parentElement.clientWidth;
        const height = 400;
        svg.attr("viewBox", [0, 0, width, height]);

        const simulation = d3.forceSimulation(graphData.nodes)
            .force("link", d3.forceLink(graphData.edges).id(d => d.id).distance(80))
            .force("charge", d3.forceManyBody().strength(-200))
            .force("center", d3.forceCenter(width / 2, height / 2));

        const link = svg.append("g")
            .selectAll("line")
            .data(graphData.edges)
            .join("line")
            .attr("class", "link")
            .attr("stroke-width", 1.5);

        const node = svg.append("g")
            .selectAll("g")
            .data(graphData.nodes)
            .join("g")
            .call(d3.drag()
                .on("start", (e, d) => {{ if (!e.active) simulation.alphaTarget(0.3).restart(); d.fx = d.x; d.fy = d.y; }})
                .on("drag", (e, d) => {{ d.fx = e.x; d.fy = e.y; }})
                .on("end", (e, d) => {{ if (!e.active) simulation.alphaTarget(0); d.fx = null; d.fy = null; }}));

        node.append("circle")
            .attr("r", 8)
            .attr("class", d => d.type === "tool" ? "node-tool" : "node-file");

        node.append("text")
            .attr("dx", 12)
            .attr("dy", 4)
            .text(d => d.id.split(":")[1]);

        simulation.on("tick", () => {{
            link
                .attr("x1", d => d.source.x)
                .attr("y1", d => d.source.y)
                .attr("x2", d => d.target.x)
                .attr("y2", d => d.target.y);
            node.attr("transform", d => `translate(${{d.x}},${{d.y}})`);
        }});
    </script>
</body>
</html>'''


def load_cti_history(history_path: Path) -> List[Dict]:
    """Load CTI history from CSV."""
    if not history_path.exists():
        return []
    history = []
    with open(history_path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('timestamp'):  # skip header
                parts = line.split(',')
                if len(parts) >= 4:
                    history.append({
                        'timestamp': parts[0],
                        'events': int(parts[1]),
                        'cti': float(parts[2]),
                        'success_rate': float(parts[3]),
                    })
    return history


def append_cti_history(history_path: Path, stats: Dict):
    """Append current stats to CTI history."""
    is_new = not history_path.exists()
    with open(history_path, 'a') as f:
        if is_new:
            f.write('timestamp,events,cti,success_rate\n')
        cti_val = float(stats['cti'].rstrip('%'))
        sr_val = float(stats['success_rate'].rstrip('%')) if stats['success_rate'] != 'N/A' else 0
        f.write(f"{datetime.now().isoformat()},{stats['total_events']},{cti_val},{sr_val}\n")


def check_drift(history: List[Dict], current_cti: float, threshold: float = 10.0) -> Optional[str]:
    """Check if CTI has drifted beyond threshold from last run."""
    if not history:
        return None
    last_cti = history[-1]['cti']
    drift = last_cti - current_cti
    if drift > threshold:
        return f"WARNING: CTI drift {drift:.1f}% (was {last_cti:.1f}%, now {current_cti:.1f}%)"
    elif drift > 0:
        return f"CTI down {drift:.1f}% from last run"
    elif drift < 0:
        return f"CTI up {-drift:.1f}% from last run"
    return None


def main():
    # Parse args
    args = sys.argv[1:]
    log_path = Path('.proof/session_log.jsonl')
    out_path = Path('proof_viz.html')
    history_path = Path('.proof/cti_history.csv')
    track_history = False

    i = 0
    while i < len(args):
        if args[i] == '--out' and i + 1 < len(args):
            out_path = Path(args[i + 1])
            i += 2
        elif args[i] == '--history':
            track_history = True
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

    cti_val = float(stats['cti'].rstrip('%'))
    print(f"Stats: {stats['total_events']} events, {stats['success_rate']} success, CTI={stats['cti']}")

    # Drift detection
    if track_history:
        history = load_cti_history(history_path)
        drift_msg = check_drift(history, cti_val)
        if drift_msg:
            print(f"Drift: {drift_msg}")
        append_cti_history(history_path, stats)
        print(f"History: {len(history) + 1} runs tracked in {history_path}")

    html = generate_html(timeline, graph, stats)
    out_path.write_text(html)
    print(f"Generated {out_path}")


if __name__ == '__main__':
    main()
