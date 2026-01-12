/**
 * Proof Visualizer - Main JavaScript
 * Extracted from proof_visualizer.py for maintainability.
 *
 * Requires: D3.js v7, window.PROOFVIZ_DATA to be set before loading
 *
 * PROOFVIZ_DATA structure:
 * {
 *   graph: { nodes: [], edges: [], clusters: [] },
 *   explorer: { nodes: [], edges: [] } | null,
 *   diffCache: { filepath: [{timestamp, old, new}] },
 *   savedLayout: { story: {nodeId: {x, y}}, explorer: {...} },
 *   insights: [{ title, detail }],
 *   beginner: { status, status_text, status_emoji, ... },
 *   phases: [{ intent, start, end, count, ... }],
 *   timeline: [{ timestamp, tool, success, file, full_path, action }]
 * }
 */

// Verify data is available
if (!window.PROOFVIZ_DATA) {
    console.error('PROOFVIZ_DATA not set - visualization will not work');
    throw new Error('PROOFVIZ_DATA required before loading proof_viz.js');
}

const graphData = window.PROOFVIZ_DATA.graph;
        const explorerData = window.PROOFVIZ_DATA.explorer;
        const diffCache = window.PROOFVIZ_DATA.diffCache;
        const savedLayout = window.PROOFVIZ_DATA.savedLayout;
        const maxCount = Math.max(...graphData.nodes.map(n => n.count));
        let currentMode = 'story';
        let currentClusterMode = 'directory';
        const DEBUG = window.PROOFVIZ_DEBUG === true;
        const debugLog = (...args) => {
            if (DEBUG) console.log(...args);
        };

        function ensureClusterFields() {
            if (!explorerData || !explorerData.nodes) return;
            explorerData.nodes.forEach(n => {
                if (n.cluster_dir === undefined || n.cluster_dir === null) {
                    n.cluster_dir = (n.cluster !== undefined && n.cluster !== null) ? n.cluster : -1;
                }
                if (n.cluster_semantic === undefined || n.cluster_semantic === null) {
                    n.cluster_semantic = -1;
                }
            });
        }

        function hasSemanticClusters() {
            if (!explorerData || !explorerData.nodes) return false;
            return explorerData.nodes.some(n => (n.cluster_semantic ?? -1) >= 0);
        }

        function applyClusterMode(mode) {
            if (!explorerData || !explorerData.nodes) return false;
            ensureClusterFields();
            const useSemantic = mode === 'semantic';
            if (useSemantic && !hasSemanticClusters()) {
                return false;
            }
            explorerData.nodes.forEach(n => {
                n.cluster = useSemantic ? (n.cluster_semantic ?? -1) : (n.cluster_dir ?? -1);
            });
            return true;
        }

        function setClusterMode(mode) {
            const nextMode = (mode === 'semantic') ? 'semantic' : 'directory';
            if (nextMode === 'semantic' && !hasSemanticClusters()) {
                mode = 'directory';
            } else {
                mode = nextMode;
            }
            if (!applyClusterMode(mode)) {
                mode = 'directory';
                applyClusterMode(mode);
            }
            currentClusterMode = mode;
            const select = document.getElementById('cluster-mode-select');
            if (select) {
                select.value = mode;
                const semanticOption = select.querySelector('option[value=\"semantic\"]');
                if (semanticOption) {
                    semanticOption.disabled = !hasSemanticClusters();
                }
            }
            if (currentMode === 'explorer') {
                setLayout(currentLayout);
            }
        }

        applyClusterMode(currentClusterMode);

        const container = document.getElementById("graph-wrapper");
        const svg = d3.select("#graph");
        let width = container.clientWidth || 800;
        let height = container.clientHeight || 600;
        svg.attr("width", width).attr("height", height);
        debugLog('Graph dimensions:', width, 'x', height);

        // Zoom behavior
        const zoom = d3.zoom()
            .scaleExtent([0.2, 5])
            .on("zoom", (event) => {
                g.attr("transform", event.transform);
            });
        svg.call(zoom);

        const g = svg.append("g");

        // Scale for node size (5-25 based on count)
        const nodeScale = d3.scaleSqrt()
            .domain([1, maxCount])
            .range([6, 25]);

        // Scale for edge width
        const edgeScale = d3.scaleLinear()
            .domain([1, Math.max(...graphData.edges.map(e => e.count))])
            .range([1, 6]);

        // ═══════════════════════════════════════════════════════════
        // CONSTELLATION MODE - Calculate brightness for Story mode
        // ═══════════════════════════════════════════════════════════

        // Brightness = count (activity) normalized
        const storyMaxCount = Math.max(...graphData.nodes.map(n => n.count || 1));
        graphData.nodes.forEach(n => {
            n.brightness = (n.count || 1) / storyMaxCount;  // 0-1 normalized
        });

        // Sort by brightness and assign tier
        const storySorted = [...graphData.nodes].sort((a, b) => b.brightness - a.brightness);
        const storyStarCount = Math.min(7, graphData.nodes.length);
        const storyContextCount = Math.min(15, graphData.nodes.length - storyStarCount);

        storySorted.forEach((n, i) => {
            if (i < storyStarCount) {
                n.tier = 'star';
            } else if (i < storyStarCount + storyContextCount) {
                n.tier = 'context';
            } else {
                n.tier = 'dark';
            }
        });

        debugLog(`Constellation (Story): ${storyStarCount} stars, ${storyContextCount} context, ${graphData.nodes.length - storyStarCount - storyContextCount} dark matter`);

        // ═══════════════════════════════════════════════════════════
        // CLUSTER ISLANDS - Story Mode: Position by type and directory
        // Only apply if no saved positions exist (fresh layout)
        // ═══════════════════════════════════════════════════════════

        // Check if we have saved positions to restore
        const storySavedPositions = (savedLayout && savedLayout.story) || JSON.parse(localStorage.getItem('nodePositions') || '{}');
        const hasSavedPositions = Object.keys(storySavedPositions).length > graphData.nodes.length * 0.5;

        if (!hasSavedPositions) {
            // No saved layout - apply Cluster Islands initial positioning
            const nodeGroups = {};
            graphData.nodes.forEach(n => {
                if (n.type === 'tool' || n.id.startsWith('tool:')) {
                    nodeGroups['__tools__'] = nodeGroups['__tools__'] || [];
                    nodeGroups['__tools__'].push(n);
                } else {
                    // Files: group by directory
                    const dir = n.dir || (n.path ? n.path.split('/').slice(0, -1).join('/') : 'root') || 'root';
                    nodeGroups[dir] = nodeGroups[dir] || [];
                    nodeGroups[dir].push(n);
                }
            });

            // Position groups in a ring
            const groupNames = Object.keys(nodeGroups).sort((a, b) => {
                // Tools always first (top of ring)
                if (a === '__tools__') return -1;
                if (b === '__tools__') return 1;
                return nodeGroups[b].length - nodeGroups[a].length;  // Larger groups first
            });

            const numGroups = groupNames.length;
            const storyRingRadius = Math.min(width, height) * 0.32;
            const storyCenterX = width / 2;
            const storyCenterY = height / 2;
            const storyZoneRadius = 70;

            groupNames.forEach((groupName, i) => {
                const angle = (2 * Math.PI * i / numGroups) - Math.PI / 2;
                const groupCenterX = storyCenterX + storyRingRadius * Math.cos(angle);
                const groupCenterY = storyCenterY + storyRingRadius * Math.sin(angle);

                nodeGroups[groupName].forEach(n => {
                    const offsetAngle = Math.random() * 2 * Math.PI;
                    const offsetRadius = Math.random() * storyZoneRadius;
                    n.x = groupCenterX + offsetRadius * Math.cos(offsetAngle);
                    n.y = groupCenterY + offsetRadius * Math.sin(offsetAngle);
                });
            });

            debugLog(`Cluster Islands (Story): ${numGroups} groups positioned in ring, ${graphData.nodes.length} nodes assigned`);
        } else {
            debugLog(`Cluster Islands (Story): Skipped - restoring ${Object.keys(storySavedPositions).length} saved positions`);
        }

        // Group force - keeps nodes near their type/directory group
        function groupForce(strength) {
            let nodes;
            const groupCenters = {};

            function force(alpha) {
                // Compute group centers
                Object.keys(groupCenters).forEach(g => {
                    groupCenters[g] = { x: 0, y: 0, count: 0 };
                });
                nodes.forEach(n => {
                    const g = n.group || 'root';
                    if (!groupCenters[g]) groupCenters[g] = { x: 0, y: 0, count: 0 };
                    groupCenters[g].x += n.x;
                    groupCenters[g].y += n.y;
                    groupCenters[g].count++;
                });
                Object.keys(groupCenters).forEach(g => {
                    if (groupCenters[g].count > 0) {
                        groupCenters[g].x /= groupCenters[g].count;
                        groupCenters[g].y /= groupCenters[g].count;
                    }
                });

                // Pull nodes toward their group center
                nodes.forEach(n => {
                    const center = groupCenters[n.group || 'root'];
                    if (center) {
                        n.vx += (center.x - n.x) * strength * alpha;
                        n.vy += (center.y - n.y) * strength * alpha;
                    }
                });
            }

            force.initialize = _ => {
                nodes = _;
                // Assign groups based on type/directory
                nodes.forEach(n => {
                    if (n.type === 'tool' || n.id.startsWith('tool:')) {
                        n.group = '__tools__';
                    } else {
                        n.group = n.dir || 'root';
                    }
                });
            };
            return force;
        }

        const simulation = d3.forceSimulation(graphData.nodes)
            .force("link", d3.forceLink(graphData.edges).id(d => d.id).distance(120))
            .force("charge", d3.forceManyBody().strength(-400))
            .force("center", d3.forceCenter(width / 2, height / 2).strength(0.03))  // Weaker center
            .force("group", groupForce(0.5))  // Keep groups together
            .force("collision", d3.forceCollide().radius(d => nodeScale(d.count) + 20));

        // Extension colors for auras
        const extColors = {
            '.py': '#7ee787',
            '.yaml': '#f0883e', '.yml': '#f0883e',
            '.json': '#58a6ff',
            '.md': '#8b949e',
            '.js': '#f1e05a', '.ts': '#3178c6', '.tsx': '#3178c6',
            '.sh': '#89e051',
            '.html': '#e34c26', '.css': '#563d7c'
        };

        // Helper to get extension from node id
        function getNodeExt(nodeId) {
            const parts = nodeId.split('.');
            if (parts.length > 1) return '.' + parts[parts.length - 1];
            return '';
        }

        // Helper to split text on any line ending (handles \n, \r\n, \r)
        function splitLines(text) {
            if (!text) return [];
            return text.split(/\r\n|\r|\n/);
        }

        const link = g.append("g")
            .selectAll("line")
            .data(graphData.edges)
            .join("line")
            .attr("class", "link")
            .attr("stroke-width", d => edgeScale(d.count));

        // Soft Territory - Aura layer (before nodes so auras are behind)
        const auraGroup = g.append('g').attr('class', 'aura-layer')
            .style('filter', 'blur(20px)')
            .style('pointer-events', 'none');

        const auraRadius = 60;
        const auras = auraGroup.selectAll('circle')
            .data(graphData.nodes.filter(n => n.type === 'file'))
            .join('circle')
            .attr('class', 'node-aura')
            .attr('r', d => auraRadius + nodeScale(d.count) * 3)
            .attr('fill', d => extColors[getNodeExt(d.id)] || '#8b949e')
            .attr('opacity', 0.35);

        const node = g.append("g")
            .selectAll("g")
            .data(graphData.nodes)
            .join("g")
            .attr("class", "node")
            .on("mouseover", showTooltip)
            .on("mouseout", hideTooltip)
            .on("click", showInsightCard);

        // CONSTELLATION MODE: opacity based on tier
        const storyTierOpacity = { star: 1.0, context: 0.3, dark: 0.08 };

        node.append("circle")
            .attr("r", d => nodeScale(d.count))
            .attr("class", d => `node-shape ${d.type === "tool" ? "node-tool" : "node-file"} tier-${d.tier}`)
            .style('opacity', d => storyTierOpacity[d.tier] || 0.08)
            .style('filter', d => d.tier === 'star' ? 'drop-shadow(0 0 6px currentColor)' : 'none')
            .style('transition', 'opacity 0.2s ease');

        node.append("text")
            .attr("class", d => `node-label tier-${d.tier}`)
            .attr("dx", d => nodeScale(d.count) + 4)
            .attr("dy", 4)
            .text(d => d.id.split(":")[1])
            .style('opacity', d => d.tier === 'star' ? 1.0 : 0)
            .style('transition', 'opacity 0.2s ease');

        // Try to restore saved node positions (prefer file-based layout over localStorage)
        const positions = (savedLayout && savedLayout.story) || JSON.parse(localStorage.getItem('nodePositions') || '{}');
        if (Object.keys(positions).length > 0) {
            let validCount = 0;
            graphData.nodes.forEach(n => {
                const pos = positions[n.id];
                // Only restore if position is within reasonable bounds
                if (pos && pos.x > 0 && pos.x < width && pos.y > 0 && pos.y < height) {
                    n.x = pos.x;
                    n.y = pos.y;
                    n.fx = pos.x;
                    n.fy = pos.y;
                    validCount++;
                }
            });
            // Only skip simulation if most positions were restored
            if (validCount > graphData.nodes.length * 0.8) {
                simulation.alpha(0).stop();
                // Manually update visual positions since tick won't run
                link.attr("x1", d => d.source.x).attr("y1", d => d.source.y)
                    .attr("x2", d => d.target.x).attr("y2", d => d.target.y);
                node.attr("transform", d => `translate(${d.x},${d.y})`);
                auras.attr('cx', d => d.x).attr('cy', d => d.y);
                debugLog('Restored', validCount, 'node positions from', savedLayout?.story ? 'file' : 'localStorage');
            } else {
                // Clear bad positions and let simulation run
                localStorage.removeItem('nodePositions');
                graphData.nodes.forEach(n => { n.fx = null; n.fy = null; });
                debugLog('Cleared invalid positions, running simulation');
            }
        }

        simulation.on("tick", () => {
            link
                .attr("x1", d => d.source.x)
                .attr("y1", d => d.source.y)
                .attr("x2", d => d.target.x)
                .attr("y2", d => d.target.y);
            node.attr("transform", d => `translate(${d.x},${d.y})`);
            // Update aura positions to follow nodes
            auras.attr('cx', d => d.x).attr('cy', d => d.y);
        }).on("end", () => {
            // Save positions when simulation settles
            saveNodePositions();
            simulation.stop();
            // Rebuild quadtree after positions stabilize
            if (typeof window.rebuildStoryQuadtree === 'function') {
                window.rebuildStoryQuadtree();
            }
        });

        function saveNodePositions() {
            const positions = {};
            graphData.nodes.forEach(n => {
                positions[n.id] = { x: n.x, y: n.y };
            });
            localStorage.setItem('nodePositions', JSON.stringify(positions));
        }

        // Also save when user drags nodes
        node.call(d3.drag()
            .on("start", (e, d) => {
                if (!e.active) simulation.alphaTarget(0.3).restart();
                d.fx = d.x;
                d.fy = d.y;
            })
            .on("drag", (e, d) => {
                d.fx = e.x;
                d.fy = e.y;
            })
            .on("end", (e, d) => {
                if (!e.active) simulation.alphaTarget(0);
                // Keep the position fixed after drag
                saveNodePositions();
                // Rebuild quadtree after drag
                if (typeof window.rebuildStoryQuadtree === 'function') {
                    window.rebuildStoryQuadtree();
                }
            }));

        // Store reference for global access (toggleRevealAll, updateGraphVisibility, etc.)
        window.storyNode = node;
        window.storyLink = link;
        window.storyGraphData = graphData;

        // ═══════════════════════════════════════════════════════════
        // CONSTELLATION MODE: Hover Proximity Reveal (Story)
        // Nodes within 100px of cursor brighten and show labels
        // ═══════════════════════════════════════════════════════════

        const PROXIMITY_RADIUS = 100;
        const PROXIMITY_RADIUS_SQ = PROXIMITY_RADIUS * PROXIMITY_RADIUS;
        // storyTierOpacity already declared above in tier opacity section

        // Quadtree for O(log N) proximity detection
        let storyQuadtree = d3.quadtree()
            .x(d => d.x)
            .y(d => d.y)
            .addAll(graphData.nodes);

        function rebuildStoryQuadtree() {
            storyQuadtree = d3.quadtree()
                .x(d => d.x)
                .y(d => d.y)
                .addAll(graphData.nodes);
        }

        // Expose for rebuild after simulation/drag
        window.rebuildStoryQuadtree = rebuildStoryQuadtree;

        svg.on('mousemove', function(event) {
            // Skip if Reveal All is enabled - everything already visible
            if (typeof revealAllEnabled !== 'undefined' && revealAllEnabled) return;

            const [mx, my] = d3.pointer(event);

            // Clear previous proximity flags
            graphData.nodes.forEach(n => n.isProximity = false);

            // During simulation animation, quadtree bounds are stale - fall back to linear scan
            // Once simulation stabilizes (alpha < 0.01), quadtree is accurate
            const isAnimating = simulation.alpha() > 0.01;

            if (isAnimating) {
                // Linear scan during animation (accurate but O(N))
                graphData.nodes.forEach(n => {
                    const dx = n.x - mx;
                    const dy = n.y - my;
                    if (dx * dx + dy * dy < PROXIMITY_RADIUS_SQ) {
                        n.isProximity = true;
                    }
                });
            } else {
                // Use quadtree for O(log N) proximity detection (stable positions)
                storyQuadtree.visit((quad, x0, y0, x1, y1) => {
                    // Skip if the quad is entirely outside proximity radius
                    const dx = Math.max(0, Math.max(x0 - mx, mx - x1));
                    const dy = Math.max(0, Math.max(y0 - my, my - y1));
                    if (dx * dx + dy * dy > PROXIMITY_RADIUS_SQ) return true; // prune

                    // Check leaf node - verify with current coordinates
                    if (!quad.length && quad.data) {
                        const d = quad.data;
                        const ndx = d.x - mx;
                        const ndy = d.y - my;
                        if (ndx * ndx + ndy * ndy < PROXIMITY_RADIUS_SQ) {
                            d.isProximity = true;
                        }
                    }
                    return false; // continue traversal
                });
            }

            // Update node opacities
            node.select('circle')
                .style('opacity', d => d.isProximity ? 1.0 : storyTierOpacity[d.tier] || 0.08)
                .style('filter', d => (d.tier === 'star' || d.isProximity) ? 'drop-shadow(0 0 6px currentColor)' : 'none');

            // Update label visibility
            node.select('text')
                .style('opacity', d => (d.tier === 'star' || d.isProximity) ? 1.0 : 0);
        });

        // Reset when mouse leaves SVG
        svg.on('mouseleave', function() {
            // Skip if Reveal All is enabled
            if (typeof revealAllEnabled !== 'undefined' && revealAllEnabled) return;

            graphData.nodes.forEach(n => n.isProximity = false);

            node.select('circle')
                .style('opacity', d => storyTierOpacity[d.tier] || 0.08)
                .style('filter', d => d.tier === 'star' ? 'drop-shadow(0 0 6px currentColor)' : 'none');

            node.select('text')
                .style('opacity', d => d.tier === 'star' ? 1.0 : 0);
        });

        // Tooltip
        const tooltip = document.getElementById("tooltip");
        function showTooltip(event, d) {
            const name = d.id.split(":")[1];
            let html = `<h3>${d.type === 'tool' ? '🔧' : '📄'} ${name}</h3>`;
            if (d.path) html += `<div class="path">${d.path}</div>`;
            html += `<div><span class="count">${d.count}</span> interactions</div>`;
            if (d.timestamps && d.timestamps.length > 0) {
                html += `<div class="timestamps"><div>Recent:</div>`;
                d.timestamps.slice(-3).forEach(t => {
                    html += `<div>${t}</div>`;
                });
                html += `</div>`;
            }
            tooltip.innerHTML = html;
            tooltip.style.display = "block";
            tooltip.style.left = (event.pageX + 15) + "px";
            tooltip.style.top = (event.pageY - 10) + "px";
        }
        function hideTooltip() {
            tooltip.style.display = "none";
        }

        // Detail panel with co-occurrence
        function showDetail(event, d) {
            event.stopPropagation();
            const panel = document.getElementById("detail-panel");
            const title = document.getElementById("detail-title");
            const content = document.getElementById("detail-content");

            const name = d.id.split(":")[1];
            title.textContent = `${d.type === 'tool' ? '🔧' : '📄'} ${name}`;

            // Find connected nodes
            const connected = [];
            graphData.edges.forEach(e => {
                if (e.source.id === d.id) connected.push({ node: e.target, count: e.count });
                if (e.target.id === d.id) connected.push({ node: e.source, count: e.count });
            });
            connected.sort((a, b) => b.count - a.count);

            // Check if anomaly
            const isAnomaly = d.count > threshold;

            let html = `
                <div class="info-row"><span class="info-label">Type</span><span class="info-value">${d.type}${isAnomaly ? ' ⚠️ anomaly' : ''}</span></div>
                <div class="info-row"><span class="info-label">Interactions</span><span class="info-value">${d.count}</span></div>
            `;
            if (d.dir) {
                html += `<div class="info-row"><span class="info-label">Directory</span><span class="info-value">${d.dir}/</span></div>`;
            }
            if (d.recency !== undefined) {
                const recStr = d.recency < 1 ? 'just now' : d.recency < 24 ? Math.round(d.recency) + 'h ago' : Math.round(d.recency / 24) + 'd ago';
                html += `<div class="info-row"><span class="info-label">Last Touch</span><span class="info-value">${recStr}</span></div>`;
            }
            if (d.path) {
                html += `<div class="info-row"><span class="info-label">Path</span><span class="info-value" style="font-size:10px;word-break:break-all;">${d.path}</span></div>`;
            }
            if (connected.length > 0) {
                html += `<div class="timestamp-list"><h4>Connected (${connected.length})</h4>`;
                connected.slice(0, 8).forEach(c => {
                    const cName = c.node.id.split(':')[1];
                    const cIcon = c.node.type === 'tool' ? '🔧' : '📄';
                    html += `<div class="timestamp-item">${cIcon} ${cName} <span style="color:#58a6ff">(${c.count}x)</span></div>`;
                });
                html += `</div>`;
            }
            if (d.timestamps && d.timestamps.length > 0) {
                html += `<div class="timestamp-list"><h4>Recent Activity (${d.timestamps.length})</h4>`;
                d.timestamps.slice().reverse().slice(0, 5).forEach(t => {
                    html += `<div class="timestamp-item">${t}</div>`;
                });
                html += `</div>`;
            }
            content.innerHTML = html;
            panel.classList.add("visible");
        }
        function closeDetail() {
            document.getElementById("detail-panel").classList.remove("visible");
        }

        // ═══════════════════════════════════════════════════════════
        // INSIGHT CARD - SOTA Node Details
        // ═══════════════════════════════════════════════════════════

        function showInsightCard(event, d) {
            event.stopPropagation();
            const card = document.getElementById("insight-card");
            const name = d.id.split(":")[1];
            const isFile = d.type === 'file';

            // Icon based on type and dominant action
            const iconMap = {
                tool: '🔧',
                file: d.dominant === 'edit' ? '✏️' : d.dominant === 'run' ? '⚡' : '📄'
            };
            document.getElementById("insight-icon").textContent = iconMap[d.type] || '📄';
            document.getElementById("insight-name").textContent = name;
            document.getElementById("insight-path").textContent = d.path ? d.path.replace(name, '').replace(/\/$/, '') || 'Root' : d.type;

            // Stats
            const actions = d.actions || {};
            const reads = actions.read || 0;
            const edits = actions.edit || 0;
            const runs = actions.run || 0;
            const fails = actions.fail || 0;
            const total = d.count || 0;

            document.getElementById("insight-total").textContent = total;
            document.getElementById("insight-edits").textContent = edits;
            document.getElementById("insight-reads").textContent = reads;

            // Action breakdown bar
            const bar = document.getElementById("insight-timeline-bar");
            bar.innerHTML = '';
            if (total > 0) {
                if (reads > 0) bar.innerHTML += `<div class="insight-timeline-segment read" style="width:${(reads/total)*100}%" title="Reads: ${reads}"></div>`;
                if (edits > 0) bar.innerHTML += `<div class="insight-timeline-segment edit" style="width:${(edits/total)*100}%" title="Edits: ${edits}"></div>`;
                if (runs > 0) bar.innerHTML += `<div class="insight-timeline-segment run" style="width:${(runs/total)*100}%" title="Runs: ${runs}"></div>`;
                if (fails > 0) bar.innerHTML += `<div class="insight-timeline-segment fail" style="width:${(fails/total)*100}%" title="Fails: ${fails}"></div>`;
            }

            // Last touch
            const lastTouch = document.getElementById("insight-last-touch");
            if (d.recency !== undefined) {
                const recStr = d.recency < 1 ? 'just now' : d.recency < 24 ? Math.round(d.recency) + 'h ago' : Math.round(d.recency / 24) + 'd ago';
                lastTouch.textContent = `Last: ${recStr}`;
            } else {
                lastTouch.textContent = '';
            }

            // Sparkline
            renderSparkline(d);

            // Smart insight
            document.getElementById("insight-message").textContent = generateInsight(d, actions);

            // Phase participation - find phases where this file appears
            const phasesList = document.getElementById("insight-phases-list");
            phasesList.innerHTML = '';
            const filePhases = [];
            const nodeFileName = d.id.startsWith('file:') ? d.id.split(':')[1] : null;

            if (nodeFileName && phasesData.length > 0) {
                phasesData.forEach((phase, idx) => {
                    // Check if this file was touched during this phase
                    for (let i = phase.start; i <= phase.end && i < timelineData.length; i++) {
                        if (timelineData[i].file === nodeFileName) {
                            filePhases.push({ phase, idx });
                            break;
                        }
                    }
                });
            }

            if (filePhases.length > 0) {
                // Show up to 4 most recent phases
                const recentPhases = filePhases.slice(-4);
                recentPhases.forEach(({ phase, idx }) => {
                    const badge = document.createElement('span');
                    badge.className = `phase-badge ${phase.intent}`;
                    badge.innerHTML = `${phaseIcons[phase.intent] || '📋'} #${idx + 1}`;
                    badge.title = `Jump to Phase ${idx + 1} (${phase.intent})`;
                    badge.onclick = (e) => {
                        e.stopPropagation();
                        // Jump to phase start
                        updateTimeline(phase.start);
                        document.getElementById('timeline-slider').value = phase.start;
                        const fsSlider = document.getElementById('fs-timeline-slider');
                        if (fsSlider) fsSlider.value = phase.start;
                    };
                    phasesList.appendChild(badge);
                });
                if (filePhases.length > 4) {
                    const more = document.createElement('span');
                    more.className = 'phase-badge mixed';
                    more.textContent = `+${filePhases.length - 4} more`;
                    phasesList.appendChild(more);
                }
            } else {
                phasesList.innerHTML = '<span style="color:#6e7681;font-size:11px;">Not in any phase yet</span>';
            }

            // Related files - find nodes connected via edges
            // Use appropriate edge data based on current mode
            const relatedList = document.getElementById("insight-related-list");
            relatedList.innerHTML = '';
            const relatedNodes = [];
            const nodeName = d.id.startsWith('file:') ? d.id.split(':')[1] : d.id;

            if (currentMode === 'explorer' && explorerData) {
                // Explorer mode: use explorerData.edges (source/target are full paths like "tools/file.py")
                // Find the node's full path ID from explorerData
                const explorerNode = explorerData.nodes.find(n => n.name === nodeName);
                const nodeFullId = explorerNode ? explorerNode.id : nodeName;

                debugLog('DEBUG related files:', { nodeName, explorerNode: !!explorerNode, nodeFullId, edgeCount: explorerData.edges?.length });

                // Track relationship types per file
                const relatedMap = new Map();  // fullId -> { types: Set, count, id, name }

                let matchCount = 0;
                (explorerData.edges || []).forEach((edge, i) => {
                    const sourceId = typeof edge.source === 'object' ? edge.source.id : edge.source;
                    const targetId = typeof edge.target === 'object' ? edge.target.id : edge.target;
                    const edgeType = edge.edgeType || edge.type || 'cooccur';

                    let relatedId = null;
                    // Match by full path ID (e.g., "tools/edge_server.py")
                    if (sourceId === nodeFullId) {
                        relatedId = targetId;
                        matchCount++;
                    } else if (targetId === nodeFullId) {
                        relatedId = sourceId;
                        matchCount++;
                    }

                    if (relatedId) {
                        if (!relatedMap.has(relatedId)) {
                            // Get the display name from explorerData nodes
                            const relNode = explorerData.nodes.find(n => n.id === relatedId);
                            const displayName = relNode ? relNode.name : relatedId.split('/').pop();
                            relatedMap.set(relatedId, { types: new Set(), count: 0, id: relatedId, name: displayName });
                        }
                        const entry = relatedMap.get(relatedId);
                        entry.types.add(edgeType);
                        entry.count += edge.weight || 1;
                    }
                });
                debugLog('DEBUG: matched', matchCount, 'edges, relatedMap size:', relatedMap.size);

                // Convert to array with type info
                relatedMap.forEach((entry, name) => {
                    relatedNodes.push({
                        id: entry.id,
                        name: entry.name,
                        count: entry.count,
                        types: Array.from(entry.types)
                    });
                });
            } else {
                // Story mode: compute related files through shared tool connections
                // Since edges are tool<->file, find files that share tools with this file
                const myTools = new Set();
                const fileToToolWeight = new Map();  // file -> total weight of connections through shared tools

                // First pass: find all tools connected to this file
                (graphData.edges || []).forEach(link => {
                    const sourceId = typeof link.source === 'object' ? link.source.id : link.source;
                    const targetId = typeof link.target === 'object' ? link.target.id : link.target;

                    if (sourceId.startsWith('tool:') && targetId === d.id) {
                        myTools.add(sourceId);
                    } else if (targetId.startsWith('tool:') && sourceId === d.id) {
                        myTools.add(targetId);
                    }
                });

                // Second pass: find other files connected to those same tools
                (graphData.edges || []).forEach(link => {
                    const sourceId = typeof link.source === 'object' ? link.source.id : link.source;
                    const targetId = typeof link.target === 'object' ? link.target.id : link.target;

                    let tool = null, file = null;
                    if (sourceId.startsWith('tool:') && targetId.startsWith('file:') && targetId !== d.id) {
                        tool = sourceId; file = targetId;
                    } else if (targetId.startsWith('tool:') && sourceId.startsWith('file:') && sourceId !== d.id) {
                        tool = targetId; file = sourceId;
                    }

                    if (tool && file && myTools.has(tool)) {
                        const current = fileToToolWeight.get(file) || 0;
                        fileToToolWeight.set(file, current + (link.count || 1));
                    }
                });

                // Convert to array
                fileToToolWeight.forEach((weight, fileId) => {
                    relatedNodes.push({ id: fileId, name: fileId.split(':')[1], count: weight });
                });
            }

            // Sort by connection count and take top 5
            relatedNodes.sort((a, b) => b.count - a.count);
            const topRelated = relatedNodes.slice(0, 5);

            if (topRelated.length > 0) {
                topRelated.forEach(rel => {
                    const fileName = rel.name;
                    const relNode = currentMode === 'explorer'
                        ? explorerData?.nodes?.find(n => n.id === rel.id || n.name === fileName)
                        : graphData.nodes.find(n => n.id === rel.id);
                    const div = document.createElement('div');
                    div.className = 'related-file';

                    // Build relationship type badges for Explorer mode
                    let typeBadges = '';
                    if (rel.types && rel.types.length > 0) {
                        const badges = rel.types.map(t => {
                            if (t === 'import') {
                                return '<span class="rel-type-badge rel-type-import" title="Import dependency">⤴</span>';
                            } else {
                                return '<span class="rel-type-badge rel-type-cooccur" title="Co-occurrence">⟷</span>';
                            }
                        }).join('');
                        typeBadges = `<span class="rel-type-badges">${badges}</span>`;
                    }

                    div.innerHTML = `
                        <span class="related-file-icon">📄</span>
                        <span class="related-file-name">${fileName}</span>
                        ${typeBadges}
                        <span class="related-file-count">${rel.count}×</span>
                    `;
                    div.onclick = (e) => {
                        e.stopPropagation();
                        if (currentMode === 'explorer' && relNode) {
                            // In explorer, navigate to that node
                            showInsightCard(e, {
                                id: 'file:' + relNode.name,
                                type: 'file',
                                count: relNode.cooccur || 0,
                                path: relNode.path,
                                actions: {},
                                dominant: 'other',
                                timestamps: []
                            });
                            focusExplorerNode(relNode.name);
                        } else if (relNode) {
                            showInsightCard(e, relNode);
                        }
                    };
                    div.onmouseenter = () => {
                        // Highlight related node in current mode
                        if (currentMode === 'explorer') {
                            d3.selectAll('.explorer-node')
                                .filter(n => n.name === fileName)
                                .select('circle')
                                .transition().duration(150)
                                .attr('stroke-width', 4)
                                .attr('stroke', '#58a6ff');
                        } else {
                            node.filter(n => n.id === rel.id)
                                .select('circle')
                                .transition().duration(150)
                                .attr('stroke-width', 4)
                                .attr('stroke', '#58a6ff');
                        }
                    };
                    div.onmouseleave = () => {
                        // Reset highlight
                        if (currentMode === 'explorer') {
                            d3.selectAll('.explorer-node')
                                .filter(n => n.name === fileName)
                                .select('circle')
                                .transition().duration(150)
                                .attr('stroke-width', 1.5)
                                .attr('stroke', '#30363d');
                        } else {
                            node.filter(n => n.id === rel.id)
                                .select('circle')
                                .transition().duration(150)
                                .attr('stroke-width', 2);
                        }
                    };
                    relatedList.appendChild(div);
                });
            } else {
                relatedList.innerHTML = '<span style="color:#6e7681;font-size:11px;">No connected files</span>';
            }

            // Render diff preview for this file
            const diffContent = document.getElementById("insight-diff-content");
            diffContent.innerHTML = '';

            // Find diffs for this file (match by filename or full path)
            const fileDiffs = [];
            const fileName = d.id.startsWith('file:') ? d.id.split(':')[1] : d.id;
            const fullPath = d.path || '';

            // Search diffCache for matching entries
            Object.entries(diffCache).forEach(([path, diffs]) => {
                // Match by filename or full path
                if (path.endsWith(fileName) || path.endsWith('/' + fileName) || path === fullPath) {
                    diffs.forEach(diff => {
                        fileDiffs.push({ ...diff, filePath: path });
                    });
                }
            });

            if (fileDiffs.length > 0) {
                // Show most recent diff (already sorted by timestamp desc)
                const latestDiff = fileDiffs[0];
                const diffEntry = document.createElement('div');
                diffEntry.className = 'diff-entry';

                // Format timestamp
                const ts = latestDiff.timestamp ? new Date(latestDiff.timestamp).toLocaleString('en-US', {
                    month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit'
                }) : 'Recent';

                // Create simple line-by-line diff
                const oldLines = splitLines(latestDiff.old).slice(0, 4);  // Limit preview
                const newLines = splitLines(latestDiff.new).slice(0, 4);

                let diffHtml = `<div class="diff-timestamp">🕐 ${ts}${latestDiff.truncated ? ' <span class="diff-truncated" title="Diff was truncated to 2000 chars">⚠️ truncated</span>' : ''}</div>`;

                // Show removed lines (old)
                oldLines.forEach(line => {
                    if (line.trim()) {
                        const escaped = line.replace(/</g, '&lt;').replace(/>/g, '&gt;');
                        diffHtml += `<div class="diff-line removed">${escaped}</div>`;
                    }
                });

                // Show added lines (new)
                newLines.forEach(line => {
                    if (line.trim()) {
                        const escaped = line.replace(/</g, '&lt;').replace(/>/g, '&gt;');
                        diffHtml += `<div class="diff-line added">${escaped}</div>`;
                    }
                });

                // Show "View more" if there are more diffs or truncated content
                const hasMore = fileDiffs.length > 1 ||
                    splitLines(latestDiff.old).length > 4 ||
                    splitLines(latestDiff.new).length > 4 ||
                    latestDiff.truncated;

                if (hasMore) {
                    diffHtml += `<div class="diff-expand" onclick="toggleDiffExpand(this, '${fileName}')">${fileDiffs.length > 1 ? `View all ${fileDiffs.length} changes` : 'Expand diff'}</div>`;
                }

                diffEntry.innerHTML = diffHtml;
                diffContent.appendChild(diffEntry);
            } else {
                diffContent.innerHTML = '<span class="diff-no-changes">No recent changes recorded</span>';
            }

            // Save open node for persistence
            localStorage.setItem('openInsightNode', d.id);

            // Anchor card to right side of viewport (fixed position)
            const cardWidth = 340;
            const cardHeight = Math.min(560, window.innerHeight - 40);
            card.style.left = 'auto';
            card.style.right = '20px';
            card.style.top = '20px';
            card.style.maxHeight = (window.innerHeight - 40) + 'px';
            card.classList.add("visible");
        }

        function closeInsightCard() {
            const card = document.getElementById("insight-card");
            card.classList.remove("visible");
            card.classList.remove("diff-focused");
            localStorage.removeItem('openInsightNode');
        }

        // Toggle Diff Takeover Mode - expand diff, collapse other sections
        function toggleDiffFocus() {
            const card = document.getElementById("insight-card");
            card.classList.toggle("diff-focused");
        }

        // Export diff in LLM-friendly format with rich session context
        function exportDiffForLLM() {
            const card = document.getElementById("insight-card");
            if (!card || !card.classList.contains('visible')) return;

            // Get current file info from card
            const nameEl = card.querySelector('.insight-card-name');
            const pathEl = card.querySelector('.insight-card-path');
            if (!nameEl) return;

            const fileName = nameEl.textContent;
            const filePath = pathEl ? pathEl.textContent : fileName;

            // Detect language from extension
            const ext = fileName.split('.').pop().toLowerCase();
            const langMap = {
                'py': 'Python', 'js': 'JavaScript', 'ts': 'TypeScript',
                'jsx': 'React JSX', 'tsx': 'React TSX', 'css': 'CSS',
                'html': 'HTML', 'yaml': 'YAML', 'yml': 'YAML',
                'json': 'JSON', 'md': 'Markdown', 'sh': 'Shell',
                'sql': 'SQL', 'go': 'Go', 'rs': 'Rust', 'java': 'Java'
            };
            const language = langMap[ext] || ext.toUpperCase();

            // Phase emoji mapping
            const phaseEmoji = {
                'building': '🔨', 'exploring': '🔍', 'debugging': '🐛',
                'executing': '⚡', 'mixed': '🔄', 'refactoring': '♻️'
            };

            // Find all diffs for this file
            const fileDiffs = [];
            Object.entries(diffCache).forEach(([path, diffs]) => {
                if (path.endsWith(fileName) || path.endsWith('/' + fileName) || path === filePath) {
                    diffs.forEach(diff => fileDiffs.push({ ...diff, filePath: path }));
                }
            });

            if (fileDiffs.length === 0) {
                showToast('No changes to export', 'warning');
                return;
            }

            // Sort by timestamp (oldest first for chronological order)
            fileDiffs.sort((a, b) => new Date(a.timestamp) - new Date(b.timestamp));

            // Get phases and timeline from PROOFVIZ_DATA
            const phases = window.PROOFVIZ_DATA?.phases || [];
            const timeline = window.PROOFVIZ_DATA?.timeline || [];

            // Find which phase each diff belongs to
            function getPhaseForTimestamp(ts) {
                const diffTime = new Date(ts).getTime();
                for (const phase of phases) {
                    const start = new Date(phase.start).getTime();
                    const end = new Date(phase.end).getTime();
                    if (diffTime >= start && diffTime <= end) {
                        return phase;
                    }
                }
                return null;
            }

            // Calculate dominant phase for this file
            const phaseCounts = {};
            fileDiffs.forEach(diff => {
                const phase = getPhaseForTimestamp(diff.timestamp);
                if (phase) {
                    phaseCounts[phase.intent] = (phaseCounts[phase.intent] || 0) + 1;
                }
            });
            const dominantPhase = Object.entries(phaseCounts)
                .sort((a, b) => b[1] - a[1])[0];

            // Find related files (other files edited in same session)
            const relatedFiles = {};
            Object.entries(diffCache).forEach(([path, diffs]) => {
                if (path === filePath || path.endsWith(fileName)) return;
                const otherFileName = path.split('/').pop();
                relatedFiles[otherFileName] = {
                    path: path,
                    edits: diffs.length,
                    relationship: 'Co-edited'
                };
            });

            // Check for import dependencies if explorer data available
            if (window.PROOFVIZ_DATA?.explorer?.edges) {
                window.PROOFVIZ_DATA.explorer.edges.forEach(edge => {
                    if (edge.type === 'import') {
                        const sourceName = edge.source?.name || edge.source;
                        const targetName = edge.target?.name || edge.target;
                        if (sourceName === fileName && relatedFiles[targetName]) {
                            relatedFiles[targetName].relationship = 'Imports';
                        } else if (targetName === fileName && relatedFiles[sourceName]) {
                            relatedFiles[sourceName].relationship = 'Imported by';
                        }
                    }
                });
            }

            // Calculate session duration for this file
            const timestamps = fileDiffs.map(d => new Date(d.timestamp)).filter(d => !isNaN(d));
            let sessionDuration = '';
            if (timestamps.length > 1) {
                const durationMs = timestamps[timestamps.length - 1] - timestamps[0];
                const minutes = Math.round(durationMs / 60000);
                sessionDuration = minutes > 60
                    ? `${Math.floor(minutes/60)}h ${minutes%60}m`
                    : `${minutes} min`;
            }

            // Get time range
            const timeRange = timestamps.length > 0
                ? `${timestamps[0].toLocaleString('en-US', {month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit'})} — ${timestamps[timestamps.length-1].toLocaleString('en-US', {hour: '2-digit', minute: '2-digit'})}`
                : 'Recent session';

            // ═══════════════════════════════════════════════════════════
            // BUILD THE EXPORT MARKDOWN
            // ═══════════════════════════════════════════════════════════

            let markdown = `# Code Review Request\n\n`;

            // Session Context
            markdown += `## Session Context\n\n`;
            if (dominantPhase) {
                const [phase, count] = dominantPhase;
                const pct = Math.round((count / fileDiffs.length) * 100);
                markdown += `**Dominant Phase:** ${phaseEmoji[phase] || '📝'} ${phase.charAt(0).toUpperCase() + phase.slice(1)} (${pct}% of changes)\n`;
            }
            if (sessionDuration) {
                markdown += `**Active Editing:** ${sessionDuration}\n`;
            }
            markdown += `**Time Range:** ${timeRange}\n\n`;

            // File Under Review
            markdown += `## File Under Review\n\n`;
            markdown += `### ${fileName}\n\n`;
            markdown += `| Property | Value |\n`;
            markdown += `|----------|-------|\n`;
            markdown += `| **Path** | \`${filePath}\` |\n`;
            markdown += `| **Language** | ${language} |\n`;
            markdown += `| **Changes** | ${fileDiffs.length} edit${fileDiffs.length > 1 ? 's' : ''} |\n\n`;

            // Related Files
            const relatedList = Object.entries(relatedFiles).slice(0, 5);
            if (relatedList.length > 0) {
                markdown += `### Related Files (same session)\n\n`;
                markdown += `| File | Edits | Relationship |\n`;
                markdown += `|------|-------|-------------|\n`;
                relatedList.forEach(([name, info]) => {
                    markdown += `| ${name} | ${info.edits} | ${info.relationship} |\n`;
                });
                markdown += `\n`;
            }

            // Work Timeline
            markdown += `## Work Timeline\n\n`;
            markdown += `| Time | Phase | Summary |\n`;
            markdown += `|------|-------|--------|\n`;
            fileDiffs.forEach((diff, idx) => {
                const ts = diff.timestamp
                    ? new Date(diff.timestamp).toLocaleString('en-US', { hour: '2-digit', minute: '2-digit' })
                    : `Edit ${idx + 1}`;
                const phase = getPhaseForTimestamp(diff.timestamp);
                const phaseStr = phase
                    ? `${phaseEmoji[phase.intent] || '📝'} ${phase.intent}`
                    : '—';
                // Create a brief summary from the diff
                const addedLines = splitLines(diff.new).filter(l => l.trim()).length;
                const removedLines = splitLines(diff.old).filter(l => l.trim()).length;
                const summary = `+${addedLines}/-${removedLines} lines`;
                markdown += `| ${ts} | ${phaseStr} | ${summary} |\n`;
            });
            markdown += `\n`;

            // The Changes
            markdown += `## The Changes\n\n`;
            fileDiffs.forEach((diff, idx) => {
                const ts = diff.timestamp
                    ? new Date(diff.timestamp).toLocaleString('en-US', {
                        month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit'
                    })
                    : `Change ${idx + 1}`;
                const phase = getPhaseForTimestamp(diff.timestamp);
                const phaseStr = phase
                    ? ` (${phase.intent})`
                    : '';

                markdown += `### Edit ${idx + 1} of ${fileDiffs.length} — ${ts}${phaseStr}\n\n`;

                if (diff.truncated) {
                    markdown += `> ⚠️ *This diff was truncated (original exceeded 2000 chars)*\n\n`;
                }

                markdown += '```diff\n';

                // Add removed lines
                const oldLines = splitLines(diff.old).filter(l => l.trim());
                oldLines.forEach(line => {
                    markdown += `- ${line}\n`;
                });

                // Add added lines
                const newLines = splitLines(diff.new).filter(l => l.trim());
                newLines.forEach(line => {
                    markdown += `+ ${line}\n`;
                });

                markdown += '```\n\n';
            });

            // Questions for Review
            markdown += `## For Your Review\n\n`;
            markdown += `### Questions\n\n`;
            markdown += `1. Are there any bugs or potential issues in these changes?\n`;
            markdown += `2. Is this the right approach, or is there a simpler solution?\n`;
            markdown += `3. Are there edge cases that might not be handled?\n`;
            markdown += `4. How could this code be improved?\n\n`;

            // Additional context hint
            if (dominantPhase && dominantPhase[0] === 'debugging') {
                markdown += `### Note\n`;
                markdown += `This was primarily a **debugging session** — focus on whether the fix addresses the root cause.\n\n`;
            } else if (dominantPhase && dominantPhase[0] === 'building') {
                markdown += `### Note\n`;
                markdown += `This was primarily a **building session** — focus on architecture and design decisions.\n\n`;
            }

            markdown += `---\n`;
            markdown += `*Exported from [Proof Visualizer](http://localhost:8080) — paste into any LLM for analysis*\n`;

            // Copy to clipboard
            navigator.clipboard.writeText(markdown).then(() => {
                showToast(`Copied ${fileDiffs.length} change${fileDiffs.length > 1 ? 's' : ''} for ${fileName}`, 'success');
            }).catch(err => {
                // Fallback for older browsers
                const textarea = document.createElement('textarea');
                textarea.value = markdown;
                document.body.appendChild(textarea);
                textarea.select();
                document.execCommand('copy');
                document.body.removeChild(textarea);
                showToast(`Copied ${fileDiffs.length} change${fileDiffs.length > 1 ? 's' : ''} for ${fileName}`, 'success');
            });
        }

        // Toast notification
        function showToast(message, type = 'info') {
            // Remove existing toast
            const existing = document.querySelector('.export-toast');
            if (existing) existing.remove();

            const toast = document.createElement('div');
            toast.className = 'export-toast';
            toast.innerHTML = `<span class="toast-icon">${type === 'success' ? '✓' : type === 'warning' ? '⚠' : 'ℹ'}</span> ${message}`;
            toast.style.cssText = `
                position: fixed;
                bottom: 20px;
                left: 50%;
                transform: translateX(-50%);
                background: ${type === 'success' ? '#238636' : type === 'warning' ? '#9e6a03' : '#1f6feb'};
                color: white;
                padding: 12px 20px;
                border-radius: 8px;
                font-size: 13px;
                font-weight: 500;
                z-index: 9999;
                box-shadow: 0 4px 12px rgba(0,0,0,0.3);
                animation: toastIn 0.3s ease;
            `;
            document.body.appendChild(toast);

            setTimeout(() => {
                toast.style.animation = 'toastOut 0.3s ease';
                setTimeout(() => toast.remove(), 300);
            }, 2500);
        }

        // Add toast animation styles
        (function() {
            const style = document.createElement('style');
            style.textContent = `
                @keyframes toastIn { from { opacity: 0; transform: translateX(-50%) translateY(20px); } to { opacity: 1; transform: translateX(-50%) translateY(0); } }
                @keyframes toastOut { from { opacity: 1; transform: translateX(-50%) translateY(0); } to { opacity: 0; transform: translateX(-50%) translateY(20px); } }
                .toast-icon { margin-right: 8px; }
            `;
            document.head.appendChild(style);
        })();

        // Initialize diff label click handler + keyboard shortcuts
        (function() {
            const diffLabel = document.querySelector('.insight-diff-label');
            if (diffLabel) {
                diffLabel.addEventListener('click', toggleDiffFocus);
            }

            // Keyboard shortcuts when insight card is visible
            document.addEventListener('keydown', (e) => {
                const card = document.getElementById('insight-card');
                if (!card || !card.classList.contains('visible')) return;
                if (e.target.matches('input, textarea')) return;

                // D key toggles diff focus
                if (e.key === 'd' || e.key === 'D') {
                    e.preventDefault();
                    toggleDiffFocus();
                }
                // E key exports diff for LLM
                if (e.key === 'e' || e.key === 'E') {
                    e.preventDefault();
                    exportDiffForLLM();
                }
                // Escape exits diff focus mode
                if (e.key === 'Escape' && card.classList.contains('diff-focused')) {
                    e.preventDefault();
                    card.classList.remove('diff-focused');
                }
            });
        })();

        // Expand/collapse diff view
        function toggleDiffExpand(btn, fileName) {
            const diffContent = document.getElementById("insight-diff-content");
            const isExpanded = btn.textContent.startsWith('Collapse');

            if (isExpanded) {
                // Collapse back to preview
                btn.closest('.diff-entry').querySelector('.diff-full')?.remove();
                btn.textContent = btn.dataset.originalText || 'Expand diff';
                diffContent.style.maxHeight = '120px';
            } else {
                // Find all diffs for this file
                const fileDiffs = [];
                Object.entries(diffCache).forEach(([path, diffs]) => {
                    if (path.endsWith(fileName) || path.endsWith('/' + fileName)) {
                        diffs.forEach(diff => fileDiffs.push({ ...diff, filePath: path }));
                    }
                });

                // Build expanded view with all diffs
                let expandedHtml = '<div class="diff-full">';
                fileDiffs.forEach((diff, idx) => {
                    const ts = diff.timestamp ? new Date(diff.timestamp).toLocaleString('en-US', {
                        month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit'
                    }) : 'Change ' + (idx + 1);

                    expandedHtml += `<div class="diff-entry"><div class="diff-timestamp">🕐 ${ts}</div>`;

                    // Show all lines (not truncated)
                    splitLines(diff.old).forEach(line => {
                        if (line.trim()) {
                            const escaped = line.replace(/</g, '&lt;').replace(/>/g, '&gt;');
                            expandedHtml += `<div class="diff-line removed">${escaped}</div>`;
                        }
                    });
                    splitLines(diff.new).forEach(line => {
                        if (line.trim()) {
                            const escaped = line.replace(/</g, '&lt;').replace(/>/g, '&gt;');
                            expandedHtml += `<div class="diff-line added">${escaped}</div>`;
                        }
                    });
                    expandedHtml += '</div>';
                });
                expandedHtml += '</div>';

                // Insert expanded content
                const entry = btn.closest('.diff-entry');
                entry.insertAdjacentHTML('beforeend', expandedHtml);

                // Update button
                btn.dataset.originalText = btn.textContent;
                btn.textContent = 'Collapse';
                diffContent.style.maxHeight = '300px';
            }
        }

        // Insight Card Drag Handling
        (function() {
            const card = document.getElementById('insight-card');
            if (!card) return;
            const header = card.querySelector('.insight-card-header');
            if (!header) return;
            let isDragging = false;
            let startX, startY, startLeft, startTop;

            header.addEventListener('mousedown', (e) => {
                if (e.target.closest('.insight-card-close')) return; // Don't drag when clicking close
                isDragging = true;
                card.classList.add('dragging');
                startX = e.clientX;
                startY = e.clientY;
                startLeft = card.offsetLeft;
                startTop = card.offsetTop;
                e.preventDefault();
            });

            document.addEventListener('mousemove', (e) => {
                if (!isDragging) return;
                const dx = e.clientX - startX;
                const dy = e.clientY - startY;
                let newLeft = startLeft + dx;
                let newTop = startTop + dy;
                // Keep on screen
                newLeft = Math.max(0, Math.min(newLeft, window.innerWidth - 100));
                newTop = Math.max(0, Math.min(newTop, window.innerHeight - 50));
                card.style.left = newLeft + 'px';
                card.style.top = newTop + 'px';
            });

            document.addEventListener('mouseup', () => {
                if (isDragging) {
                    isDragging = false;
                    card.classList.remove('dragging');
                    // Save position
                    localStorage.setItem('insightCardPosition', JSON.stringify({
                        left: card.style.left,
                        top: card.style.top
                    }));
                }
            });

            // Restore saved position
            const savedPosition = localStorage.getItem('insightCardPosition');
            if (savedPosition) {
                const pos = JSON.parse(savedPosition);
                if (pos.left) card.style.left = pos.left;
                if (pos.top) card.style.top = pos.top;
            }

            // Observe resize and persist card size
            const resizeObserver = new ResizeObserver((entries) => {
                for (const entry of entries) {
                    const { width, height } = entry.contentRect;
                    if (width > 0 && height > 0) {
                        localStorage.setItem('insightCardSize', JSON.stringify({ width, height }));
                    }
                }
            });
            resizeObserver.observe(card);

            // Restore saved size
            const savedSize = localStorage.getItem('insightCardSize');
            if (savedSize) {
                const size = JSON.parse(savedSize);
                if (size.width) card.style.width = size.width + 'px';
                if (size.height) card.style.height = size.height + 'px';
            }
        })();

        function renderSparkline(d) {
            const svg = document.getElementById("insight-sparkline");
            // Clear previous
            svg.querySelectorAll('path').forEach(p => p.remove());

            if (!d.timestamps || d.timestamps.length < 2) {
                return;
            }

            const width = svg.clientWidth || 308;
            const height = 32;
            const padding = 2;

            // Group timestamps by hour buckets
            const buckets = {};
            d.timestamps.forEach(ts => {
                const hour = ts.substring(0, 13); // YYYY-MM-DDTHH
                buckets[hour] = (buckets[hour] || 0) + 1;
            });

            const sortedKeys = Object.keys(buckets).sort();
            if (sortedKeys.length < 2) return;

            const values = sortedKeys.map(k => buckets[k]);
            const maxVal = Math.max(...values);

            // Create path
            const xScale = (width - padding * 2) / (values.length - 1);
            const yScale = (height - padding * 2) / (maxVal || 1);

            let pathD = '';
            let areaD = `M ${padding} ${height - padding} `;

            values.forEach((v, i) => {
                const x = padding + i * xScale;
                const y = height - padding - v * yScale;
                if (i === 0) {
                    pathD = `M ${x} ${y}`;
                    areaD += `L ${x} ${y} `;
                } else {
                    pathD += ` L ${x} ${y}`;
                    areaD += `L ${x} ${y} `;
                }
            });
            areaD += `L ${padding + (values.length - 1) * xScale} ${height - padding} Z`;

            // Add area fill
            const area = document.createElementNS("http://www.w3.org/2000/svg", "path");
            area.setAttribute("d", areaD);
            area.setAttribute("class", "insight-sparkline-area");
            svg.appendChild(area);

            // Add line
            const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
            path.setAttribute("d", pathD);
            path.setAttribute("class", "insight-sparkline-path");
            svg.appendChild(path);
        }

        function generateInsight(d, actions) {
            const name = d.id.split(":")[1];
            const total = d.count || 0;
            const reads = actions.read || 0;
            const edits = actions.edit || 0;
            const runs = actions.run || 0;
            const fails = actions.fail || 0;

            // Find top files by count for comparison
            const maxFileCount = Math.max(...graphData.nodes.filter(n => n.type === 'file').map(n => n.count));
            const avgFileCount = graphData.nodes.filter(n => n.type === 'file').reduce((a, n) => a + n.count, 0) / graphData.nodes.filter(n => n.type === 'file').length;

            if (d.type === 'tool') {
                if (total > avgFileCount * 2) {
                    return `Your most-used tool. ${edits > reads ? 'Primarily for making changes.' : 'Primarily for exploration.'}`;
                }
                return `Standard ${name.toLowerCase()} usage patterns.`;
            }

            // File insights
            if (fails > 0) {
                return `⚠️ Had ${fails} failure${fails > 1 ? 's' : ''}. Consider adding error handling or tests.`;
            }

            if (total === maxFileCount) {
                return `🔥 Your most-touched file (${total} interactions). Central to this session's work.`;
            }

            const editRatio = edits / (total || 1);
            const readRatio = reads / (total || 1);

            if (editRatio > 0.7 && reads < 3) {
                return `High edit/read ratio (${Math.round(editRatio * 100)}% edits). Consider reading more before changes.`;
            }

            if (readRatio > 0.8) {
                return `Mostly exploration (${reads} reads). You're learning this area of the codebase.`;
            }

            if (edits > 10 && reads > 5) {
                return `Active development: ${edits} edits with ${reads} reads. Good exploration-to-change balance.`;
            }

            if (total > avgFileCount * 1.5) {
                return `Frequently touched (${Math.round((total / avgFileCount) * 100 - 100)}% above average). Key file in your workflow.`;
            }

            return `${edits} edit${edits !== 1 ? 's' : ''}, ${reads} read${reads !== 1 ? 's' : ''}. ${d.dir ? 'Part of ' + d.dir + '/ module.' : ''}`;
        }

        document.addEventListener("click", (e) => {
            if (!e.target.closest(".detail-panel") && !e.target.closest(".node") && !e.target.closest(".explorer-node") && !e.target.closest(".insight-card")) {
                closeDetail();
                closeInsightCard();
            }
        });

        // Controls
        function resetZoom() {
            svg.transition().duration(500).call(zoom.transform, d3.zoomIdentity);
        }
        function resetLayout() {
            // Clear saved positions
            localStorage.removeItem('nodePositions');

            // Apply Cluster Islands positioning (Story Mode)
            const nodeGroups = {};
            graphData.nodes.forEach(n => {
                n.fx = null;
                n.fy = null;
                if (n.type === 'tool' || n.id.startsWith('tool:')) {
                    n.group = '__tools__';
                    nodeGroups['__tools__'] = nodeGroups['__tools__'] || [];
                    nodeGroups['__tools__'].push(n);
                } else {
                    const dir = n.dir || 'root';
                    n.group = dir;
                    nodeGroups[dir] = nodeGroups[dir] || [];
                    nodeGroups[dir].push(n);
                }
            });

            const groupNames = Object.keys(nodeGroups).sort((a, b) => {
                if (a === '__tools__') return -1;
                if (b === '__tools__') return 1;
                return nodeGroups[b].length - nodeGroups[a].length;
            });

            const numGroups = groupNames.length;
            const ringRadius = Math.min(width, height) * 0.32;
            const centerX = width / 2;
            const centerY = height / 2;
            const zoneRadius = 70;

            groupNames.forEach((groupName, i) => {
                const angle = (2 * Math.PI * i / numGroups) - Math.PI / 2;
                const groupCenterX = centerX + ringRadius * Math.cos(angle);
                const groupCenterY = centerY + ringRadius * Math.sin(angle);

                nodeGroups[groupName].forEach(n => {
                    const offsetAngle = Math.random() * 2 * Math.PI;
                    const offsetRadius = Math.random() * zoneRadius;
                    n.x = groupCenterX + offsetRadius * Math.cos(offsetAngle);
                    n.y = groupCenterY + offsetRadius * Math.sin(offsetAngle);
                });
            });

            debugLog(`Reset Layout: ${numGroups} groups positioned in ring`);

            // Restart simulation from new positions
            simulation.alpha(1).restart();
        }
        function toggleFullscreen() {
            const container = document.getElementById("graph-container");
            container.classList.toggle("fullscreen");
            setTimeout(() => {
                // Update Story Mode
                width = document.getElementById("graph-wrapper").clientWidth;
                height = document.getElementById("graph-wrapper").clientHeight;
                svg.attr("width", width).attr("height", height);
                simulation.force("center", d3.forceCenter(width / 2, height / 2));
                simulation.alpha(0.3).restart();

                // Update Explorer Mode if initialized
                if (window.explorerSimulation && window.explorerSvg) {
                    const eContainer = document.getElementById('explorer-wrapper');
                    const eWidth = eContainer.clientWidth;
                    const eHeight = eContainer.clientHeight || 600;
                    window.explorerSvg.attr('width', eWidth).attr('height', eHeight);
                    window.explorerSimulation.force('center', d3.forceCenter(eWidth / 2, eHeight / 2));
                    window.explorerSimulation.alpha(0.5).restart();
                }
            }, 100);
        }

        // Insight highlighting
        let activeInsight = null;
        function highlightInsight(el) {
            // Toggle active state
            const wasActive = el.classList.contains('active');
            document.querySelectorAll('.insight').forEach(i => i.classList.remove('active'));
            node.classed('highlighted', false).classed('dimmed', false);

            if (wasActive) {
                activeInsight = null;
                return;
            }

            el.classList.add('active');
            const nodeId = el.dataset.node;
            const cluster = el.dataset.cluster;

            if (nodeId) {
                // Highlight specific node
                node.classed('dimmed', true);
                node.filter(d => d.id === nodeId).classed('highlighted', true).classed('dimmed', false);
                // Also highlight connected nodes
                graphData.edges.forEach(e => {
                    if (e.source.id === nodeId || e.target.id === nodeId) {
                        const otherId = e.source.id === nodeId ? e.target.id : e.source.id;
                        node.filter(d => d.id === otherId).classed('dimmed', false);
                    }
                });
                activeInsight = nodeId;
            } else if (cluster) {
                // Highlight cluster
                node.classed('dimmed', true);
                node.filter(d => d.dir === cluster).classed('highlighted', true).classed('dimmed', false);
                activeInsight = cluster;
            }
        }

        // Heatmap modes
        let currentHeatmap = 'default';
        const recencyScale = d3.scaleSequential(d3.interpolateRdYlGn).domain([48, 0]);  // Red=old, Green=recent
        const frequencyScale = d3.scaleSequential(d3.interpolateYlOrRd).domain([1, maxCount]);  // Yellow=low, Red=high

        function setHeatmap(mode) {
            debugLog('setHeatmap called with mode:', mode);
            currentHeatmap = mode;
            document.querySelectorAll('.heatmap-controls button').forEach(b => b.classList.remove('active'));
            document.getElementById('hm-' + mode).classList.add('active');

            debugLog('window.storyNode:', window.storyNode);
            debugLog('maxCount:', maxCount);
            if (!window.storyNode) {
                debugLog('No storyNode, returning early');
                return;
            }
            window.storyNode.each(function(d) {
                const el = d3.select(this);
                const nodeData = d.data || d;

                // Find the shape element using unified class
                let shape = el.select('.node-shape');
                if (shape.empty()) {
                    // Fallback for direct shape elements
                    const tagName = el.node()?.tagName?.toLowerCase();
                    if (tagName === 'circle' || tagName === 'rect' || tagName === 'path') {
                        shape = el;
                    }
                }
                if (shape.empty()) return;

                debugLog('Node:', nodeData.id, 'count:', nodeData.count, 'recency:', nodeData.recency);
                if (nodeData.type === 'tool') {
                    // Tools keep CSS color; no inline override.
                    shape.style('fill', null);
                    return;
                }

                let fillColor = null;
                if (mode === 'recency') {
                    const hours = nodeData.recency || 0;
                    fillColor = recencyScale(Math.min(hours, 48));
                } else if (mode === 'frequency') {
                    fillColor = frequencyScale(nodeData.count || 1);
                    debugLog('Frequency color for', nodeData.id, ':', fillColor);
                }

                if (fillColor) {
                    shape.style('fill', fillColor, 'important');
                } else {
                    // Clear inline style, let CSS apply
                    shape.style('fill', null);
                }
            });

            // Update legend
            const legend = document.getElementById('heatmap-legend');
            const legendBar = document.getElementById('legend-bar');
            const legendTitle = document.getElementById('legend-title');
            const legendLeft = document.getElementById('legend-left');
            const legendRight = document.getElementById('legend-right');
            if (mode === 'recency') {
                legend.classList.add('visible');
                legendBar.className = 'legend-bar legend-recency';
                legendTitle.textContent = 'Recency';
                legendLeft.textContent = 'Stale (48h+)';
                legendRight.textContent = 'Recent';
            } else if (mode === 'frequency') {
                legend.classList.add('visible');
                legendBar.className = 'legend-bar legend-frequency';
                legendTitle.textContent = 'Frequency';
                legendLeft.textContent = 'Few';
                legendRight.textContent = 'Many';
            } else {
                legend.classList.remove('visible');
            }
        }

        // Search functionality
        // ═══════════════════════════════════════════════════════════
        // CONSTELLATION MODE: Search Promotes Matches (Story)
        // Typing instantly makes matching nodes become "bright"
        // ═══════════════════════════════════════════════════════════

        const storySearchTierOpacity = { star: 1.0, context: 0.3, dark: 0.08 };

        function handleSearch(event) {
            const query = event.target.value.toLowerCase().trim();

            if (!query) {
                clearSearch();
                return;
            }

            // Mark matching nodes as search matches
            graphData.nodes.forEach(d => {
                const name = d.id.split(':')[1].toLowerCase();
                const dir = (d.dir || '').toLowerCase();
                const path = (d.path || '').toLowerCase();
                d.isSearchMatch = name.includes(query) || dir.includes(query) || path.includes(query);
            });

            // Reveal All locks opacity but NOT glow/filter effects
            const lockOpacity = typeof revealAllEnabled !== 'undefined' && revealAllEnabled;

            // Update visuals - search matches get glow; opacity depends on revealAll state
            node.select('circle')
                .style('opacity', d => lockOpacity ? 1.0 : (d.isSearchMatch ? 1.0 : storySearchTierOpacity[d.tier] || 0.08))
                .style('filter', d => (d.tier === 'star' || d.isSearchMatch) ? 'drop-shadow(0 0 6px currentColor)' : 'none');

            node.select('text')
                .style('opacity', d => lockOpacity ? 1.0 : ((d.tier === 'star' || d.isSearchMatch) ? 1.0 : 0));

            // Keep legacy class behavior for CSS styling
            node.classed('highlighted', d => d.isSearchMatch);
        }

        function clearSearch() {
            document.getElementById('search-input').value = '';
            graphData.nodes.forEach(d => d.isSearchMatch = false);

            // Reveal All locks opacity but clears glow/filter
            const lockOpacity = typeof revealAllEnabled !== 'undefined' && revealAllEnabled;

            // Reset to tier-based opacity (or locked if Reveal All)
            node.select('circle')
                .style('opacity', d => lockOpacity ? 1.0 : storySearchTierOpacity[d.tier] || 0.08)
                .style('filter', d => d.tier === 'star' ? 'drop-shadow(0 0 6px currentColor)' : 'none');

            node.select('text')
                .style('opacity', d => lockOpacity ? 1.0 : (d.tier === 'star' ? 1.0 : 0));

            node.classed('dimmed', false).classed('highlighted', false);
            document.querySelectorAll('.insight').forEach(i => i.classList.remove('active'));
        }

        // Anomaly detection - mark nodes > 3σ above mean
        const counts = graphData.nodes.map(n => n.count);
        const mean = counts.reduce((a, b) => a + b, 0) / counts.length;
        const stdDev = Math.sqrt(counts.map(c => Math.pow(c - mean, 2)).reduce((a, b) => a + b, 0) / counts.length);
        const threshold = mean + 3 * stdDev;
        node.filter(d => d.count > threshold).classed('anomaly', true);

        // Export functions
        function toggleExportMenu() {
            document.getElementById('export-dropdown').classList.toggle('visible');
        }
        document.addEventListener('click', (e) => {
            if (!e.target.closest('.export-menu')) {
                document.getElementById('export-dropdown').classList.remove('visible');
            }
        });

        function exportPNG() {
            const svgElement = document.getElementById('graph');
            const svgData = new XMLSerializer().serializeToString(svgElement);
            const canvas = document.createElement('canvas');
            canvas.width = width * 2;
            canvas.height = height * 2;
            const ctx = canvas.getContext('2d');
            ctx.fillStyle = '#0d1117';
            ctx.fillRect(0, 0, canvas.width, canvas.height);
            const img = new Image();
            img.onload = () => {
                ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
                const link = document.createElement('a');
                link.download = 'proof-graph.png';
                link.href = canvas.toDataURL('image/png');
                link.click();
            };
            img.src = 'data:image/svg+xml;base64,' + btoa(unescape(encodeURIComponent(svgData)));
            document.getElementById('export-dropdown').classList.remove('visible');
        }

        function exportLayout() {
            // Collect positions from both Story and Explorer modes
            const layout = { story: {}, explorer: {} };
            graphData.nodes.forEach(n => {
                if (n.x !== undefined && n.y !== undefined) {
                    layout.story[n.id] = { x: n.x, y: n.y };
                }
            });
            if (explorerData && explorerData.nodes) {
                explorerData.nodes.forEach(n => {
                    if (n.x !== undefined && n.y !== undefined) {
                        layout.explorer[n.id] = { x: n.x, y: n.y };
                    }
                });
            }
            const blob = new Blob([JSON.stringify(layout, null, 2)], { type: 'application/json' });
            const link = document.createElement('a');
            link.download = 'layout.json';
            link.href = URL.createObjectURL(blob);
            link.click();
            document.getElementById('export-dropdown').classList.remove('visible');
            // Show hint to move file
            alert('Layout saved! Move layout.json to .proof/layout.json to persist across regenerations.');
        }

        function exportMarkdown() {
            const insightsData = window.PROOFVIZ_DATA.insights;
            const beginnerData = window.PROOFVIZ_DATA.beginner;
            const stats = window.PROOFVIZ_DATA.stats;
            const summary = window.PROOFVIZ_DATA.summary || '';

            let md = '# Claude Session Analysis Report\\n\\n';
            md += '> This report is formatted for LLM analysis. Copy and paste to any AI for deeper review.\\n\\n';

            // Quick Assessment
            md += '## Quick Assessment\\n\\n';
            md += '| Metric | Value | Status |\\n';
            md += '|--------|-------|--------|\\n';
            md += '| Health Score | ' + beginnerData.health_score + '% | ' + beginnerData.status_emoji + ' ' + beginnerData.status_text + ' |\\n';
            md += '| Success Rate | ' + stats.success_rate + ' | ' + (parseFloat(stats.success_rate) >= 95 ? "Good" : "Review") + ' |\\n';
            md += '| CTI (Traceability) | ' + stats.cti + ' | ' + (parseFloat(stats.cti) >= 70 ? "Good" : "Low") + ' |\\n';
            md += '| Total Operations | ' + stats.total_events + ' | - |\\n';
            md += '| Failed Operations | ' + stats.failures + ' | ' + (stats.failures <= 5 ? "Good" : "Check") + ' |\\n\\n';

            // What Happened
            md += '## Session Summary\\n\\n';
            md += summary + '\\n\\n';
            md += '**Actions**: ' + beginnerData.what_happened + '\\n\\n';

            // Key Files
            md += '## Key Files (by activity)\\n\\n';
            md += '| Rank | File | Touches | Directory |\\n';
            md += '|------|------|---------|-----------|\\n';
            graphData.nodes.filter(n => n.type === 'file').sort((a, b) => b.count - a.count).slice(0, 10).forEach((n, i) => {
                md += '| ' + (i+1) + ' | ' + n.id.split(':')[1] + ' | ' + n.count + ' | ' + (n.dir || '-') + ' |\\n';
            });
            md += '\\n';

            // Tool Usage
            md += '## Tool Usage\\n\\n';
            const tools = graphData.nodes.filter(n => n.type === 'tool').sort((a, b) => b.count - a.count);
            md += '| Tool | Count | % of Total |\\n';
            md += '|------|-------|------------|\\n';
            tools.forEach(t => {
                const pct = (t.count / stats.total_events * 100).toFixed(1);
                md += '| ' + t.id.split(':')[1] + ' | ' + t.count + ' | ' + pct + '% |\\n';
            });
            md += '\\n';

            // Insights
            md += '## Automated Insights\\n\\n';
            if (insightsData.length > 0) {
                insightsData.forEach(i => { md += '- **' + i.title + '**: ' + i.detail + '\\n'; });
            } else {
                md += '_No notable patterns detected._\\n';
            }
            md += '\\n';

            // Tips
            md += '## Recommendations\\n\\n';
            beginnerData.tips.forEach(tip => { md += '- ' + tip + '\\n'; });
            md += '\\n';

            // LLM Analysis Prompts
            md += '---\\n\\n';
            md += '## Suggested Analysis Questions\\n\\n';
            md += 'Use these prompts to get deeper analysis from an LLM:\\n\\n';
            md += '1. **Pattern Analysis**: "Based on the tool usage and file activity, what kind of work was being done? Was it debugging, feature development, refactoring, or exploration?"\\n\\n';
            md += '2. **Risk Assessment**: "Given the success/failure ratio and file changes, are there any potential risks or areas that need more testing?"\\n\\n';
            md += '3. **Efficiency Review**: "Looking at the number of touches per file, was the session efficient or were there signs of trial-and-error or confusion?"\\n\\n';
            md += '4. **Improvement Suggestions**: "What could be improved in the next session based on this activity pattern?"\\n\\n';

            // Raw data for LLM
            md += '---\\n\\n';
            md += '## Raw Data (for LLM parsing)\\n\\n';
            md += '```json\\n';
            md += JSON.stringify({
                stats: {
                    total: stats.total_events,
                    successes: stats.successes,
                    failures: stats.failures,
                    success_rate: stats.success_rate,
                    cti: stats.cti
                },
                health: beginnerData,
                top_files: graphData.nodes.filter(n => n.type === 'file').sort((a,b) => b.count - a.count).slice(0,10).map(n => ({ name: n.id.split(':')[1], count: n.count, dir: n.dir })),
                tools: tools.map(t => ({ name: t.id.split(':')[1], count: t.count }))
            }, null, 2);
            md += '\\n```\\n';

            const blob = new Blob([md], { type: 'text/markdown' });
            const link = document.createElement('a');
            link.download = 'proof-report.md';
            link.href = URL.createObjectURL(blob);
            link.click();
            document.getElementById('export-dropdown').classList.remove('visible');
        }

        // Handle resize
        window.addEventListener("resize", () => {
            width = container.clientWidth;
            height = container.clientHeight;
            svg.attr("width", width).attr("height", height);
        });

        // Toggle advanced view
        function toggleAdvanced() {
            const adv = document.getElementById('advanced-view');
            const btn = document.querySelector('.qv-toggle');
            if (adv.classList.contains('collapsed')) {
                adv.classList.remove('collapsed');
                btn.textContent = 'Hide Advanced Details';
            } else {
                adv.classList.add('collapsed');
                btn.textContent = 'Show Advanced Details';
            }
        }

        // ===== STORY MODE =====
        const phasesData = window.PROOFVIZ_DATA.phases;
        const timelineData = window.PROOFVIZ_DATA.timeline;
        const totalEvents = timelineData.length;
        let currentPosition = 0;
        let isPlaying = false;
        let playInterval = null;
        let playSpeed = 100;

        // Phase icons
        const phaseIcons = {
            exploring: '🔍',
            building: '🔨',
            debugging: '🐛',
            executing: '⚡',
            mixed: '📦'
        };

        // Build phase segments for both main and fullscreen timelines
        function buildPhaseSegments() {
            const containers = [
                document.getElementById('timeline-phases'),
                document.getElementById('fs-timeline-phases')
            ];
            if (!phasesData.length || !totalEvents) return;

            containers.forEach(container => {
                if (!container) return;
                container.innerHTML = '';
                phasesData.forEach((phase, i) => {
                    const width = ((phase.end - phase.start + 1) / totalEvents) * 100;
                    const segment = document.createElement('div');
                    segment.className = `phase-segment ${phase.intent}`;
                    segment.style.width = `${width}%`;
                    segment.onclick = () => jumpToPosition(phase.start);
                    segment.title = `${phase.intent} (${phase.count} ops)`;

                    if (width > 8) {
                        const label = document.createElement('span');
                        label.className = 'phase-label';
                        label.textContent = phase.intent;
                        segment.appendChild(label);
                    }

                    container.appendChild(segment);
                });
            });
        }

        // Update scrubber position (syncs both main and fullscreen views)
        function updateScrubber(position) {
            const pct = (position / totalEvents) * 100;

            // Update both main and fullscreen scrubbers
            document.getElementById('scrubber-handle').style.left = `${pct}%`;
            const fsHandle = document.getElementById('fs-scrubber-handle');
            if (fsHandle) fsHandle.style.left = `${pct}%`;

            // Update both position displays
            const posText = `Event ${position} of ${totalEvents}`;
            document.getElementById('current-position').textContent = posText;
            const fsPos = document.getElementById('fs-current-position');
            if (fsPos) fsPos.textContent = posText;

            // Find current phase
            const currentPhase = phasesData.find(p => position >= p.start && position <= p.end);
            if (currentPhase) {
                const icon = phaseIcons[currentPhase.intent] || '📦';
                const phaseText = `${icon} ${currentPhase.intent}`;
                document.getElementById('current-phase').textContent = phaseText;
                const fsPhase = document.getElementById('fs-current-phase');
                if (fsPhase) fsPhase.textContent = phaseText;
                updateNarrative(position, currentPhase);
            }

            // Update graph visibility
            updateGraphVisibility(position);
        }

        // Update narrative text (syncs both main and fullscreen)
        function updateNarrative(position, phase) {
            const icon = phaseIcons[phase.intent] || '📦';

            // Get current event
            const event = timelineData[position];
            if (!event) return;

            // Find phase index
            const phaseIndex = phasesData.findIndex(p => p.start === phase.start);
            const phaseNum = phaseIndex >= 0 ? phaseIndex + 1 : '?';

            // Phase header with duration and CTI
            let text = `<span style="color:#8b949e;font-size:11px;">Phase ${phaseNum}/${phasesData.length}`;
            if (phase.duration_formatted) {
                text += ` · ${phase.duration_formatted}`;
            }
            if (phase.cti !== undefined) {
                const ctiColor = phase.cti >= 70 ? '#3fb950' : phase.cti >= 50 ? '#9e6a03' : '#da3633';
                text += ` · <span style="color:${ctiColor}">CTI ${phase.cti}%</span>`;
            }
            text += `</span> `;

            text += `${icon} `;
            if (phase.intent === 'exploring') {
                text += `<strong>Exploring</strong>: Claude is reading files to understand the codebase`;
            } else if (phase.intent === 'building') {
                text += `<strong>Building</strong>: Claude is making changes to the code`;
            } else if (phase.intent === 'debugging') {
                text += `<strong>Debugging</strong>: Claude encountered an issue and is investigating`;
            } else if (phase.intent === 'executing') {
                text += `<strong>Executing</strong>: Claude is running commands`;
            } else {
                text += `<strong>Working</strong>: Claude is performing various operations`;
            }

            if (event.file) {
                text += ` → <span style="color:#7ee787;">${event.file}</span>`;
            }

            // Update both narratives
            document.getElementById('story-narrative').innerHTML = text;
            const fsNarrative = document.getElementById('fs-story-narrative');
            if (fsNarrative) fsNarrative.innerHTML = text;
        }

        // Track last action per node for coloring
        let nodeLastAction = {};
        let lastPosition = -1;

        // Update graph visibility and action coloring based on position
        function updateGraphVisibility(position) {
            const visibleFiles = new Set();
            const visibleTools = new Set();
            const justTouched = new Set();

            // Collect all files/tools up to position and track last action
            for (let i = 0; i <= position && i < timelineData.length; i++) {
                const event = timelineData[i];
                const toolId = 'tool:' + event.tool;
                visibleTools.add(toolId);
                nodeLastAction[toolId] = event.action || 'other';

                if (event.file) {
                    const fileId = 'file:' + event.file;
                    visibleFiles.add(fileId);
                    nodeLastAction[fileId] = event.action || 'other';

                    // Track nodes touched at current position for pulse
                    if (i === position) {
                        justTouched.add(toolId);
                        justTouched.add(fileId);
                    }
                }
            }

            // Action color map for inline styles (overrides heatmap)
            const actionColors = {
                read: { fill: '#58a6ff', stroke: '#388bfd' },
                edit: { fill: '#3fb950', stroke: '#2ea043' },
                run: { fill: '#f2cc60', stroke: '#d29922' },
                fail: { fill: '#f85149', stroke: '#da3633' },
                other: { fill: '#8b949e', stroke: '#6e7681' }
            };

            // Update node visibility and action coloring
            if (!window.storyNode) return;
            window.storyNode.each(function(d) {
                const el = d3.select(this);

                // Get the node ID - handle hierarchy data structures from alternate layouts
                const nodeId = d.data ? d.data.id : d.id;
                const nodeData = d.data || d;

                const isVisible = visibleFiles.has(nodeId) || visibleTools.has(nodeId);
                const action = nodeLastAction[nodeId] || 'other';

                // Find the shape element using unified class
                let shape = el.select('.node-shape');
                if (shape.empty()) {
                    // Fallback for direct shape elements
                    const tagName = el.node()?.tagName?.toLowerCase();
                    if (tagName === 'circle' || tagName === 'rect' || tagName === 'path') {
                        shape = el;
                    }
                }

                // Set opacity
                el.transition().duration(50).style('opacity', isVisible ? 1 : 0.15);

                // Apply colors based on heatmap mode (use .style to override CSS)
                if (isVisible && !shape.empty()) {
                    if (currentHeatmap === 'recency') {
                        const hours = nodeData.recency || 0;
                        shape.style('fill', recencyScale(Math.min(hours, 48))).style('stroke', '#30363d');
                    } else if (currentHeatmap === 'frequency') {
                        shape.style('fill', frequencyScale(nodeData.count || 1)).style('stroke', '#30363d');
                    } else {
                        // Default: action colors
                        const colors = actionColors[action] || actionColors.other;
                        shape.style('fill', colors.fill).style('stroke', colors.stroke);
                    }
                }

                // Pulse animation for just-touched nodes - shine bright then fade
                if (justTouched.has(nodeId) && position !== lastPosition) {
                    el.classed('just-touched', false);
                    // Force reflow to restart animation
                    void el.node().offsetWidth;
                    el.classed('just-touched', true);
                    // Remove class after animation completes (1.5s to match CSS)
                    setTimeout(() => el.classed('just-touched', false), 1500);
                }
            });

            // Update edge visibility
            if (window.storyLink) {
                window.storyLink.transition().duration(50)
                    .style('opacity', d => {
                        const sourceVisible = visibleFiles.has(d.source.id) || visibleTools.has(d.source.id);
                        const targetVisible = visibleFiles.has(d.target.id) || visibleTools.has(d.target.id);
                        return (sourceVisible && targetVisible) ? 0.6 : 0.1;
                    });
            }

            lastPosition = position;
        }

        // Playback controls (syncs both main and fullscreen)
        function togglePlay() {
            const btn = document.getElementById('play-btn');
            const fsBtn = document.getElementById('fs-play-btn');
            if (isPlaying) {
                isPlaying = false;
                clearInterval(playInterval);
                btn.textContent = '▶ Play';
                btn.classList.remove('active');
                if (fsBtn) {
                    fsBtn.textContent = '▶ Play';
                    fsBtn.classList.remove('active');
                }
            } else {
                isPlaying = true;
                btn.textContent = '⏸ Pause';
                btn.classList.add('active');
                if (fsBtn) {
                    fsBtn.textContent = '⏸ Pause';
                    fsBtn.classList.add('active');
                }
                playInterval = setInterval(() => {
                    if (currentPosition < totalEvents - 1) {
                        currentPosition++;
                        updateScrubber(currentPosition);
                    } else {
                        togglePlay(); // Stop at end
                    }
                }, playSpeed);
            }
        }

        function setSpeed(speed) {
            playSpeed = parseInt(speed);
            // Sync both speed selects
            document.getElementById('speed-select').value = speed;
            const fsSelect = document.getElementById('fs-speed-select');
            if (fsSelect) fsSelect.value = speed;

            if (isPlaying) {
                clearInterval(playInterval);
                playInterval = setInterval(() => {
                    if (currentPosition < totalEvents - 1) {
                        currentPosition++;
                        updateScrubber(currentPosition);
                    } else {
                        togglePlay();
                    }
                }, playSpeed);
            }
        }

        function jumpToStart() {
            currentPosition = 0;
            updateScrubber(currentPosition);
        }

        function jumpToEnd() {
            currentPosition = totalEvents - 1;
            updateScrubber(currentPosition);
        }

        function jumpToPosition(pos) {
            currentPosition = Math.max(0, Math.min(pos, totalEvents - 1));
            updateScrubber(currentPosition);
        }

        // Scrubber drag handling (supports both main and fullscreen)
        const scrubber = document.getElementById('timeline-scrubber');
        const handle = document.getElementById('scrubber-handle');
        const fsScrubber = document.getElementById('fs-timeline-scrubber');
        const fsHandle = document.getElementById('fs-scrubber-handle');
        let isDragging = false;
        let activeScrubber = null;

        function handleScrubberInteraction(e, targetScrubber) {
            const rect = targetScrubber.getBoundingClientRect();
            const x = (e.clientX || e.touches?.[0]?.clientX || 0) - rect.left;
            const pct = Math.max(0, Math.min(1, x / rect.width));
            currentPosition = Math.floor(pct * totalEvents);
            updateScrubber(currentPosition);
        }

        // Main scrubber events
        scrubber.addEventListener('click', (e) => handleScrubberInteraction(e, scrubber));
        handle.addEventListener('mousedown', () => { isDragging = true; activeScrubber = scrubber; });

        // Fullscreen scrubber events
        if (fsScrubber && fsHandle) {
            fsScrubber.addEventListener('click', (e) => handleScrubberInteraction(e, fsScrubber));
            fsHandle.addEventListener('mousedown', () => { isDragging = true; activeScrubber = fsScrubber; });
        }

        document.addEventListener('mousemove', (e) => {
            if (isDragging && activeScrubber) handleScrubberInteraction(e, activeScrubber);
        });
        document.addEventListener('mouseup', () => { isDragging = false; activeScrubber = null; });

        // Initialize Story Mode
        buildPhaseSegments();

        // Restore position from localStorage (survives refresh)
        const savedPosition = localStorage.getItem('storyModePosition');
        if (savedPosition && parseInt(savedPosition) < totalEvents) {
            currentPosition = parseInt(savedPosition);
        }
        updateScrubber(currentPosition);

        // Restore open Insight Card if any
        const savedInsightNode = localStorage.getItem('openInsightNode');
        if (savedInsightNode) {
            const nodeData = graphData.nodes.find(n => n.id === savedInsightNode);
            if (nodeData) {
                // Find the DOM element for this node
                setTimeout(() => {
                    const nodeEl = node.filter(n => n.id === savedInsightNode).node();
                    if (nodeEl) {
                        // Create synthetic event for positioning
                        const rect = nodeEl.querySelector('circle').getBoundingClientRect();
                        const syntheticEvent = {
                            stopPropagation: () => {},
                            target: { getBoundingClientRect: () => rect }
                        };
                        showInsightCard(syntheticEvent, nodeData);
                    }
                }, 100);
            }
        }

        // Save position on change
        function savePosition() {
            localStorage.setItem('storyModePosition', currentPosition.toString());
        }

        // Override updateScrubber to also save
        const originalUpdateScrubber = updateScrubber;
        updateScrubber = function(position) {
            originalUpdateScrubber(position);
            savePosition();
        };

        // Add reset button functionality
        function resetStoryMode() {
            localStorage.removeItem('storyModePosition');
            currentPosition = 0;
            originalUpdateScrubber(0);
        }

        // Keyboard navigation for phases
        document.addEventListener('keydown', (e) => {
            // Don't capture if user is typing in an input
            if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') return;

            switch (e.key) {
                case 'ArrowLeft':
                    // Previous phase
                    if (phasesData.length > 0) {
                        const currentPhase = phasesData.findIndex(p => currentPosition >= p.start && currentPosition <= p.end);
                        const prevPhaseIdx = Math.max(0, currentPhase - 1);
                        const prevPhase = phasesData[prevPhaseIdx];
                        if (prevPhase) {
                            jumpToPhase(prevPhase.start, prevPhaseIdx);
                        }
                    }
                    e.preventDefault();
                    break;
                case 'ArrowRight':
                    // Next phase
                    if (phasesData.length > 0) {
                        const currentPhase = phasesData.findIndex(p => currentPosition >= p.start && currentPosition <= p.end);
                        const nextPhaseIdx = Math.min(phasesData.length - 1, currentPhase + 1);
                        const nextPhase = phasesData[nextPhaseIdx];
                        if (nextPhase) {
                            jumpToPhase(nextPhase.start, nextPhaseIdx);
                        }
                    }
                    e.preventDefault();
                    break;
                case 'Escape':
                    // Close insight card
                    closeInsightCard();
                    break;
                case ' ':
                    // Space toggles play/pause
                    togglePlay();
                    e.preventDefault();
                    break;
            }
        });

        // Jump to phase with visual feedback
        function jumpToPhase(position, phaseIdx) {
            // Add transition class for fade effect
            const graphWrapper = document.getElementById('graph-wrapper');
            graphWrapper.classList.add('phase-transition');

            // Update position
            currentPosition = position;
            updateScrubber(position);
            document.getElementById('timeline-slider').value = position;
            const fsSlider = document.getElementById('fs-timeline-slider');
            if (fsSlider) fsSlider.value = position;

            // Show phase indicator toast
            const phase = phasesData[phaseIdx];
            if (phase) {
                showPhaseToast(phaseIdx + 1, phase.intent);
            }

            // Remove transition class after animation
            setTimeout(() => graphWrapper.classList.remove('phase-transition'), 300);
        }

        // Phase jump toast notification
        function showPhaseToast(phaseNum, intent) {
            let toast = document.getElementById('phase-toast');
            if (!toast) {
                toast = document.createElement('div');
                toast.id = 'phase-toast';
                toast.className = 'phase-toast';
                document.body.appendChild(toast);
            }
            const icons = { exploring: '🔍', building: '🔨', debugging: '🐛', executing: '⚡', mixed: '📋' };
            toast.innerHTML = `${icons[intent] || '📋'} Phase ${phaseNum} · ${intent}`;
            toast.classList.add('visible');
            setTimeout(() => toast.classList.remove('visible'), 1500);
        }

        // Mode toggle (Story ↔ Explorer) with fade transition
        // Toggle nebula/aura visibility (works for both Story and Explorer modes)
        let nebulaeVisible = true;
        function toggleAuras() {
            nebulaeVisible = !nebulaeVisible;
            // Toggle all aura layers (Story mode)
            document.querySelectorAll('.aura-layer').forEach(layer => {
                layer.style.display = nebulaeVisible ? 'block' : 'none';
            });
            // Toggle nebula layers (Explorer mode)
            document.querySelectorAll('.nebula-layer').forEach(layer => {
                layer.style.display = nebulaeVisible ? 'block' : 'none';
            });
            // Update all toggle buttons (Explorer, Story, Fullscreen Story)
            ['aura-toggle', 'story-aura-toggle', 'fs-aura-toggle'].forEach(id => {
                const btn = document.getElementById(id);
                if (btn) btn.classList.toggle('active', nebulaeVisible);
            });
        }

        // ═══════════════════════════════════════════════════════════
        // CONSTELLATION MODE: Reveal All Toggle
        // Power user feature to show all nodes at full opacity
        // ═══════════════════════════════════════════════════════════

        let revealAllEnabled = false;
        const revealTierOpacity = { star: 1.0, context: 0.3, dark: 0.08 };

        function toggleRevealAll() {
            revealAllEnabled = !revealAllEnabled;

            const toggleBtn = document.getElementById('reveal-all-toggle');
            if (toggleBtn) {
                toggleBtn.classList.toggle('active', revealAllEnabled);
                toggleBtn.textContent = revealAllEnabled ? '👁 Hide Dark' : '👁 Reveal All';
            }

            if (currentMode === 'story') {
                // Story mode - use window.storyNode with layout-aware shape detection
                if (window.storyNode) {
                    window.storyNode.each(function(d) {
                        const el = d3.select(this);
                        const nodeData = d.data || d;
                        const tier = nodeData.tier;

                        // Find shape element using unified class
                        let shape = el.select('.node-shape');
                        if (shape.empty()) {
                            const tagName = el.node()?.tagName?.toLowerCase();
                            if (tagName === 'circle' || tagName === 'rect' || tagName === 'path') {
                                shape = el;
                            }
                        }

                        if (!shape.empty()) {
                            shape.style('opacity', revealAllEnabled ? 1.0 : revealTierOpacity[tier] || 0.08)
                                .style('filter', (tier === 'star' || revealAllEnabled) ? 'drop-shadow(0 0 6px currentColor)' : 'none');
                        }

                        const text = el.select('text');
                        if (!text.empty()) {
                            text.style('opacity', (tier === 'star' || revealAllEnabled) ? 1.0 : 0);
                        }
                    });
                }
            } else {
                // Explorer mode - use window.explorerNodes
                if (window.explorerNodes) {
                    window.explorerNodes.select('circle')
                        .style('opacity', d => revealAllEnabled ? 1.0 : revealTierOpacity[d.tier] || 0.08)
                        .style('filter', d => {
                            if (d.tier === 'star' || revealAllEnabled) {
                                const extColors = { '.py': '#7ee787', '.yaml': '#f0883e', '.json': '#58a6ff', '.md': '#8b949e', '.sh': '#a371f7', '.js': '#f1e05a', '.html': '#e34c26', '.css': '#563d7c' };
                                return `drop-shadow(0 0 8px ${extColors[d.ext] || '#8b949e'})`;
                            }
                            return 'none';
                        });
                    window.explorerNodes.select('text')
                        .style('opacity', d => (d.tier === 'star' || revealAllEnabled) ? 1.0 : 0);
                }
            }
        }

        function setMode(mode) {
            currentMode = mode;
            document.getElementById('mode-story').classList.toggle('active', mode === 'story');
            document.getElementById('mode-explorer').classList.toggle('active', mode === 'explorer');

            // Toggle scene classes for fade transition
            document.getElementById('story-scene').classList.toggle('active', mode === 'story');
            document.getElementById('explorer-scene').classList.toggle('active', mode === 'explorer');

            // Toggle story-mode controls visibility
            const storyControls = document.getElementById('story-mode');
            if (storyControls) storyControls.style.display = mode === 'story' ? 'block' : 'none';

            // Toggle heat legend visibility
            const heatLegend = document.getElementById('heat-legend');
            if (heatLegend) heatLegend.style.display = mode === 'explorer' ? 'block' : 'none';

            if (mode === 'explorer' && explorerData) {
                renderLayout(currentLayout);
            }
        }

        // ═══════════════════════════════════════════════════════════
        // MULTI-LAYOUT SYSTEM - Switch between organized views
        // ═══════════════════════════════════════════════════════════

        let currentLayout = 'force';
        const layoutRendered = {};  // Track which layouts have been rendered

        function setLayout(layout) {
            currentLayout = layout;
            debugLog('Switching to layout:', layout);

            // Clear existing visualization
            const explorerSvg = d3.select('#explorer-graph');
            explorerSvg.selectAll('*').remove();

            // Reset render tracking for this layout
            layoutRendered[layout] = false;

            // Render the new layout
            renderLayout(layout);
        }

        // Story mode layout switcher
        let storyLayout = 'force';
        const storyLayoutRendered = {};

        function setStoryLayout(layout) {
            storyLayout = layout;
            debugLog('Switching Story layout to:', layout);

            // Pause playback if running
            if (isPlaying) togglePlay();

            // Save current position
            const currentPos = currentPosition;

            // Clear story SVG
            const storySvg = d3.select('#graph');
            storySvg.selectAll('*').remove();

            // Reset render tracking
            storyLayoutRendered[layout] = false;

            // Render the new layout
            renderStoryLayout(layout);

            // Restore position
            if (currentPos > 0) {
                jumpToPosition(currentPos);
            }
        }

        function renderStoryLayout(layout) {
            debugLog('Rendering Story layout:', layout);
            if (storyLayoutRendered[layout]) return;

            switch (layout) {
                case 'force':
                    renderStoryForceLayout();
                    break;
                case 'bundling':
                    renderStoryEdgeBundlingLayout();
                    break;
                case 'treemap':
                    renderStoryTreemapLayout();
                    break;
                case 'packing':
                    renderStoryCirclePackingLayout();
                    break;
                case 'sunburst':
                    renderStorySunburstLayout();
                    break;
                case 'grid':
                    renderStoryGridLayout();
                    break;
                default:
                    renderStoryForceLayout();
            }

            storyLayoutRendered[layout] = true;
        }

        function renderLayout(layout) {
            if (!explorerData) return;
            if (layoutRendered[layout]) return;  // Don't re-render if already done

            debugLog('Rendering layout:', layout);

            switch (layout) {
                case 'force':
                    renderForceLayout();
                    break;
                case 'bundling':
                    renderEdgeBundlingLayout();
                    break;
                case 'treemap':
                    renderTreemapLayout();
                    break;
                case 'packing':
                    renderCirclePackingLayout();
                    break;
                case 'sunburst':
                    renderSunburstLayout();
                    break;
                case 'grid':
                    renderGridLayout();
                    break;
                default:
                    renderForceLayout();
            }

            layoutRendered[layout] = true;
        }

        // Force-directed layout (original Explorer mode)
        function renderForceLayout() {
            if (!explorerData) return;

            const explorerContainer = document.getElementById('explorer-wrapper');
            const explorerSvg = d3.select('#explorer-graph');
            const eWidth = explorerContainer.clientWidth;
            const eHeight = explorerContainer.clientHeight || 600;
            explorerSvg.attr('width', eWidth).attr('height', eHeight);

            // Zoom for explorer
            const eZoom = d3.zoom()
                .scaleExtent([0.2, 3])
                .on('zoom', (event) => eG.attr('transform', event.transform));
            explorerSvg.call(eZoom);

            const eG = explorerSvg.append('g');

            // Compute phase participation (heat) for each file
            const filePhaseCount = {};
            if (phasesData && timelineData) {
                phasesData.forEach(phase => {
                    const filesInPhase = new Set();
                    for (let i = phase.start; i <= phase.end && i < timelineData.length; i++) {
                        if (timelineData[i].file) filesInPhase.add(timelineData[i].file);
                    }
                    filesInPhase.forEach(f => {
                        filePhaseCount[f] = (filePhaseCount[f] || 0) + 1;
                    });
                });
            }
            const maxPhaseCount = Math.max(...Object.values(filePhaseCount), 1);
            const heatScale = d3.scaleLinear().domain([0, maxPhaseCount]).range([0.4, 1]);

            // Update heat legend stats
            const touchedFiles = Object.keys(filePhaseCount).length;
            const totalFiles = explorerData.nodes.length;
            const touchedPct = totalFiles > 0 ? Math.round(100 * touchedFiles / totalFiles) : 0;
            const avgPhases = touchedFiles > 0 ? (Object.values(filePhaseCount).reduce((a, b) => a + b, 0) / touchedFiles).toFixed(1) : 0;
            const heatStat = document.getElementById('heat-stat');
            if (heatStat) {
                heatStat.innerHTML = `<strong>${touchedFiles}</strong> of ${totalFiles} files touched (${touchedPct}%)<br>Avg: ${avgPhases} phases/file`;
            }
            // Show legend in explorer mode
            const heatLegend = document.getElementById('heat-legend');
            if (heatLegend) heatLegend.style.display = 'block';

            // Color by file extension
            const extColors = {
                '.py': '#7ee787',
                '.yaml': '#f0883e',
                '.yml': '#f0883e',
                '.json': '#58a6ff',
                '.md': '#8b949e',
                '.html': '#e34c26',
                '.js': '#f1e05a',
                '.css': '#563d7c'
            };

            // Filter to files with connections only
            const connectedNodes = new Set();
            explorerData.edges.forEach(e => {
                connectedNodes.add(e.source);
                connectedNodes.add(e.target);
            });

            const nodes = explorerData.nodes.filter(n => connectedNodes.has(n.id));
            // Add phase heat to each node
            nodes.forEach(n => {
                n.phaseCount = filePhaseCount[n.name] || 0;
                n.heat = heatScale(n.phaseCount);
            });
            const edges = explorerData.edges;

            // ═══════════════════════════════════════════════════════════
            // CONSTELLATION MODE - Calculate brightness for each node
            // "Only show the brightest stars. The dim ones are still there."
            // ═══════════════════════════════════════════════════════════

            // Brightness = cooccur count (activity) * recency boost from phaseCount
            // Higher cooccur = touched more often, higher phaseCount = touched in more phases
            const maxActivity = Math.max(...nodes.map(n => (n.cooccur || 1) * (1 + (n.phaseCount || 0) * 0.2)));
            nodes.forEach(n => {
                const activity = (n.cooccur || 1) * (1 + (n.phaseCount || 0) * 0.2);
                n.brightness = activity / maxActivity;  // 0-1 normalized
            });

            // Sort by brightness and assign tier
            const sortedByBrightness = [...nodes].sort((a, b) => b.brightness - a.brightness);
            const starCount = Math.min(7, nodes.length);
            const contextCount = Math.min(15, nodes.length - starCount);

            sortedByBrightness.forEach((n, i) => {
                if (i < starCount) {
                    n.tier = 'star';       // Top 7: full visibility
                } else if (i < starCount + contextCount) {
                    n.tier = 'context';    // Next 15: dim but visible
                } else {
                    n.tier = 'dark';       // Rest: nearly invisible
                }
            });

            debugLog(`Constellation: ${starCount} stars, ${contextCount} context, ${nodes.length - starCount - contextCount} dark matter`);

            // Build node lookup
            const nodeById = {};
            nodes.forEach(n => nodeById[n.id] = n);

            // Size scale based on cooccur count
            const maxCooccur = Math.max(...nodes.map(n => n.cooccur || 1));
            const nodeScale = d3.scaleSqrt().domain([0, maxCooccur]).range([4, 16]);

            // ═══════════════════════════════════════════════════════════
            // CLUSTER ISLANDS - Meaningful initial node positions
            // "Friends start standing with their friend group, then mingle"
            // ═══════════════════════════════════════════════════════════

            // Get unique cluster IDs for initial layout
            const layoutClusterIds = [...new Set(nodes.map(n => n.cluster).filter(c => c >= 0))].sort((a, b) => a - b);
            const numClusters = layoutClusterIds.length;

            // Compute cluster center positions in a ring around viewport center
            const centerX = eWidth / 2;
            const centerY = eHeight / 2;
            const ringRadius = Math.min(eWidth, eHeight) * 0.35;  // 35% of smaller dimension

            const clusterCenters = {};
            layoutClusterIds.forEach((clusterId, i) => {
                const angle = (2 * Math.PI * i / numClusters) - Math.PI / 2;  // Start at top
                clusterCenters[clusterId] = {
                    x: centerX + ringRadius * Math.cos(angle),
                    y: centerY + ringRadius * Math.sin(angle)
                };
            });

            // Assign initial x,y to nodes based on cluster membership
            const clusterZoneRadius = 80;  // Nodes spread within this radius of cluster center
            nodes.forEach(n => {
                if (n.cluster >= 0 && clusterCenters[n.cluster]) {
                    // Position within cluster zone with small random offset
                    const center = clusterCenters[n.cluster];
                    const offsetAngle = Math.random() * 2 * Math.PI;
                    const offsetRadius = Math.random() * clusterZoneRadius;
                    n.x = center.x + offsetRadius * Math.cos(offsetAngle);
                    n.y = center.y + offsetRadius * Math.sin(offsetAngle);
                } else {
                    // Unclustered nodes: position near center, force will scatter
                    n.x = centerX + (Math.random() - 0.5) * 100;
                    n.y = centerY + (Math.random() - 0.5) * 100;
                }
            });

            debugLog(`Cluster Islands: ${numClusters} clusters positioned in ring, ${nodes.length} nodes assigned initial positions`);

            // Custom cluster force - pulls nodes toward cluster centroids + repels clusters from each other
            function clusterForce(strength) {
                let nodeData;
                function force(alpha) {
                    const centers = {};
                    const counts = {};
                    // Calculate cluster centers
                    nodeData.forEach(d => {
                        if (d.cluster < 0) return; // Skip unclustered
                        if (!centers[d.cluster]) { centers[d.cluster] = {x: 0, y: 0}; counts[d.cluster] = 0; }
                        centers[d.cluster].x += d.x;
                        centers[d.cluster].y += d.y;
                        counts[d.cluster]++;
                    });
                    Object.keys(centers).forEach(c => {
                        centers[c].x /= counts[c];
                        centers[c].y /= counts[c];
                    });

                    // Inter-cluster repulsion - push cluster centers apart
                    const clusterList = Object.keys(centers);
                    const repulsionStrength = 200;  // How strongly clusters repel each other
                    for (let i = 0; i < clusterList.length; i++) {
                        for (let j = i + 1; j < clusterList.length; j++) {
                            const ci = centers[clusterList[i]];
                            const cj = centers[clusterList[j]];
                            const dx = cj.x - ci.x;
                            const dy = cj.y - ci.y;
                            const dist = Math.sqrt(dx * dx + dy * dy) || 1;
                            const minDist = 150;  // Minimum distance between cluster centers
                            if (dist < minDist) {
                                const pushFactor = (minDist - dist) / dist * repulsionStrength * alpha;
                                ci.repelX = (ci.repelX || 0) - dx * pushFactor / dist;
                                ci.repelY = (ci.repelY || 0) - dy * pushFactor / dist;
                                cj.repelX = (cj.repelX || 0) + dx * pushFactor / dist;
                                cj.repelY = (cj.repelY || 0) + dy * pushFactor / dist;
                            }
                        }
                    }

                    // Apply forces to nodes: pull toward own cluster center + inter-cluster repulsion
                    nodeData.forEach(d => {
                        if (d.cluster < 0) return;
                        const c = centers[d.cluster];
                        if (c) {
                            // Pull toward cluster center
                            d.vx += (c.x - d.x) * strength * alpha;
                            d.vy += (c.y - d.y) * strength * alpha;
                            // Apply inter-cluster repulsion (pushes whole cluster away from others)
                            if (c.repelX) d.vx += c.repelX * 0.1;
                            if (c.repelY) d.vy += c.repelY * 0.1;
                        }
                    });
                }
                force.initialize = _ => nodeData = _;
                return force;
            }

            // Simulation - gentler forces, settles quickly
            const simulation = d3.forceSimulation(nodes)
                .force('link', d3.forceLink(edges).id(d => d.id).distance(100).strength(0.3))
                .force('charge', d3.forceManyBody().strength(-80))
                .force('center', d3.forceCenter(eWidth / 2, eHeight / 2))
                .force('collision', d3.forceCollide().radius(d => nodeScale(d.cooccur || 1) + 8))
                .force('cluster', clusterForce(0.6))  // Strong pull toward cluster centroids (tectonic)
                .alphaDecay(0.05)  // Settle faster
                .velocityDecay(0.4);  // More damping

            // ═══════════════════════════════════════════════════════════
            // TECTONIC CLUSTERS - Physics-based cluster emergence
            // Clusters become visible through spacing, not overlays
            // ═══════════════════════════════════════════════════════════

            // Get unique cluster IDs (excluding -1 = unclustered)
            const clusterIds = [...new Set(nodes.map(n => n.cluster).filter(c => c >= 0))].sort((a, b) => a - b);

            // Pre-compute cluster membership for edge styling
            const nodeCluster = {};
            nodes.forEach(n => { nodeCluster[n.id] = n.cluster; });

            // Cluster color palette for node borders (subtle but distinct)
            const clusterBorderColors = [
                '#ff6b6b',  // Coral - cluster 0 (hooks)
                '#4ecdc4',  // Teal - cluster 1 (commands)
                '#ffe66d',  // Gold - cluster 2 (root configs)
                '#7b6d8d',  // Lavender - cluster 3 (tools)
                '#1a535c',  // Deep teal - cluster 4 (research)
                '#f4a261',  // Orange - cluster 5 (state)
                '#a8dadc',  // Cyan - cluster 6 (proof)
            ];

            // Legacy: keep contour layer hidden for compatibility
            const contourGroup = eG.append('g').attr('class', 'contour-layer').style('display', 'none');

            // Density computation function - call after simulation stabilizes
            function computeDensityContours() {
                // Get current node positions
                const points = nodes.map(n => [n.x, n.y]);
                if (points.length < 3) return; // Need at least 3 points

                // Compute bounding box with padding
                const xExtent = d3.extent(points, d => d[0]);
                const yExtent = d3.extent(points, d => d[1]);
                const padding = 60;
                const x0 = xExtent[0] - padding;
                const x1 = xExtent[1] + padding;
                const y0 = yExtent[0] - padding;
                const y1 = yExtent[1] + padding;

                // Bandwidth = average node spacing (adaptive to graph density)
                const avgSpacing = Math.sqrt((x1 - x0) * (y1 - y0) / nodes.length);
                const bandwidth = avgSpacing * 0.8;

                // Create density estimator
                const densityData = d3.contourDensity()
                    .x(d => d[0])
                    .y(d => d[1])
                    .size([x1 - x0, y1 - y0])
                    .bandwidth(bandwidth)
                    .thresholds(8)  // Number of contour levels
                    (points);

                // Store for later use (coloring, glow intensity)
                window.densityContours = densityData;
                window.contourGroup = contourGroup;
                window.contourOffset = { x: x0, y: y0 };
                window.explorerExtColors = extColors;
                window.explorerNodes_data = nodes;

                // Render basic contours (will be enhanced in L3-L6)
                renderContours(densityData, x0, y0);
            }

            // Render contour paths with extension-based coloring
            function renderContours(densityData, offsetX, offsetY) {
                // Clear existing contours
                contourGroup.selectAll('*').remove();

                // For each contour, find nodes inside and determine dominant extension
                densityData.forEach(contour => {
                    // Get contour bounds (approximate from coordinates)
                    const coords = contour.coordinates.flat(2);
                    if (coords.length === 0) return;

                    const xs = coords.filter((_, i) => i % 2 === 0);
                    const ys = coords.filter((_, i) => i % 2 === 1);
                    const bounds = {
                        minX: Math.min(...xs) + offsetX,
                        maxX: Math.max(...xs) + offsetX,
                        minY: Math.min(...ys) + offsetY,
                        maxY: Math.max(...ys) + offsetY
                    };

                    // Find nodes within these bounds
                    const nodesInRegion = nodes.filter(n =>
                        n.x >= bounds.minX && n.x <= bounds.maxX &&
                        n.y >= bounds.minY && n.y <= bounds.maxY
                    );

                    // Count extensions
                    const extCounts = {};
                    nodesInRegion.forEach(n => {
                        const ext = n.ext || '.other';
                        extCounts[ext] = (extCounts[ext] || 0) + 1;
                    });

                    // Find dominant extension
                    let dominantExt = '.py';  // default
                    let maxCount = 0;
                    for (const [ext, count] of Object.entries(extCounts)) {
                        if (count > maxCount) {
                            maxCount = count;
                            dominantExt = ext;
                        }
                    }

                    // Count internal edges (both endpoints in region)
                    const nodeNamesInRegion = new Set(nodesInRegion.map(n => n.name || n.id));
                    let internalEdgeCount = 0;
                    (edges || []).forEach(edge => {
                        const sourceId = typeof edge.source === 'object' ? edge.source.id : edge.source;
                        const targetId = typeof edge.target === 'object' ? edge.target.id : edge.target;
                        if (nodeNamesInRegion.has(sourceId) && nodeNamesInRegion.has(targetId)) {
                            internalEdgeCount += (edge.weight || 1);
                        }
                    });

                    // Store for later use (glow, purity)
                    // Calculate purity: how homogeneous is the extension distribution?
                    // purity = dominant count / total nodes (1.0 = all same type, lower = mixed)
                    const totalInRegion = nodesInRegion.length;
                    const purity = totalInRegion > 0 ? maxCount / totalInRegion : 0;

                    contour.dominantExt = dominantExt;
                    contour.nodesInRegion = nodesInRegion;
                    contour.extCounts = extCounts;
                    contour.internalEdges = internalEdgeCount;
                    contour.purity = purity;
                });

                // Calculate max internal edges for normalization
                const maxInternalEdges = Math.max(...densityData.map(d => d.internalEdges || 0), 1);

                // Draw contours with extension colors and edge-based glow
                contourGroup.selectAll('path')
                    .data(densityData)
                    .join('path')
                    .attr('class', 'density-contour')
                    .attr('d', d3.geoPath())
                    .attr('transform', `translate(${offsetX}, ${offsetY})`)
                    .attr('fill', d => {
                        const baseColor = extColors[d.dominantExt] || '#8b949e';
                        return d3.color(baseColor).copy({opacity: 1}).formatHex();
                    })
                    .attr('stroke', d => extColors[d.dominantExt] || '#8b949e')
                    .attr('stroke-width', d => {
                        // Thicker stroke for high-connectivity regions
                        const edgeRatio = (d.internalEdges || 0) / maxInternalEdges;
                        return 0.5 + edgeRatio * 2;
                    })
                    .attr('opacity', d => {
                        // Opacity based on: density level + purity bonus
                        // Pure clusters (all same extension) are more visible
                        // Mixed clusters fade into background
                        const maxDensity = d3.max(densityData, c => c.value) || 1;
                        const densityFactor = (d.value / maxDensity);
                        const purity = d.purity || 0;

                        // Base: 0.05-0.15 from density
                        // Purity bonus: 0-0.20 for pure clusters
                        const baseOpacity = 0.05 + densityFactor * 0.10;
                        const purityBonus = purity * purity * 0.20;  // squared for stronger effect

                        return Math.min(baseOpacity + purityBonus, 0.35);  // cap at 35%
                    })
                    .style('filter', d => {
                        // Glow intensity based on internal edge count
                        const edgeRatio = (d.internalEdges || 0) / maxInternalEdges;
                        if (edgeRatio > 0.3) {
                            const glowSize = 4 + edgeRatio * 12;
                            const color = extColors[d.dominantExt] || '#8b949e';
                            return `drop-shadow(0 0 ${glowSize}px ${color})`;
                        }
                        return 'none';
                    })
                    .style('pointer-events', 'none');  // Don't block node interactions
            }

            // Trigger density computation after simulation settles
            simulation.on('end', () => {
                computeDensityContours();
            });

            // Also compute after a few seconds in case simulation doesn't fully end
            setTimeout(() => {
                if (!window.densityContours) {
                    computeDensityContours();
                }
            }, 3000);

            // Draw edges with visual distinction by cluster relationship
            // Cross-cluster edges (bridges) are bright - intra-cluster edges are faint
            const link = eG.append('g')
                .selectAll('line')
                .data(edges)
                .join('line')
                .attr('class', d => {
                    const sourceId = typeof d.source === 'object' ? d.source.id : d.source;
                    const targetId = typeof d.target === 'object' ? d.target.id : d.target;
                    const sourceCluster = nodeCluster[sourceId];
                    const targetCluster = nodeCluster[targetId];
                    const isCrossCluster = sourceCluster >= 0 && targetCluster >= 0 && sourceCluster !== targetCluster;
                    return `explorer-link ${d.edgeType || d.type} ${isCrossCluster ? 'bridge' : 'internal'}`;
                })
                .attr('stroke', d => {
                    const sourceId = typeof d.source === 'object' ? d.source.id : d.source;
                    const targetId = typeof d.target === 'object' ? d.target.id : d.target;
                    const sourceCluster = nodeCluster[sourceId];
                    const targetCluster = nodeCluster[targetId];
                    const isCrossCluster = sourceCluster >= 0 && targetCluster >= 0 && sourceCluster !== targetCluster;
                    // Cross-cluster = bright gold, intra-cluster/import = subtle gray
                    if (isCrossCluster) return '#f0c674';  // Gold bridges
                    return (d.edgeType === 'import') ? '#39c5bb' : '#30363d';
                })
                .attr('stroke-width', d => {
                    const sourceId = typeof d.source === 'object' ? d.source.id : d.source;
                    const targetId = typeof d.target === 'object' ? d.target.id : d.target;
                    const sourceCluster = nodeCluster[sourceId];
                    const targetCluster = nodeCluster[targetId];
                    const isCrossCluster = sourceCluster >= 0 && targetCluster >= 0 && sourceCluster !== targetCluster;
                    const base = Math.max(1, Math.log(d.weight || 1));
                    // Cross-cluster edges are thicker to stand out
                    if (isCrossCluster) return base * 1.5;
                    return (d.edgeType === 'import') ? base * 0.6 : base * 0.7;
                })
                .attr('stroke-dasharray', d => {
                    // Import edges: dashed, others: solid
                    return (d.edgeType === 'import') ? '4,3' : 'none';
                })
                .attr('opacity', d => {
                    const sourceId = typeof d.source === 'object' ? d.source.id : d.source;
                    const targetId = typeof d.target === 'object' ? d.target.id : d.target;
                    const sourceCluster = nodeCluster[sourceId];
                    const targetCluster = nodeCluster[targetId];
                    const isCrossCluster = sourceCluster >= 0 && targetCluster >= 0 && sourceCluster !== targetCluster;
                    // Cross-cluster = very bright (0.9), intra-cluster = faint (0.2)
                    if (isCrossCluster) return 0.9;
                    return (d.edgeType === 'import') ? 0.35 : 0.2;
                })
                .style('filter', d => {
                    const sourceId = typeof d.source === 'object' ? d.source.id : d.source;
                    const targetId = typeof d.target === 'object' ? d.target.id : d.target;
                    const sourceCluster = nodeCluster[sourceId];
                    const targetCluster = nodeCluster[targetId];
                    const isCrossCluster = sourceCluster >= 0 && targetCluster >= 0 && sourceCluster !== targetCluster;
                    // Add glow to cross-cluster bridges
                    if (isCrossCluster) return 'drop-shadow(0 0 3px #f0c674)';
                    return 'none';
                });

            // Draw nodes
            const eNode = eG.append('g')
                .selectAll('g')
                .data(nodes)
                .join('g')
                .attr('class', 'explorer-node')
                .call(d3.drag()
                    .on('start', dragstarted)
                    .on('drag', dragged)
                    .on('end', dragended))
                .on('click', (event, d) => {
                    event.stopPropagation();
                    showInsightCard(event, {
                        id: 'file:' + d.name,
                        type: 'file',
                        count: d.cooccur || 0,
                        path: d.path,
                        actions: {},
                        dominant: 'other',
                        timestamps: []
                    });
                    focusExplorerNode(d.name);
                });

            // CONSTELLATION MODE: opacity based on tier
            const tierOpacity = { star: 1.0, context: 0.3, dark: 0.08 };

            eNode.append('circle')
                .attr('class', d => `node-shape node-circle tier-${d.tier}`)
                .attr('r', d => nodeScale(d.cooccur || 1))
                .attr('fill', d => extColors[d.ext] || '#8b949e')
                .attr('stroke', d => {
                    // Cluster-colored borders for grouped nodes, gray for unclustered
                    if (d.cluster >= 0 && d.cluster < clusterBorderColors.length) {
                        return clusterBorderColors[d.cluster];
                    }
                    return '#30363d';
                })
                .attr('stroke-width', d => d.cluster >= 0 ? 2.5 : 1.5)
                .style('opacity', d => tierOpacity[d.tier] || 0.08)
                .style('filter', d => d.tier === 'star' ? `drop-shadow(0 0 8px ${extColors[d.ext] || '#8b949e'})` : 'none')
                .style('transition', 'opacity 0.2s ease');

            eNode.append('text')
                .attr('class', d => `node-label tier-${d.tier}`)
                .attr('dx', d => nodeScale(d.cooccur || 1) + 4)
                .attr('dy', 4)
                .text(d => d.name)
                .style('opacity', d => d.tier === 'star' ? 1.0 : 0)  // Only stars show labels
                .style('transition', 'opacity 0.2s ease');

            // Add title/tooltip with phase info
            eNode.append('title')
                .text(d => `${d.name}\nTouched in ${d.phaseCount} phase${d.phaseCount !== 1 ? 's' : ''}\nCo-occurred ${d.cooccur || 0} times`);

            // Tick - update positions for links and nodes
            simulation.on('tick', () => {
                link
                    .attr('x1', d => d.source.x)
                    .attr('y1', d => d.source.y)
                    .attr('x2', d => d.target.x)
                    .attr('y2', d => d.target.y);
                eNode.attr('transform', d => `translate(${d.x},${d.y})`);
            }).on('end', () => {
                // Rebuild quadtree after simulation stabilizes
                if (typeof window.rebuildExplorerQuadtree === 'function') {
                    window.rebuildExplorerQuadtree();
                }
            });

            // Drag handlers - nodes stay where you put them
            function dragstarted(event, d) {
                if (!event.active) simulation.alphaTarget(0.1).restart();
                d.fx = d.x;
                d.fy = d.y;
            }
            function dragged(event, d) {
                d.fx = event.x;
                d.fy = event.y;
            }
            function dragended(event, d) {
                if (!event.active) simulation.alphaTarget(0);
                // Keep node fixed where user placed it (don't release to simulation)
                // d.fx and d.fy remain set from dragged()
                // Rebuild quadtree after drag
                if (typeof window.rebuildExplorerQuadtree === 'function') {
                    window.rebuildExplorerQuadtree();
                }
            }

            // Store references for focus function and fullscreen resize
            window.explorerNodes = eNode;
            window.explorerLinks = link;
            window.explorerEdges = edges;
            window.explorerSimulation = simulation;
            window.explorerSvg = explorerSvg;

            // ═══════════════════════════════════════════════════════════
            // CONSTELLATION MODE: Hover Proximity Reveal (Explorer)
            // Nodes within 100px of cursor brighten and show labels
            // ═══════════════════════════════════════════════════════════

            const EXPLORER_PROXIMITY_RADIUS = 100;
            const EXPLORER_PROXIMITY_RADIUS_SQ = EXPLORER_PROXIMITY_RADIUS * EXPLORER_PROXIMITY_RADIUS;
            const explorerTierOpacity = { star: 1.0, context: 0.3, dark: 0.08 };

            // Quadtree for O(log N) proximity detection
            let explorerQuadtree = d3.quadtree()
                .x(d => d.x)
                .y(d => d.y)
                .addAll(nodes);

            function rebuildExplorerQuadtree() {
                explorerQuadtree = d3.quadtree()
                    .x(d => d.x)
                    .y(d => d.y)
                    .addAll(nodes);
            }

            // Expose for rebuild after simulation/drag
            window.rebuildExplorerQuadtree = rebuildExplorerQuadtree;

            explorerSvg.on('mousemove', function(event) {
                // Skip if Reveal All is enabled - everything already visible
                if (typeof revealAllEnabled !== 'undefined' && revealAllEnabled) return;

                const [mx, my] = d3.pointer(event);

                // Clear previous proximity flags
                nodes.forEach(n => n.isProximity = false);

                // During simulation animation, quadtree bounds are stale - fall back to linear scan
                const isAnimating = simulation.alpha() > 0.01;

                if (isAnimating) {
                    // Linear scan during animation (accurate but O(N))
                    nodes.forEach(n => {
                        const dx = n.x - mx;
                        const dy = n.y - my;
                        if (dx * dx + dy * dy < EXPLORER_PROXIMITY_RADIUS_SQ) {
                            n.isProximity = true;
                        }
                    });
                } else {
                    // Use quadtree for O(log N) proximity detection (stable positions)
                    explorerQuadtree.visit((quad, x0, y0, x1, y1) => {
                        // Skip if the quad is entirely outside proximity radius
                        const dx = Math.max(0, Math.max(x0 - mx, mx - x1));
                        const dy = Math.max(0, Math.max(y0 - my, my - y1));
                        if (dx * dx + dy * dy > EXPLORER_PROXIMITY_RADIUS_SQ) return true; // prune

                        // Check leaf node - verify with current coordinates
                        if (!quad.length && quad.data) {
                            const d = quad.data;
                            const ndx = d.x - mx;
                            const ndy = d.y - my;
                            if (ndx * ndx + ndy * ndy < EXPLORER_PROXIMITY_RADIUS_SQ) {
                                d.isProximity = true;
                            }
                        }
                        return false; // continue traversal
                    });
                }

                // Update node opacities
                eNode.select('circle')
                    .style('opacity', d => d.isProximity ? 1.0 : explorerTierOpacity[d.tier] || 0.08)
                    .style('filter', d => {
                        if (d.tier === 'star' || d.isProximity) {
                            return `drop-shadow(0 0 8px ${extColors[d.ext] || '#8b949e'})`;
                        }
                        return 'none';
                    });

                // Update label visibility
                eNode.select('text')
                    .style('opacity', d => (d.tier === 'star' || d.isProximity) ? 1.0 : 0);
            });

            // Reset when mouse leaves SVG
            explorerSvg.on('mouseleave', function() {
                // Skip if Reveal All is enabled
                if (typeof revealAllEnabled !== 'undefined' && revealAllEnabled) return;

                nodes.forEach(n => n.isProximity = false);

                eNode.select('circle')
                    .style('opacity', d => explorerTierOpacity[d.tier] || 0.08)
                    .style('filter', d => d.tier === 'star' ? `drop-shadow(0 0 8px ${extColors[d.ext] || '#8b949e'})` : 'none');

                eNode.select('text')
                    .style('opacity', d => d.tier === 'star' ? 1.0 : 0);
            });
        }

        // ═══════════════════════════════════════════════════════════
        // HIERARCHICAL EDGE BUNDLING LAYOUT
        // Nodes arranged by directory hierarchy, edges bundled through center
        // ═══════════════════════════════════════════════════════════

        function renderEdgeBundlingLayout() {
            if (!explorerData) return;

            const container = document.getElementById('explorer-wrapper');
            const svg = d3.select('#explorer-graph');
            const width = container.clientWidth;
            const height = container.clientHeight || 600;
            svg.attr('width', width).attr('height', height);

            const g = svg.append('g')
                .attr('transform', `translate(${width/2},${height/2})`);

            // Build hierarchy from file paths
            const root = buildHierarchy(explorerData.nodes);
            const radius = Math.min(width, height) / 2 - 120;

            // Create cluster layout
            const cluster = d3.cluster()
                .size([360, radius]);

            cluster(root);

            // Get leaf nodes (files)
            const leaves = root.leaves();
            const nodeById = {};
            leaves.forEach(d => {
                nodeById[d.data.id] = d;
            });

            // Extension colors
            const extColors = {
                '.py': '#7ee787', '.yaml': '#f0883e', '.yml': '#f0883e',
                '.json': '#58a6ff', '.md': '#8b949e', '.html': '#e34c26',
                '.js': '#f1e05a', '.css': '#563d7c', '.sh': '#a371f7'
            };

            // Draw edges with bundling
            const line = d3.lineRadial()
                .curve(d3.curveBundle.beta(0.85))
                .radius(d => d.y)
                .angle(d => d.x * Math.PI / 180);

            // Create edge paths
            const edges = explorerData.edges.filter(e =>
                nodeById[e.source] && nodeById[e.target]
            );

            g.append('g')
                .attr('class', 'bundled-edges')
                .selectAll('path')
                .data(edges)
                .join('path')
                .attr('class', 'bundled-edge')
                .attr('d', d => {
                    const source = nodeById[d.source];
                    const target = nodeById[d.target];
                    if (!source || !target) return '';
                    const path = source.path(target);
                    return line(path);
                })
                .attr('fill', 'none')
                .attr('stroke', d => {
                    const source = nodeById[d.source];
                    return source ? (extColors[source.data.ext] || '#30363d') : '#30363d';
                })
                .attr('stroke-opacity', 0.4)
                .attr('stroke-width', 1.5);

            // Draw nodes
            const node = g.append('g')
                .attr('class', 'bundled-nodes')
                .selectAll('g')
                .data(leaves)
                .join('g')
                .attr('class', 'bundled-node')
                .attr('transform', d => `rotate(${d.x - 90}) translate(${d.y},0)`);

            node.append('circle')
                .attr('class', 'node-shape')
                .attr('r', 5)
                .attr('fill', d => extColors[d.data.ext] || '#8b949e')
                .style('cursor', 'pointer');

            node.append('text')
                .attr('dy', '0.31em')
                .attr('x', d => d.x < 180 ? 8 : -8)
                .attr('text-anchor', d => d.x < 180 ? 'start' : 'end')
                .attr('transform', d => d.x >= 180 ? 'rotate(180)' : null)
                .text(d => {
                    const name = d.data.name;
                    return name.length > 12 ? name.slice(0, 10) + '…' : name;
                })
                .attr('fill', '#c9d1d9')
                .attr('font-size', '8px')
                .style('pointer-events', 'none');

            // Add hover and click effects
            node.on('mouseover', function(event, d) {
                d3.select(this).select('circle')
                    .attr('r', 8)
                    .style('filter', `drop-shadow(0 0 6px ${extColors[d.data.ext] || '#8b949e'})`);

                // Highlight connected edges
                g.selectAll('.bundled-edge')
                    .attr('stroke-opacity', e =>
                        (e.source === d.data.id || e.target === d.data.id) ? 0.9 : 0.1
                    )
                    .attr('stroke-width', e =>
                        (e.source === d.data.id || e.target === d.data.id) ? 3 : 1
                    );

                // Show tooltip with full path
                const tooltip = d3.select('#tooltip');
                tooltip.style('display', 'block')
                    .style('left', (event.pageX + 10) + 'px')
                    .style('top', (event.pageY - 10) + 'px')
                    .html(`<strong>${d.data.name}</strong><br/>
                           <span style="color:#8b949e;font-size:10px;">Path: ${d.data.id || ''}</span><br/>
                           Activity: ${d.data.data?.cooccur || 0}`);
            })
            .on('mouseout', function() {
                d3.select(this).select('circle')
                    .attr('r', 5)
                    .style('filter', 'none');

                g.selectAll('.bundled-edge')
                    .attr('stroke-opacity', 0.4)
                    .attr('stroke-width', 1.5);

                d3.select('#tooltip').style('display', 'none');
            })
            .on('click', function(event, d) {
                event.stopPropagation();
                showInsightCard(event, {
                    name: d.data.name,
                    id: d.data.id,
                    count: d.data.data?.cooccur || 1,
                    ext: d.data.ext,
                    type: 'file'
                });
            });

            // Zoom
            const zoom = d3.zoom()
                .scaleExtent([0.3, 3])
                .on('zoom', (event) => g.attr('transform', `translate(${width/2 + event.transform.x},${height/2 + event.transform.y}) scale(${event.transform.k})`));
            svg.call(zoom);

            debugLog('Edge Bundling: rendered', leaves.length, 'nodes,', edges.length, 'edges');
        }

        // Helper: Build hierarchy from flat file list
        function buildHierarchy(nodes) {
            const root = { name: 'root', children: [] };
            const pathMap = { '': root };

            // Sort by path for consistent ordering
            const sorted = [...nodes].sort((a, b) => a.id.localeCompare(b.id));

            sorted.forEach(node => {
                const parts = node.id.split('/');
                let parent = root;
                let currentPath = '';

                // Create directory nodes
                for (let i = 0; i < parts.length - 1; i++) {
                    currentPath += (currentPath ? '/' : '') + parts[i];
                    if (!pathMap[currentPath]) {
                        const dir = { name: parts[i], children: [] };
                        parent.children.push(dir);
                        pathMap[currentPath] = dir;
                    }
                    parent = pathMap[currentPath];
                }

                // Add file node
                const ext = '.' + (node.name.split('.').pop() || '');
                parent.children.push({
                    name: node.name,
                    id: node.id,
                    ext: ext,
                    data: node
                });
            });

            return d3.hierarchy(root);
        }

        // ═══════════════════════════════════════════════════════════
        // TREEMAP LAYOUT
        // Rectangles nested by directory hierarchy
        // ═══════════════════════════════════════════════════════════

        function renderTreemapLayout() {
            if (!explorerData) return;

            const container = document.getElementById('explorer-wrapper');
            const svg = d3.select('#explorer-graph');
            const width = container.clientWidth;
            const height = container.clientHeight || 600;
            svg.attr('width', width).attr('height', height);

            const g = svg.append('g');

            // Build hierarchy
            const root = buildHierarchy(explorerData.nodes);

            // Compute sizes based on file activity
            root.sum(d => d.data && d.data.cooccur ? d.data.cooccur + 1 : 1);

            // Create treemap layout
            const treemap = d3.treemap()
                .size([width - 20, height - 20])
                .paddingOuter(3)
                .paddingTop(19)
                .paddingInner(2)
                .round(true);

            treemap(root);

            // Extension colors
            const extColors = {
                '.py': '#7ee787', '.yaml': '#f0883e', '.yml': '#f0883e',
                '.json': '#58a6ff', '.md': '#8b949e', '.html': '#e34c26',
                '.js': '#f1e05a', '.css': '#563d7c', '.sh': '#a371f7'
            };

            // Draw cells
            const cell = g.selectAll('g')
                .data(root.descendants())
                .join('g')
                .attr('transform', d => `translate(${d.x0 + 10},${d.y0 + 10})`);

            // Rectangles
            cell.append('rect')
                .attr('class', 'node-shape')
                .attr('width', d => Math.max(0, d.x1 - d.x0))
                .attr('height', d => Math.max(0, d.y1 - d.y0))
                .attr('fill', d => {
                    if (d.children) return '#21262d';  // Directories
                    return extColors[d.data.ext] || '#8b949e';
                })
                .attr('fill-opacity', d => d.children ? 0.3 : 0.7)
                .attr('stroke', '#30363d')
                .attr('stroke-width', d => d.depth === 1 ? 2 : 1)
                .attr('rx', 2)
                .style('cursor', d => d.children ? 'default' : 'pointer')
                .on('mouseover', function(event, d) {
                    if (d.children) return;
                    d3.select(this)
                        .attr('fill-opacity', 1)
                        .attr('stroke', '#58a6ff')
                        .attr('stroke-width', 2);

                    // Show tooltip with full path
                    const tooltip = d3.select('#tooltip');
                    tooltip.style('display', 'block')
                        .style('left', (event.pageX + 10) + 'px')
                        .style('top', (event.pageY - 10) + 'px')
                        .html(`<strong>${d.data.name}</strong><br/>
                               <span style="color:#8b949e;font-size:10px;">Path: ${d.data.id || ''}</span><br/>
                               Activity: ${d.data.data?.cooccur || 0}`);
                })
                .on('mouseout', function(event, d) {
                    if (d.children) return;
                    d3.select(this)
                        .attr('fill-opacity', 0.7)
                        .attr('stroke', '#30363d')
                        .attr('stroke-width', 1);
                    d3.select('#tooltip').style('display', 'none');
                })
                .on('click', function(event, d) {
                    if (d.children) return;
                    event.stopPropagation();
                    d3.select('#tooltip').style('display', 'none');
                    showInsightCard(event, {
                        name: d.data.name,
                        id: d.data.id,
                        count: d.data.data?.cooccur || 1,
                        ext: d.data.ext,
                        type: 'file'
                    });
                });

            // Labels - smaller font, more aggressive truncation
            cell.append('text')
                .attr('x', 4)
                .attr('y', d => d.children ? 14 : (d.y1 - d.y0) / 2 + 3)
                .text(d => {
                    const w = d.x1 - d.x0;
                    const h = d.y1 - d.y0;
                    const name = d.data.name;
                    if (w < 25 || h < 18) return '';
                    if (w < 50) return name.slice(0, 2);
                    if (w < 80) return name.slice(0, 6);
                    if (w < 120) return name.length > 10 ? name.slice(0, 8) + '…' : name;
                    return name.length > 16 ? name.slice(0, 14) + '…' : name;
                })
                .attr('fill', d => d.children ? '#8b949e' : '#0d1117')
                .attr('font-size', d => d.children ? '10px' : '8px')
                .attr('font-weight', d => d.children ? '600' : '400')
                .style('pointer-events', 'none');

            // Zoom
            const zoom = d3.zoom()
                .scaleExtent([0.5, 4])
                .on('zoom', (event) => g.attr('transform', event.transform));
            svg.call(zoom);

            debugLog('Treemap: rendered', root.descendants().length, 'nodes');
        }

        // ═══════════════════════════════════════════════════════════
        // CIRCLE PACKING LAYOUT
        // Nested circles by directory hierarchy
        // ═══════════════════════════════════════════════════════════

        function renderCirclePackingLayout() {
            if (!explorerData) return;

            const container = document.getElementById('explorer-wrapper');
            const svg = d3.select('#explorer-graph');
            const width = container.clientWidth;
            const height = container.clientHeight || 600;
            svg.attr('width', width).attr('height', height);

            const g = svg.append('g')
                .attr('transform', `translate(${width/2},${height/2})`);

            // Build hierarchy
            const root = buildHierarchy(explorerData.nodes);
            root.sum(d => d.data && d.data.cooccur ? d.data.cooccur + 1 : 1);

            // Create pack layout
            const pack = d3.pack()
                .size([Math.min(width, height) - 40, Math.min(width, height) - 40])
                .padding(3);

            pack(root);

            // Extension colors
            const extColors = {
                '.py': '#7ee787', '.yaml': '#f0883e', '.yml': '#f0883e',
                '.json': '#58a6ff', '.md': '#8b949e', '.html': '#e34c26',
                '.js': '#f1e05a', '.css': '#563d7c', '.sh': '#a371f7'
            };

            // Draw circles
            const node = g.selectAll('circle')
                .data(root.descendants())
                .join('circle')
                .attr('cx', d => d.x - (Math.min(width, height) - 40) / 2)
                .attr('cy', d => d.y - (Math.min(width, height) - 40) / 2)
                .attr('r', d => d.r)
                .attr('fill', d => {
                    if (d.children) return 'none';
                    return extColors[d.data.ext] || '#8b949e';
                })
                .attr('fill-opacity', d => d.children ? 0 : 0.7)
                .attr('stroke', d => d.children ? '#30363d' : 'none')
                .attr('stroke-width', d => d.depth === 1 ? 2 : 1)
                .style('cursor', d => d.children ? 'default' : 'pointer')
                .on('mouseover', function(event, d) {
                    if (d.children) return;
                    d3.select(this)
                        .attr('fill-opacity', 1)
                        .attr('stroke', '#58a6ff')
                        .attr('stroke-width', 2);

                    // Show tooltip
                    const tooltip = d3.select('#tooltip');
                    tooltip.style('display', 'block')
                        .style('left', (event.pageX + 10) + 'px')
                        .style('top', (event.pageY - 10) + 'px')
                        .html(`<strong>${d.data.name}</strong><br/>
                               Path: ${d.data.id || ''}<br/>
                               Activity: ${d.data.data?.cooccur || 0}`);
                })
                .on('mouseout', function(event, d) {
                    if (d.children) return;
                    d3.select(this)
                        .attr('fill-opacity', 0.7)
                        .attr('stroke', 'none');
                    d3.select('#tooltip').style('display', 'none');
                })
                .on('click', function(event, d) {
                    if (d.children) return;
                    event.stopPropagation();
                    d3.select('#tooltip').style('display', 'none');
                    showInsightCard(event, {
                        name: d.data.name,
                        id: d.data.id,
                        count: d.data.data?.cooccur || 1,
                        ext: d.data.ext,
                        type: 'file'
                    });
                });

            // Add labels for large enough circles - smaller font, better truncation
            g.selectAll('text')
                .data(root.leaves().filter(d => d.r > 18))
                .join('text')
                .attr('x', d => d.x - (Math.min(width, height) - 40) / 2)
                .attr('y', d => d.y - (Math.min(width, height) - 40) / 2)
                .attr('text-anchor', 'middle')
                .attr('dy', '0.3em')
                .text(d => {
                    const name = d.data.name;
                    if (d.r > 40) return name.length > 12 ? name.slice(0, 10) + '…' : name;
                    if (d.r > 25) return name.slice(0, 6);
                    return name.slice(0, 3);
                })
                .attr('fill', '#0d1117')
                .attr('font-size', d => Math.min(d.r / 4, 9) + 'px')
                .style('pointer-events', 'none');

            // Zoom
            const zoom = d3.zoom()
                .scaleExtent([0.5, 4])
                .on('zoom', (event) => g.attr('transform', `translate(${width/2 + event.transform.x},${height/2 + event.transform.y}) scale(${event.transform.k})`));
            svg.call(zoom);

            debugLog('Circle Packing: rendered', root.descendants().length, 'nodes');
        }

        // ═══════════════════════════════════════════════════════════
        // SUNBURST LAYOUT
        // Radial hierarchy with arcs
        // ═══════════════════════════════════════════════════════════

        function renderSunburstLayout() {
            if (!explorerData) return;

            const container = document.getElementById('explorer-wrapper');
            const svg = d3.select('#explorer-graph');
            const width = container.clientWidth;
            const height = container.clientHeight || 600;
            svg.attr('width', width).attr('height', height);

            const radius = Math.min(width, height) / 2 - 10;

            const g = svg.append('g')
                .attr('transform', `translate(${width/2},${height/2})`);

            // Build hierarchy
            const root = buildHierarchy(explorerData.nodes);
            root.sum(d => d.data && d.data.cooccur ? d.data.cooccur + 1 : 1);

            // Create partition layout
            const partition = d3.partition()
                .size([2 * Math.PI, radius]);

            partition(root);

            // Extension colors
            const extColors = {
                '.py': '#7ee787', '.yaml': '#f0883e', '.yml': '#f0883e',
                '.json': '#58a6ff', '.md': '#8b949e', '.html': '#e34c26',
                '.js': '#f1e05a', '.css': '#563d7c', '.sh': '#a371f7'
            };

            // Color scale for directories
            const dirColor = d3.scaleOrdinal()
                .domain(root.descendants().filter(d => d.depth === 1).map(d => d.data.name))
                .range(['#ff6b6b', '#4ecdc4', '#ffe66d', '#7b6d8d', '#f4a261', '#a8dadc', '#e76f51']);

            // Arc generator
            const arc = d3.arc()
                .startAngle(d => d.x0)
                .endAngle(d => d.x1)
                .padAngle(d => Math.min((d.x1 - d.x0) / 2, 0.005))
                .padRadius(radius / 2)
                .innerRadius(d => d.y0)
                .outerRadius(d => d.y1 - 1);

            // Draw arcs
            const path = g.selectAll('path')
                .data(root.descendants().filter(d => d.depth))
                .join('path')
                .attr('d', arc)
                .attr('fill', d => {
                    if (!d.children) return extColors[d.data.ext] || '#8b949e';
                    // For directories, use ancestor color
                    let node = d;
                    while (node.depth > 1) node = node.parent;
                    return dirColor(node.data.name);
                })
                .attr('fill-opacity', d => d.children ? 0.6 : 0.85)
                .attr('stroke', '#0d1117')
                .attr('stroke-width', 0.5)
                .style('cursor', 'pointer')
                .on('mouseover', function(event, d) {
                    d3.select(this)
                        .attr('fill-opacity', 1)
                        .attr('stroke', '#58a6ff')
                        .attr('stroke-width', 2);

                    // Highlight ancestors
                    const ancestors = d.ancestors();
                    g.selectAll('path')
                        .attr('fill-opacity', node =>
                            ancestors.includes(node) || node === d ? 1 : 0.3
                        );

                    // Show tooltip with full path
                    const tooltip = d3.select('#tooltip');
                    tooltip.style('display', 'block')
                        .style('left', (event.pageX + 10) + 'px')
                        .style('top', (event.pageY - 10) + 'px')
                        .html(`<strong>${d.data.name}</strong><br/>
                               <span style="color:#8b949e;font-size:10px;">Path: ${d.data.id || ''}</span><br/>
                               Activity: ${d.data.data?.cooccur || 0}`);
                })
                .on('mouseout', function() {
                    g.selectAll('path')
                        .attr('fill-opacity', d => d.children ? 0.6 : 0.85)
                        .attr('stroke', '#0d1117')
                        .attr('stroke-width', 0.5);
                    d3.select('#tooltip').style('display', 'none');
                })
                .on('click', function(event, d) {
                    if (d.children) return;  // Only files, not directories
                    event.stopPropagation();
                    d3.select('#tooltip').style('display', 'none');
                    showInsightCard(event, {
                        name: d.data.name,
                        id: d.data.id,
                        count: d.data.data?.cooccur || 1,
                        ext: d.data.ext,
                        type: 'file'
                    });
                });

            // Add labels for large arcs - smaller font
            g.selectAll('text')
                .data(root.descendants().filter(d => d.depth && (d.y1 - d.y0) > 20 && (d.x1 - d.x0) > 0.08))
                .join('text')
                .attr('transform', d => {
                    const x = (d.x0 + d.x1) / 2 * 180 / Math.PI;
                    const y = (d.y0 + d.y1) / 2;
                    return `rotate(${x - 90}) translate(${y},0) rotate(${x < 180 ? 0 : 180})`;
                })
                .attr('dy', '0.35em')
                .attr('text-anchor', 'middle')
                .text(d => {
                    const name = d.data.name;
                    return name.length > 8 ? name.slice(0, 6) + '…' : name;
                })
                .attr('fill', d => d.children ? '#c9d1d9' : '#0d1117')
                .attr('font-size', '7px')
                .style('pointer-events', 'none');

            // Zoom
            const zoom = d3.zoom()
                .scaleExtent([0.5, 4])
                .on('zoom', (event) => g.attr('transform', `translate(${width/2 + event.transform.x},${height/2 + event.transform.y}) scale(${event.transform.k})`));
            svg.call(zoom);

            debugLog('Sunburst: rendered', root.descendants().length, 'nodes');
        }

        // ═══════════════════════════════════════════════════════════
        // GRID LAYOUT
        // Ultra-organized rows and columns by directory
        // ═══════════════════════════════════════════════════════════

        function renderGridLayout() {
            if (!explorerData) return;

            const container = document.getElementById('explorer-wrapper');
            const svg = d3.select('#explorer-graph');
            const width = container.clientWidth;
            const height = container.clientHeight || 600;
            svg.attr('width', width).attr('height', height);

            const g = svg.append('g')
                .attr('transform', 'translate(20, 20)');

            // Group nodes by top-level directory
            const dirGroups = {};
            explorerData.nodes.forEach(node => {
                const parts = node.id.split('/');
                const topDir = parts.length > 1 ? parts[0] : 'root';
                if (!dirGroups[topDir]) dirGroups[topDir] = [];
                dirGroups[topDir].push(node);
            });

            // Extension colors
            const extColors = {
                '.py': '#7ee787', '.yaml': '#f0883e', '.yml': '#f0883e',
                '.json': '#58a6ff', '.md': '#8b949e', '.html': '#e34c26',
                '.js': '#f1e05a', '.css': '#563d7c', '.sh': '#a371f7'
            };

            // Directory colors
            const dirColors = ['#ff6b6b', '#4ecdc4', '#ffe66d', '#7b6d8d', '#f4a261', '#a8dadc', '#e76f51'];

            const cellSize = 24;
            const cellPadding = 4;
            const groupPadding = 30;
            const labelHeight = 25;

            let currentY = 0;
            const dirs = Object.keys(dirGroups).sort();

            dirs.forEach((dir, dirIdx) => {
                const nodes = dirGroups[dir].sort((a, b) => a.name.localeCompare(b.name));
                const cols = Math.ceil(Math.sqrt(nodes.length * 2));
                const rows = Math.ceil(nodes.length / cols);

                // Directory label
                g.append('text')
                    .attr('x', 0)
                    .attr('y', currentY + 15)
                    .text(dir + '/')
                    .attr('fill', dirColors[dirIdx % dirColors.length])
                    .attr('font-size', '13px')
                    .attr('font-weight', '600');

                currentY += labelHeight;

                // Grid of files
                const dirGroup = g.append('g')
                    .attr('transform', `translate(0, ${currentY})`);

                nodes.forEach((node, i) => {
                    const col = i % cols;
                    const row = Math.floor(i / cols);
                    const x = col * (cellSize + cellPadding);
                    const y = row * (cellSize + cellPadding);
                    const ext = '.' + (node.name.split('.').pop() || '');

                    const cell = dirGroup.append('g')
                        .attr('transform', `translate(${x}, ${y})`)
                        .style('cursor', 'pointer');

                    cell.append('rect')
                        .attr('class', 'node-shape')
                        .attr('width', cellSize)
                        .attr('height', cellSize)
                        .attr('rx', 3)
                        .attr('fill', extColors[ext] || '#8b949e')
                        .attr('fill-opacity', 0.7)
                        .attr('stroke', 'none');

                    cell.append('text')
                        .attr('x', cellSize / 2)
                        .attr('y', cellSize / 2 + 3)
                        .attr('text-anchor', 'middle')
                        .text(node.name.slice(0, 2))
                        .attr('fill', '#0d1117')
                        .attr('font-size', '9px')
                        .attr('font-weight', '500');

                    cell.on('mouseover', function(event) {
                        d3.select(this).select('rect')
                            .attr('fill-opacity', 1)
                            .attr('stroke', '#58a6ff')
                            .attr('stroke-width', 2);

                        const tooltip = d3.select('#tooltip');
                        tooltip.style('display', 'block')
                            .style('left', (event.pageX + 10) + 'px')
                            .style('top', (event.pageY - 10) + 'px')
                            .html(`<strong>${node.name}</strong><br/>
                                   Path: ${node.id}<br/>
                                   Activity: ${node.cooccur || 0}`);
                    })
                    .on('mouseout', function() {
                        d3.select(this).select('rect')
                            .attr('fill-opacity', 0.7)
                            .attr('stroke', 'none');
                        d3.select('#tooltip').style('display', 'none');
                    })
                    .on('click', function(event) {
                        event.stopPropagation();
                        d3.select('#tooltip').style('display', 'none');
                        showInsightCard(event, {
                            name: node.name,
                            id: node.id,
                            count: node.cooccur || 1,
                            ext: ext,
                            type: 'file'
                        });
                    });
                });

                currentY += rows * (cellSize + cellPadding) + groupPadding;
            });

            // Zoom
            const zoom = d3.zoom()
                .scaleExtent([0.5, 4])
                .on('zoom', (event) => g.attr('transform', `translate(${20 + event.transform.x}, ${20 + event.transform.y}) scale(${event.transform.k})`));
            svg.call(zoom);

            debugLog('Grid: rendered', explorerData.nodes.length, 'nodes in', dirs.length, 'directories');
        }

        // ═══════════════════════════════════════════════════════════
        // STORY MODE LAYOUTS
        // Alternative organized views for the Story timeline
        // ═══════════════════════════════════════════════════════════

        // Story Force Layout - default, already rendered at page load
        function renderStoryForceLayout() {
            // The default force layout is rendered at page load
            // Just need to re-initialize if cleared
            debugLog('Story Force Layout: using existing initialization');
            // Re-run the initial story mode setup if needed
            if (!window.storyNode) {
                // Initial render happens at load - nothing to do here
                debugLog('Story nodes already rendered at page load');
            }
        }

        // Story Edge Bundling Layout
        function renderStoryEdgeBundlingLayout() {
            const container = document.getElementById('graph-wrapper');
            const svg = d3.select('#graph');
            const width = container.clientWidth || 800;
            const height = container.clientHeight || 600;
            svg.attr('width', width).attr('height', height);

            const g = svg.append('g')
                .attr('transform', `translate(${width/2},${height/2})`);

            // Build hierarchy from graphData nodes
            const root = buildStoryHierarchy(graphData.nodes);
            const radius = Math.min(width, height) / 2 - 100;

            const cluster = d3.cluster().size([360, radius]);
            cluster(root);

            const leaves = root.leaves();
            const nodeById = {};
            leaves.forEach(d => { nodeById[d.data.id] = d; });

            // Extension colors
            const extColors = {
                '.py': '#7ee787', '.yaml': '#f0883e', '.yml': '#f0883e',
                '.json': '#58a6ff', '.md': '#8b949e', '.html': '#e34c26',
                '.js': '#f1e05a', '.css': '#563d7c', '.sh': '#a371f7'
            };

            // Draw bundled edges
            const line = d3.lineRadial()
                .curve(d3.curveBundle.beta(0.85))
                .radius(d => d.y)
                .angle(d => d.x * Math.PI / 180);

            const edges = graphData.edges.filter(e =>
                nodeById[e.source] && nodeById[e.target]
            );

            g.append('g').attr('class', 'story-bundled-edges')
                .selectAll('path')
                .data(edges)
                .join('path')
                .attr('d', d => {
                    const source = nodeById[d.source];
                    const target = nodeById[d.target];
                    if (!source || !target) return '';
                    return line(source.path(target));
                })
                .attr('fill', 'none')
                .attr('stroke', '#30363d')
                .attr('stroke-opacity', 0.3)
                .attr('stroke-width', 1);

            // Draw nodes
            window.storyNode = g.append('g').attr('class', 'story-bundled-nodes')
                .selectAll('g')
                .data(leaves)
                .join('g')
                .attr('class', 'story-node')
                .attr('data-id', d => d.data.id)
                .attr('transform', d => `rotate(${d.x - 90}) translate(${d.y},0)`);

            window.storyNode.append('circle')
                .attr('class', 'node-shape')
                .attr('r', d => Math.sqrt((d.data.count || 1) * 3) + 4)
                .attr('fill', d => d.data.type === 'tool' ? '#a371f7' : (extColors[d.data.ext] || '#58a6ff'))
                .style('opacity', d => d.data.tier === 'star' ? 1 : d.data.tier === 'context' ? 0.3 : 0.08)
                .style('cursor', 'pointer');

            window.storyNode.append('text')
                .attr('dy', '0.31em')
                .attr('x', d => d.x < 180 ? 8 : -8)
                .attr('text-anchor', d => d.x < 180 ? 'start' : 'end')
                .attr('transform', d => d.x >= 180 ? 'rotate(180)' : null)
                .text(d => {
                    const name = d.data.id.split(':').pop().split('/').pop() || d.data.id;
                    return name.length > 10 ? name.slice(0, 8) + '…' : name;
                })
                .attr('fill', '#c9d1d9')
                .attr('font-size', '7px')
                .style('opacity', d => d.data.tier === 'star' ? 1 : 0)
                .style('pointer-events', 'none');

            window.storyNode.on('mouseover', (event, d) => {
                const tooltip = d3.select('#tooltip');
                const name = d.data.id.split(':').pop() || d.data.id;
                tooltip.style('display', 'block')
                    .style('left', (event.pageX + 10) + 'px')
                    .style('top', (event.pageY - 10) + 'px')
                    .html(`<strong>${name.split('/').pop()}</strong><br/>
                           <span style="color:#8b949e;font-size:10px;">Path: ${name}</span><br/>
                           Interactions: ${d.data.count || 0}`);
            })
            .on('mouseout', () => d3.select('#tooltip').style('display', 'none'))
            .on('click', (event, d) => {
                event.stopPropagation();
                d3.select('#tooltip').style('display', 'none');
                showInsightCard(event, d.data);
            });

            // Zoom
            const zoom = d3.zoom()
                .scaleExtent([0.3, 3])
                .on('zoom', (event) => g.attr('transform', `translate(${width/2 + event.transform.x},${height/2 + event.transform.y}) scale(${event.transform.k})`));
            svg.call(zoom);

            debugLog('Story Edge Bundling: rendered', leaves.length, 'nodes');
        }

        // Story Treemap Layout
        function renderStoryTreemapLayout() {
            const container = document.getElementById('graph-wrapper');
            const svg = d3.select('#graph');
            const width = container.clientWidth || 800;
            const height = container.clientHeight || 600;
            svg.attr('width', width).attr('height', height);

            const g = svg.append('g');

            const root = buildStoryHierarchy(graphData.nodes);
            root.sum(d => d.count || 1);

            const treemap = d3.treemap()
                .size([width - 20, height - 20])
                .paddingOuter(3)
                .paddingTop(19)
                .paddingInner(2)
                .round(true);

            treemap(root);

            const extColors = {
                '.py': '#7ee787', '.yaml': '#f0883e', '.json': '#58a6ff',
                '.md': '#8b949e', '.html': '#e34c26', '.js': '#f1e05a'
            };

            window.storyNode = g.selectAll('g')
                .data(root.descendants())
                .join('g')
                .attr('class', 'story-node')
                .attr('data-id', d => d.data.id)
                .attr('transform', d => `translate(${d.x0 + 10},${d.y0 + 10})`);

            window.storyNode.append('rect')
                .attr('class', 'node-shape')
                .attr('width', d => Math.max(0, d.x1 - d.x0))
                .attr('height', d => Math.max(0, d.y1 - d.y0))
                .attr('fill', d => d.children ? '#21262d' : (d.data.type === 'tool' ? '#a371f7' : extColors[d.data.ext] || '#58a6ff'))
                .attr('fill-opacity', d => d.children ? 0.3 : 0.7)
                .attr('stroke', '#30363d')
                .attr('rx', 2)
                .style('cursor', d => d.children ? 'default' : 'pointer');

            window.storyNode.append('text')
                .attr('x', 4)
                .attr('y', d => d.children ? 14 : (d.y1 - d.y0) / 2 + 3)
                .text(d => {
                    const w = d.x1 - d.x0;
                    const h = d.y1 - d.y0;
                    const name = d.data.id?.split(':').pop().split('/').pop() || '';
                    if (w < 25 || h < 16) return '';
                    if (w < 50) return name.slice(0, 2);
                    if (w < 80) return name.slice(0, 5);
                    return name.length > 10 ? name.slice(0, 8) + '…' : name;
                })
                .attr('fill', d => d.children ? '#8b949e' : '#0d1117')
                .attr('font-size', d => d.children ? '9px' : '7px')
                .style('pointer-events', 'none');

            window.storyNode.filter(d => !d.children)
                .on('mouseover', (event, d) => {
                    const tooltip = d3.select('#tooltip');
                    const name = d.data.id?.split(':').pop() || d.data.id;
                    tooltip.style('display', 'block')
                        .style('left', (event.pageX + 10) + 'px')
                        .style('top', (event.pageY - 10) + 'px')
                        .html(`<strong>${name?.split('/').pop()}</strong><br/>
                               <span style="color:#8b949e;font-size:10px;">Path: ${name}</span><br/>
                               Interactions: ${d.data.count || 0}`);
                })
                .on('mouseout', () => d3.select('#tooltip').style('display', 'none'))
                .on('click', (event, d) => {
                    event.stopPropagation();
                    d3.select('#tooltip').style('display', 'none');
                    showInsightCard(event, d.data);
                });

            const zoom = d3.zoom()
                .scaleExtent([0.5, 4])
                .on('zoom', (event) => g.attr('transform', event.transform));
            svg.call(zoom);

            debugLog('Story Treemap: rendered', root.descendants().length, 'nodes');
        }

        // Story Circle Packing Layout
        function renderStoryCirclePackingLayout() {
            const container = document.getElementById('graph-wrapper');
            const svg = d3.select('#graph');
            const width = container.clientWidth || 800;
            const height = container.clientHeight || 600;
            svg.attr('width', width).attr('height', height);

            const g = svg.append('g')
                .attr('transform', `translate(${width/2},${height/2})`);

            const root = buildStoryHierarchy(graphData.nodes);
            root.sum(d => d.count || 1);

            const pack = d3.pack()
                .size([Math.min(width, height) - 40, Math.min(width, height) - 40])
                .padding(3);

            pack(root);

            const extColors = {
                '.py': '#7ee787', '.yaml': '#f0883e', '.json': '#58a6ff',
                '.md': '#8b949e', '.js': '#f1e05a'
            };

            const offset = (Math.min(width, height) - 40) / 2;

            window.storyNode = g.selectAll('circle')
                .data(root.descendants())
                .join('circle')
                .attr('class', 'story-node')
                .attr('data-id', d => d.data.id)
                .attr('cx', d => d.x - offset)
                .attr('cy', d => d.y - offset)
                .attr('r', d => d.r)
                .attr('fill', d => d.children ? 'none' : (d.data.type === 'tool' ? '#a371f7' : extColors[d.data.ext] || '#58a6ff'))
                .attr('fill-opacity', d => d.children ? 0 : 0.7)
                .attr('stroke', d => d.children ? '#30363d' : 'none')
                .style('cursor', d => d.children ? 'default' : 'pointer')
                .on('mouseover', function(event, d) {
                    if (d.children) return;
                    d3.select(this).attr('fill-opacity', 1).attr('stroke', '#58a6ff').attr('stroke-width', 2);
                    const tooltip = d3.select('#tooltip');
                    const name = d.data.id?.split(':').pop() || d.data.id;
                    tooltip.style('display', 'block')
                        .style('left', (event.pageX + 10) + 'px')
                        .style('top', (event.pageY - 10) + 'px')
                        .html(`<strong>${name?.split('/').pop()}</strong><br/>
                               <span style="color:#8b949e;font-size:10px;">Path: ${name}</span><br/>
                               Interactions: ${d.data.count || 0}`);
                })
                .on('mouseout', function(event, d) {
                    if (d.children) return;
                    d3.select(this).attr('fill-opacity', 0.7).attr('stroke', 'none');
                    d3.select('#tooltip').style('display', 'none');
                })
                .on('click', function(event, d) {
                    if (d.children) return;
                    event.stopPropagation();
                    d3.select('#tooltip').style('display', 'none');
                    showInsightCard(event, d.data);
                });

            const zoom = d3.zoom()
                .scaleExtent([0.5, 4])
                .on('zoom', (event) => g.attr('transform', `translate(${width/2 + event.transform.x},${height/2 + event.transform.y}) scale(${event.transform.k})`));
            svg.call(zoom);

            debugLog('Story Circle Packing: rendered', root.descendants().length, 'nodes');
        }

        // Story Sunburst Layout
        function renderStorySunburstLayout() {
            const container = document.getElementById('graph-wrapper');
            const svg = d3.select('#graph');
            const width = container.clientWidth || 800;
            const height = container.clientHeight || 600;
            svg.attr('width', width).attr('height', height);

            const radius = Math.min(width, height) / 2 - 10;
            const g = svg.append('g')
                .attr('transform', `translate(${width/2},${height/2})`);

            const root = buildStoryHierarchy(graphData.nodes);
            root.sum(d => d.count || 1);

            const partition = d3.partition().size([2 * Math.PI, radius]);
            partition(root);

            const extColors = {
                '.py': '#7ee787', '.yaml': '#f0883e', '.json': '#58a6ff',
                '.md': '#8b949e', '.js': '#f1e05a'
            };

            const arc = d3.arc()
                .startAngle(d => d.x0)
                .endAngle(d => d.x1)
                .padAngle(d => Math.min((d.x1 - d.x0) / 2, 0.005))
                .padRadius(radius / 2)
                .innerRadius(d => d.y0)
                .outerRadius(d => d.y1 - 1);

            window.storyNode = g.selectAll('path')
                .data(root.descendants().filter(d => d.depth))
                .join('path')
                .attr('class', 'story-node')
                .attr('data-id', d => d.data.id)
                .attr('d', arc)
                .attr('fill', d => d.children ? '#30363d' : (d.data.type === 'tool' ? '#a371f7' : extColors[d.data.ext] || '#58a6ff'))
                .attr('fill-opacity', d => d.children ? 0.5 : 0.8)
                .attr('stroke', '#0d1117')
                .style('cursor', 'pointer')
                .on('mouseover', function(event, d) {
                    d3.select(this).attr('fill-opacity', 1).attr('stroke', '#58a6ff').attr('stroke-width', 2);
                    const tooltip = d3.select('#tooltip');
                    const name = d.data.id?.split(':').pop() || d.data.id;
                    tooltip.style('display', 'block')
                        .style('left', (event.pageX + 10) + 'px')
                        .style('top', (event.pageY - 10) + 'px')
                        .html(`<strong>${name?.split('/').pop()}</strong><br/>
                               <span style="color:#8b949e;font-size:10px;">Path: ${name}</span><br/>
                               Interactions: ${d.data.count || 0}`);
                })
                .on('mouseout', function(event, d) {
                    d3.select(this).attr('fill-opacity', d.children ? 0.5 : 0.8).attr('stroke', '#0d1117').attr('stroke-width', 1);
                    d3.select('#tooltip').style('display', 'none');
                })
                .on('click', function(event, d) {
                    if (d.children) return;
                    event.stopPropagation();
                    d3.select('#tooltip').style('display', 'none');
                    showInsightCard(event, d.data);
                });

            const zoom = d3.zoom()
                .scaleExtent([0.5, 4])
                .on('zoom', (event) => g.attr('transform', `translate(${width/2 + event.transform.x},${height/2 + event.transform.y}) scale(${event.transform.k})`));
            svg.call(zoom);

            debugLog('Story Sunburst: rendered', root.descendants().length, 'nodes');
        }

        // Story Grid Layout
        function renderStoryGridLayout() {
            const container = document.getElementById('graph-wrapper');
            const svg = d3.select('#graph');
            const width = container.clientWidth || 800;
            const height = container.clientHeight || 600;
            svg.attr('width', width).attr('height', height);

            const g = svg.append('g').attr('transform', 'translate(20, 20)');

            // Group by type (tool vs file)
            const tools = graphData.nodes.filter(n => n.type === 'tool');
            const files = graphData.nodes.filter(n => n.type !== 'tool');

            const extColors = {
                '.py': '#7ee787', '.yaml': '#f0883e', '.json': '#58a6ff',
                '.md': '#8b949e', '.js': '#f1e05a'
            };

            const cellSize = 28;
            const cellPadding = 4;
            let currentY = 0;

            // Tools section
            if (tools.length > 0) {
                g.append('text')
                    .attr('x', 0)
                    .attr('y', currentY + 15)
                    .text('Tools')
                    .attr('fill', '#a371f7')
                    .attr('font-size', '13px')
                    .attr('font-weight', '600');
                currentY += 25;

                const toolCols = Math.ceil(Math.sqrt(tools.length * 3));
                tools.forEach((node, i) => {
                    const col = i % toolCols;
                    const row = Math.floor(i / toolCols);

                    const cell = g.append('g')
                        .attr('class', 'story-node')
                        .attr('data-id', node.id)
                        .attr('transform', `translate(${col * (cellSize + cellPadding)}, ${currentY + row * (cellSize + cellPadding)})`)
                        .style('cursor', 'pointer');

                    cell.append('rect')
                        .attr('class', 'node-shape')
                        .attr('width', cellSize)
                        .attr('height', cellSize)
                        .attr('rx', 3)
                        .attr('fill', '#a371f7')
                        .attr('fill-opacity', 0.7);

                    cell.append('text')
                        .attr('x', cellSize / 2)
                        .attr('y', cellSize / 2 + 3)
                        .attr('text-anchor', 'middle')
                        .text(node.id.replace('tool:', '').slice(0, 2))
                        .attr('fill', '#fff')
                        .attr('font-size', '8px')
                        .style('pointer-events', 'none');

                    cell.on('mouseover', (event) => {
                        cell.select('rect').attr('fill-opacity', 1).attr('stroke', '#58a6ff').attr('stroke-width', 2);
                        const tooltip = d3.select('#tooltip');
                        const name = node.id.replace('tool:', '');
                        tooltip.style('display', 'block')
                            .style('left', (event.pageX + 10) + 'px')
                            .style('top', (event.pageY - 10) + 'px')
                            .html(`<strong>🔧 ${name}</strong><br/>
                                   <span style="color:#8b949e;font-size:10px;">Type: Tool</span><br/>
                                   Interactions: ${node.count || 0}`);
                    })
                    .on('mouseout', () => {
                        cell.select('rect').attr('fill-opacity', 0.7).attr('stroke', 'none');
                        d3.select('#tooltip').style('display', 'none');
                    })
                    .on('click', (event) => {
                        event.stopPropagation();
                        d3.select('#tooltip').style('display', 'none');
                        showInsightCard(event, node);
                    });
                });
                currentY += Math.ceil(tools.length / Math.ceil(Math.sqrt(tools.length * 3))) * (cellSize + cellPadding) + 30;
            }

            // Files section
            if (files.length > 0) {
                g.append('text')
                    .attr('x', 0)
                    .attr('y', currentY + 15)
                    .text('Files')
                    .attr('fill', '#58a6ff')
                    .attr('font-size', '13px')
                    .attr('font-weight', '600');
                currentY += 25;

                const fileCols = Math.ceil(Math.sqrt(files.length * 2));
                files.forEach((node, i) => {
                    const col = i % fileCols;
                    const row = Math.floor(i / fileCols);
                    const ext = '.' + (node.id.split('.').pop() || '');

                    const cell = g.append('g')
                        .attr('class', 'story-node')
                        .attr('data-id', node.id)
                        .attr('transform', `translate(${col * (cellSize + cellPadding)}, ${currentY + row * (cellSize + cellPadding)})`)
                        .style('cursor', 'pointer');

                    cell.append('rect')
                        .attr('class', 'node-shape')
                        .attr('width', cellSize)
                        .attr('height', cellSize)
                        .attr('rx', 3)
                        .attr('fill', extColors[ext] || '#58a6ff')
                        .attr('fill-opacity', 0.7);

                    cell.append('text')
                        .attr('x', cellSize / 2)
                        .attr('y', cellSize / 2 + 3)
                        .attr('text-anchor', 'middle')
                        .text(node.id.split('/').pop()?.slice(0, 2) || node.id.slice(0, 2))
                        .attr('fill', '#0d1117')
                        .attr('font-size', '8px')
                        .style('pointer-events', 'none');

                    cell.on('mouseover', (event) => {
                        cell.select('rect').attr('fill-opacity', 1).attr('stroke', '#58a6ff').attr('stroke-width', 2);
                        const tooltip = d3.select('#tooltip');
                        const name = node.id.split(':').pop() || node.id;
                        tooltip.style('display', 'block')
                            .style('left', (event.pageX + 10) + 'px')
                            .style('top', (event.pageY - 10) + 'px')
                            .html(`<strong>${name.split('/').pop()}</strong><br/>
                                   <span style="color:#8b949e;font-size:10px;">Path: ${name}</span><br/>
                                   Interactions: ${node.count || 0}`);
                    })
                    .on('mouseout', () => {
                        cell.select('rect').attr('fill-opacity', 0.7).attr('stroke', 'none');
                        d3.select('#tooltip').style('display', 'none');
                    })
                    .on('click', (event) => {
                        event.stopPropagation();
                        d3.select('#tooltip').style('display', 'none');
                        showInsightCard(event, node);
                    });
                });
            }

            // Store reference for timeline updates
            window.storyNode = g.selectAll('.story-node');

            const zoom = d3.zoom()
                .scaleExtent([0.5, 4])
                .on('zoom', (event) => g.attr('transform', `translate(${20 + event.transform.x}, ${20 + event.transform.y}) scale(${event.transform.k})`));
            svg.call(zoom);

            debugLog('Story Grid: rendered', graphData.nodes.length, 'nodes');
        }

        // Helper: Build hierarchy from Story mode nodes
        function buildStoryHierarchy(nodes) {
            const root = { name: 'root', children: [], id: 'root' };

            // Group by type first (tools vs files)
            const tools = nodes.filter(n => n.type === 'tool');
            const files = nodes.filter(n => n.type !== 'tool');

            if (tools.length > 0) {
                root.children.push({
                    name: 'tools',
                    id: 'tools',
                    children: tools.map(n => ({ ...n, name: n.id }))
                });
            }

            if (files.length > 0) {
                root.children.push({
                    name: 'files',
                    id: 'files',
                    children: files.map(n => ({
                        ...n,
                        name: n.id,
                        ext: '.' + (n.id.split('.').pop() || '')
                    }))
                });
            }

            return d3.hierarchy(root);
        }

        // ═══════════════════════════════════════════════════════════
        // EXPLORER FOCUS MODE - Highlight related nodes on click
        // ═══════════════════════════════════════════════════════════

        let focusedNode = null;

        function focusExplorerNode(nodeName) {
            if (!explorerData || !window.explorerNodes) return;

            // If clicking the same node, clear focus
            if (focusedNode === nodeName) {
                clearExplorerFocus();
                return;
            }

            focusedNode = nodeName;

            // Find the node's full path ID from explorerData
            const focusedNodeData = explorerData.nodes.find(n => n.name === nodeName);
            const nodeFullId = focusedNodeData ? focusedNodeData.id : nodeName;

            // Find all related nodes via edges (using full path IDs)
            const relatedNames = new Set([nodeName]);
            (explorerData.edges || []).forEach(edge => {
                const sourceId = typeof edge.source === 'object' ? edge.source.id : edge.source;
                const targetId = typeof edge.target === 'object' ? edge.target.id : edge.target;

                // Match by full path ID, then add the display name to relatedNames
                if (sourceId === nodeFullId) {
                    const targetNode = explorerData.nodes.find(n => n.id === targetId);
                    if (targetNode) relatedNames.add(targetNode.name);
                }
                if (targetId === nodeFullId) {
                    const sourceNode = explorerData.nodes.find(n => n.id === sourceId);
                    if (sourceNode) relatedNames.add(sourceNode.name);
                }
            });

            // ═══════════════════════════════════════════════════════════
            // FOCUS TERRAIN - Related cluster "rises", others "sink"
            // ═══════════════════════════════════════════════════════════

            // Non-related nodes: fade, shrink, no shadow (sink into background)
            window.explorerNodes
                .filter(d => !relatedNames.has(d.name))
                .transition().duration(400).ease(d3.easeCubicOut)
                .style('opacity', 0.12)
                .attr('transform', d => `translate(${d.x},${d.y}) scale(0.7)`);

            // Related nodes: full opacity, slight scale up (rise)
            window.explorerNodes
                .filter(d => relatedNames.has(d.name) && d.name !== nodeName)
                .transition().duration(400).ease(d3.easeCubicOut)
                .style('opacity', 1)
                .attr('transform', d => `translate(${d.x},${d.y}) scale(1.1)`);

            // Related node circles: green border, elevation shadow
            window.explorerNodes
                .filter(d => relatedNames.has(d.name) && d.name !== nodeName)
                .select('circle')
                .transition().duration(400)
                .attr('stroke', '#3fb950')
                .attr('stroke-width', 2.5)
                .style('filter', 'drop-shadow(0 4px 8px rgba(0,0,0,0.5))');

            // Focused node: maximum elevation (largest scale, brightest glow)
            window.explorerNodes
                .filter(d => d.name === nodeName)
                .transition().duration(400).ease(d3.easeCubicOut)
                .style('opacity', 1)
                .attr('transform', d => `translate(${d.x},${d.y}) scale(1.25)`);

            // Focused node circle: blue border, strong elevation shadow + glow
            window.explorerNodes
                .filter(d => d.name === nodeName)
                .select('circle')
                .transition().duration(400)
                .attr('stroke', '#58a6ff')
                .attr('stroke-width', 3)
                .style('filter', 'drop-shadow(0 6px 12px rgba(0,0,0,0.6)) drop-shadow(0 0 12px #58a6ff)');

            // Fade non-related edges, highlight related ones (preserve edge type styling)
            window.explorerLinks
                .transition().duration(400)
                .style('opacity', d => {
                    const sourceId = typeof d.source === 'object' ? d.source.id : d.source;
                    const targetId = typeof d.target === 'object' ? d.target.id : d.target;
                    // Match by full path ID
                    const isRelated = (sourceId === nodeFullId || targetId === nodeFullId);
                    return isRelated ? 1 : 0.05;
                })
                .attr('stroke', d => {
                    const sourceId = typeof d.source === 'object' ? d.source.id : d.source;
                    const targetId = typeof d.target === 'object' ? d.target.id : d.target;
                    // Match by full path ID
                    const isRelated = (sourceId === nodeFullId || targetId === nodeFullId);
                    if (isRelated) {
                        // Highlight related: import=bright cyan, cooccur=blue
                        return (d.edgeType === 'import') ? '#5de4db' : '#58a6ff';
                    } else {
                        // Non-related: import=dim cyan, cooccur=gray
                        return (d.edgeType === 'import') ? '#39c5bb' : '#30363d';
                    }
                });
        }

        function clearExplorerFocus() {
            if (!window.explorerNodes) return;
            focusedNode = null;

            // Restore all nodes - reset scale and opacity
            window.explorerNodes
                .transition().duration(400).ease(d3.easeCubicOut)
                .style('opacity', d => d.heat || 0.4)
                .attr('transform', d => `translate(${d.x},${d.y}) scale(1)`);

            // Restore circle styling
            window.explorerNodes.select('circle')
                .transition().duration(400)
                .attr('stroke', '#30363d')
                .attr('stroke-width', 1.5)
                .style('filter', d => d.phaseCount > 5 ? `drop-shadow(0 0 ${Math.min(d.phaseCount, 10)}px ${extColors[d.ext] || '#8b949e'})` : 'none');

            // Restore all edges (with edge type distinction)
            window.explorerLinks
                .transition().duration(400)
                .style('opacity', d => (d.edgeType === 'import') ? 0.7 : 0.5)
                .attr('stroke', d => (d.edgeType === 'import') ? '#39c5bb' : '#30363d');
        }

        // Clear focus when clicking background or closing card
        document.addEventListener('click', (e) => {
            if (currentMode === 'explorer' && focusedNode) {
                // Check if click was outside nodes and insight card
                if (!e.target.closest('.explorer-node') && !e.target.closest('#insight-card')) {
                    clearExplorerFocus();
                }
            }
        });

        // Also clear on Escape
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape' && focusedNode) {
                clearExplorerFocus();
                closeInsightCard();
            }
        });
