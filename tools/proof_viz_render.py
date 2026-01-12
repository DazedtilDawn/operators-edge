#!/usr/bin/env python3
"""
Proof Visualizer - HTML Rendering
Generates HTML with external CSS/JS and embedded JSON data.
"""
import json
from typing import List, Dict, Optional


def generate_html(
    timeline: List[Dict],
    graph: Dict,
    stats: Dict,
    insights: List[Dict],
    summary: str,
    beginner: Dict,
    phases: List[Dict] = None,
    explorer_data: Dict = None,
    saved_layout: Dict = None,
    diff_cache: Dict = None,
    inline_assets: bool = False
) -> str:
    """
    Generate HTML visualization.

    Args:
        timeline: List of timeline events
        graph: Graph data with nodes, edges, clusters
        stats: Computed statistics
        insights: List of insight dictionaries
        summary: Natural language summary
        beginner: Beginner-friendly view data
        phases: Detected phases (optional)
        explorer_data: Explorer mode data (optional)
        saved_layout: Saved node positions (optional)
        diff_cache: Diff cache for file changes (optional)
        inline_assets: If True, inline CSS/JS instead of external refs

    Returns:
        Complete HTML string
    """
    # Prepare data for JSON embedding
    proofviz_data = {
        'graph': graph,
        'explorer': explorer_data,
        'diffCache': diff_cache or {},
        'savedLayout': saved_layout or {},
        'insights': [{'title': i['title'], 'detail': i['detail']} for i in insights],
        'beginner': beginner,
        'phases': phases or [],
        'timeline': timeline,
        'stats': stats,
        'summary': summary,
    }

    # Pre-compute HTML fragments
    tips_html = "".join(f'<div class="tip-item">{tip}</div>' for tip in beginner['tips'])
    files_html = ", ".join(
        f'<span class="file-tag">{f}</span>' for f in beginner['file_focus'][:3]
    ) if beginner['file_focus'] else "Various files"
    total_events = len(timeline)

    # Build stats HTML
    stats_extra = "".join(
        f'<div class="stat"><div class="stat-value">{count}</div><div class="stat-label">{tool}</div></div>'
        for tool, count in sorted(stats['tool_counts'].items(), key=lambda x: -x[1])[:4]
    )

    # Build insights HTML
    insights_html = "".join(
        f'''<div class="insight" data-node="{i.get('node_id', '')}" data-cluster="{i.get('cluster', '')}" onclick="highlightInsight(this)">
            <span class="insight-icon">{i['icon']}</span>
            <div class="insight-text">
                <span class="insight-title">{i['title']}</span>
                <span class="insight-detail">{i['detail']}</span>
            </div>
        </div>'''
        for i in insights
    )

    # Build timeline HTML
    timeline_html = "".join(
        f'''<div class="timeline-item {'success' if e['success'] else 'failure'}" data-file="{e.get('full_path', '')}">
            <span class="tool">{e['tool']}</span>
            {f'<span class="file"> → {e["file"]}</span>' if e['file'] else ''}
            <div class="time">{e['timestamp']}</div>
        </div>'''
        for e in timeline[-100:][::-1]
    )

    # Time range display
    time_start = stats['time_range']['start'][:10] if stats['time_range']['start'] != 'unknown' else ''
    time_end = stats['time_range']['end'][:10] if stats['time_range']['end'] != 'unknown' else ''
    time_range = f"{time_start} → {time_end}" if time_start else ""

    # Asset loading strategy
    if inline_assets:
        # For standalone HTML files, inline everything
        css_tag = _get_inline_css()
        js_tag = _get_inline_js()
    else:
        # For server-based, use external references
        css_tag = '<link rel="stylesheet" href="/assets/styles.css">'
        js_tag = '<script src="/assets/proof_viz.js"></script>'

    return f'''<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>Proof Visualizer - Operator's Edge</title>
    <script src="https://d3js.org/d3.v7.min.js"></script>
    {css_tag}
</head>
<body>
    <div class="header">
        <div>
            <h1>Proof Visualizer</h1>
            <p style="color: #8b949e;">Operator's Edge - Session Analysis</p>
        </div>
        <div style="color: #6e7681; font-size: 12px;">
            {time_range}
        </div>
    </div>

    <!-- Quick View for Beginners -->
    <div class="quick-view status-{beginner['status']}" id="quick-view">
        <div class="qv-header">
            <div class="qv-status">
                <span class="qv-status-indicator">{beginner['status_emoji']}</span>
                <div>
                    <div class="qv-status-text">{beginner['status_text']}</div>
                    <div class="qv-health">Health Score: {beginner['health_score']}%</div>
                </div>
            </div>
            <button class="qv-toggle" onclick="toggleAdvanced()">Show Advanced Details</button>
        </div>
        <div class="qv-content">
            <div class="qv-section">
                <h4>What Claude Did</h4>
                <div class="qv-what">{beginner['what_happened']}</div>
                <div style="margin-top: 10px; color: #8b949e; font-size: 12px;">
                    Focused on: {files_html}
                </div>
            </div>
            <div class="qv-section">
                <h4>By The Numbers</h4>
                <div class="qv-numbers">
                    <div class="qv-num">
                        <div class="qv-num-value">{beginner['stats_simple']['total']}</div>
                        <div class="qv-num-label">Total</div>
                    </div>
                    <div class="qv-num">
                        <div class="qv-num-value success">{beginner['stats_simple']['worked']}</div>
                        <div class="qv-num-label">Worked</div>
                    </div>
                    <div class="qv-num">
                        <div class="qv-num-value fail">{beginner['stats_simple']['failed']}</div>
                        <div class="qv-num-label">Failed</div>
                    </div>
                </div>
            </div>
            <div class="qv-section">
                <h4>Tips</h4>
                {tips_html}
            </div>
        </div>
    </div>

    <div class="advanced-view" id="advanced-view">
    <div class="stats">
        <div class="stat">
            <div class="stat-value">{stats['total_events']}</div>
            <div class="stat-label">Events</div>
        </div>
        <div class="stat">
            <div class="stat-value">{stats['success_rate']}</div>
            <div class="stat-label">Success</div>
        </div>
        <div class="stat">
            <div class="stat-value">{stats['cti']}</div>
            <div class="stat-label">CTI</div>
        </div>
        <div class="stat">
            <div class="stat-value">{len(graph['nodes'])}</div>
            <div class="stat-label">Nodes</div>
        </div>
        <div class="stat">
            <div class="stat-value">{len(graph['edges'])}</div>
            <div class="stat-label">Edges</div>
        </div>
        {stats_extra}
    </div>

    <div class="insights" id="insights">
        {insights_html}
    </div>

    <div class="summary-block">
        <h3>Session Summary</h3>
        <p>{summary}</p>
    </div>

    <div class="search-bar">
        <input type="text" id="search-input" placeholder="Search files, tools, or directories..." oninput="handleSearch(event)">
        <button class="clear-btn" onclick="clearSearch()" title="Clear search and reset highlighting">Clear</button>
    </div>

    <div class="graph-container" id="graph-container">
        <div class="graph-header">
            <h2 style="margin: 0;">Dependency Graph</h2>
            <div class="graph-controls">
                <button onclick="resetZoom()" title="Reset zoom and pan to default">Reset View</button>
                <button onclick="resetLayout()" title="Re-run physics simulation to reorganize nodes">Reset Layout</button>
                <button onclick="toggleFullscreen()" title="Toggle fullscreen mode">Fullscreen</button>
                <div class="export-menu">
                    <button onclick="toggleExportMenu()" title="Export graph or report">Export</button>
                    <div class="export-dropdown" id="export-dropdown">
                        <button onclick="exportPNG()">PNG Image</button>
                        <button onclick="exportMarkdown()">Markdown Report</button>
                        <button onclick="exportLayout()">Save Layout</button>
                    </div>
                </div>
                <div class="heatmap-controls" title="Color nodes by different metrics">
                    <button id="hm-default" class="active" onclick="setHeatmap('default')" title="Default colors: purple=tools, green=files">Default</button>
                    <button id="hm-recency" onclick="setHeatmap('recency')" title="Red=stale (48h+), Yellow=recent, Green=just touched">Recency</button>
                    <button id="hm-frequency" onclick="setHeatmap('frequency')" title="Yellow=few touches, Red=many touches">Frequency</button>
                </div>
                <div class="mode-toggle">
                    <button id="mode-story" class="active" onclick="setMode('story')">Story</button>
                    <button id="mode-explorer" onclick="setMode('explorer')">Explorer</button>
                </div>
            </div>
        </div>
        <!-- Scene wrapper for absolute positioned scenes -->
        <div class="scene-wrapper">
            <div id="story-scene" class="scene active">
                <div id="graph-wrapper">
                    <svg id="graph"></svg>
                </div>
            </div>
            <div id="explorer-scene" class="scene">
                <div id="explorer-wrapper">
                    <svg id="explorer-graph"></svg>
                </div>
                <div class="explorer-legend">
                    <div class="layout-selector">
                        <label>Layout:</label>
                        <select id="layout-select" onchange="setLayout(this.value)">
                            <option value="force" selected>Force-Directed</option>
                            <option value="bundling">Edge Bundling</option>
                            <option value="treemap">Treemap</option>
                            <option value="packing">Circle Packing</option>
                            <option value="sunburst">Sunburst</option>
                            <option value="grid">Grid</option>
                        </select>
                    </div>
                    <div class="layout-selector cluster-selector">
                        <label>Clusters:</label>
                        <select id="cluster-mode-select" onchange="setClusterMode(this.value)">
                            <option value="directory" selected>Directory</option>
                            <option value="semantic">Semantic</option>
                        </select>
                    </div>
                    <span class="legend-item"><span class="dot" style="background:#7ee787;"></span> .py</span>
                    <span class="legend-item"><span class="dot" style="background:#f0883e;"></span> .yaml</span>
                    <span class="legend-item"><span class="dot" style="background:#58a6ff;"></span> .json</span>
                    <span class="legend-item"><span class="dot" style="background:#8b949e;"></span> .md</span>
                    <button id="aura-toggle" class="aura-toggle active" onclick="toggleAuras()" title="Toggle nebula clusters">Nebulae</button>
                    <button id="reveal-all-toggle" class="aura-toggle" onclick="toggleRevealAll()" title="Show all nodes (toggle Constellation Mode)">Reveal All</button>
                </div>
                <div class="heat-legend" id="heat-legend">
                    <div class="heat-legend-title">Phase Activity</div>
                    <div class="heat-legend-bar"></div>
                    <div class="heat-legend-labels"><span>Untouched</span><span>Active</span></div>
                    <div class="heat-legend-stat" id="heat-stat"></div>
                </div>
            </div>
        </div>
        <!-- Story Mode Controls - below graph -->
        <div class="story-mode" id="story-mode">
            <div class="story-header">
                <h3 style="margin:0;color:#58a6ff;">Story Mode</h3>
                <div class="story-controls">
                    <button id="play-btn" onclick="togglePlay()" title="Play/Pause animation">Play</button>
                    <button onclick="jumpToStart()" title="Jump to beginning">Start</button>
                    <button onclick="jumpToEnd()" title="Jump to end">End</button>
                    <button onclick="resetStoryMode()" title="Reset to beginning">Reset</button>
                    <button id="story-aura-toggle" class="active" onclick="toggleAuras()" title="Toggle nebula clouds">Clouds</button>
                    <div class="speed-control">
                        <span>Speed:</span>
                        <select id="speed-select" onchange="setSpeed(this.value)">
                            <option value="25">Fast</option>
                            <option value="100" selected>Normal</option>
                            <option value="500">Slow</option>
                            <option value="1000">Very Slow</option>
                        </select>
                    </div>
                    <div class="layout-selector story-layout">
                        <label>Layout:</label>
                        <select id="story-layout-select" onchange="setStoryLayout(this.value)">
                            <option value="force" selected>Force-Directed</option>
                            <option value="bundling">Edge Bundling</option>
                            <option value="treemap">Treemap</option>
                            <option value="packing">Circle Packing</option>
                            <option value="sunburst">Sunburst</option>
                            <option value="grid">Grid</option>
                        </select>
                    </div>
                </div>
            </div>
            <div class="timeline-scrubber" id="timeline-scrubber">
                <div class="timeline-phases" id="timeline-phases"></div>
                <div class="scrubber-handle" id="scrubber-handle" style="left: 0%;"></div>
            </div>
            <div class="story-info">
                <span id="current-position">Event 0 of {total_events}</span>
                <span id="current-phase">-</span>
            </div>
            <div class="story-narrative" id="story-narrative">
                <span class="phase-icon"></span> Click Play or drag the timeline to watch the session unfold...
            </div>
            <div class="action-legend">
                <span style="color:#6e7681;">Action:</span>
                <span class="action-legend-item"><span class="action-legend-dot read"></span> Read</span>
                <span class="action-legend-item"><span class="action-legend-dot edit"></span> Edit</span>
                <span class="action-legend-item"><span class="action-legend-dot run"></span> Run</span>
                <span class="action-legend-item"><span class="action-legend-dot fail"></span> Fail</span>
            </div>
        </div>
        <div class="zoom-info">Scroll to zoom - Drag to pan - Click nodes for details</div>
        <div class="heatmap-legend" id="heatmap-legend">
            <div class="legend-title" id="legend-title">Recency</div>
            <div class="legend-bar" id="legend-bar"></div>
            <div class="legend-labels"><span id="legend-left">Stale</span><span id="legend-right">Recent</span></div>
        </div>
        <!-- Fullscreen Story Mode Overlay -->
        <div class="fullscreen-story" id="fullscreen-story">
            <div class="fs-story-header">
                <span style="color:#58a6ff;font-weight:600;">Story Mode</span>
                <div class="fs-story-controls">
                    <button id="fs-play-btn" onclick="togglePlay()" title="Play/Pause animation">Play</button>
                    <button onclick="jumpToStart()" title="Jump to beginning">Start</button>
                    <button onclick="jumpToEnd()" title="Jump to end">End</button>
                    <button onclick="resetStoryMode()" title="Reset to beginning">Reset</button>
                    <button id="fs-aura-toggle" class="active" onclick="toggleAuras()" title="Toggle nebula clouds">Clouds</button>
                    <div class="speed-control">
                        <span>Speed:</span>
                        <select id="fs-speed-select" onchange="setSpeed(this.value)">
                            <option value="25">Fast</option>
                            <option value="100" selected>Normal</option>
                            <option value="500">Slow</option>
                            <option value="1000">Very Slow</option>
                        </select>
                    </div>
                </div>
            </div>
            <div class="fs-timeline-scrubber" id="fs-timeline-scrubber">
                <div class="fs-timeline-phases" id="fs-timeline-phases"></div>
                <div class="fs-scrubber-handle" id="fs-scrubber-handle" style="left: 0%;"></div>
            </div>
            <div class="fs-story-info">
                <span id="fs-current-position">Event 0 of {total_events}</span>
                <span id="fs-current-phase">-</span>
            </div>
            <div class="fs-story-narrative" id="fs-story-narrative">
                <span class="phase-icon"></span> Click Play or drag the timeline to watch the session unfold...
            </div>
        </div>
    </div>

    <div class="timeline-container">
        <h2>Timeline (Recent 100)</h2>
        <div id="timeline">
            {timeline_html}
        </div>
    </div>
    </div><!-- end advanced-view -->

    <div class="tooltip" id="tooltip"></div>
    <div class="detail-panel" id="detail-panel">
        <h3><span id="detail-title"></span><span class="close" onclick="closeDetail()">&times;</span></h3>
        <div id="detail-content"></div>
    </div>

    <!-- Insight Card for node details -->
    <div class="insight-card" id="insight-card">
        <div class="insight-card-header">
            <div class="insight-card-title">
                <span class="insight-card-icon" id="insight-icon"></span>
                <div>
                    <div class="insight-card-name" id="insight-name">filename.py</div>
                    <div class="insight-card-path" id="insight-path">path/to/file</div>
                </div>
            </div>
            <button class="insight-card-close" onclick="closeInsightCard()">&times;</button>
        </div>
        <div class="insight-card-stats">
            <div class="insight-stat">
                <div class="insight-stat-value" id="insight-total">0</div>
                <div class="insight-stat-label">Touches</div>
            </div>
            <div class="insight-stat">
                <div class="insight-stat-value edit" id="insight-edits">0</div>
                <div class="insight-stat-label">Edits</div>
            </div>
            <div class="insight-stat">
                <div class="insight-stat-value read" id="insight-reads">0</div>
                <div class="insight-stat-label">Reads</div>
            </div>
        </div>
        <div class="insight-card-timeline">
            <div class="insight-timeline-label">Action Breakdown</div>
            <div class="insight-timeline-bar" id="insight-timeline-bar"></div>
        </div>
        <div class="insight-card-sparkline">
            <div class="insight-sparkline-label">
                <span>Activity Over Time</span>
                <span id="insight-last-touch">Last: --</span>
            </div>
            <svg class="insight-sparkline-svg" id="insight-sparkline">
                <defs>
                    <linearGradient id="sparklineGradient" x1="0%" y1="0%" x2="0%" y2="100%">
                        <stop offset="0%" style="stop-color:#58a6ff;stop-opacity:0.3"/>
                        <stop offset="100%" style="stop-color:#58a6ff;stop-opacity:0"/>
                    </linearGradient>
                </defs>
            </svg>
        </div>
        <div class="insight-card-insight">
            <div class="insight-text">
                <span class="insight-icon"></span>
                <span class="insight-message" id="insight-message">Loading insight...</span>
            </div>
        </div>
        <div class="insight-card-phases" id="insight-phases">
            <div class="insight-phases-label">Phase Participation</div>
            <div class="insight-phases-list" id="insight-phases-list"></div>
        </div>
        <div class="insight-card-related" id="insight-related">
            <div class="insight-related-label">Related Files</div>
            <div class="insight-related-list" id="insight-related-list"></div>
        </div>
        <div class="insight-card-diff" id="insight-diff">
            <div class="insight-diff-header">
                <div class="insight-diff-label">Recent Changes</div>
                <button class="insight-diff-export" onclick="exportDiffForLLM()" title="Export for LLM (E)">📤 Export</button>
            </div>
            <div class="insight-diff-content" id="insight-diff-content">
                <span class="diff-placeholder">Diff preview coming soon...</span>
            </div>
        </div>
    </div>

    <div class="keyboard-hint">
        <kbd>D</kbd> expand diff
        <kbd>E</kbd> export
        <kbd>←/→</kbd> phases
        <kbd>Space</kbd> play
        <kbd>Esc</kbd> close
    </div>

    <!-- Data injection for JavaScript -->
    <script type="application/json" id="proofviz-data">
{json.dumps(proofviz_data)}
    </script>

    <!-- Initialize data for JS -->
    <script>
        window.PROOFVIZ_DATA = JSON.parse(document.getElementById('proofviz-data').textContent);
    </script>

    {js_tag}
</body>
</html>'''


def _get_inline_css() -> str:
    """Read CSS file and return inline style tag."""
    from pathlib import Path
    css_path = Path(__file__).parent / 'proof_viz_assets' / 'styles.css'
    if css_path.exists():
        css_content = css_path.read_text()
        return f'<style>\n{css_content}\n</style>'
    return '<!-- CSS file not found -->'


def _get_inline_js() -> str:
    """Read JS file and return inline script tag."""
    from pathlib import Path
    js_path = Path(__file__).parent / 'proof_viz_assets' / 'proof_viz.js'
    if js_path.exists():
        js_content = js_path.read_text()
        return f'<script>\n{js_content}\n</script>'
    return '<!-- JS file not found -->'
