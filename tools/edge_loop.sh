#!/bin/bash
# Edge Loop v0.1 - Self-measuring feedback cycle
# Closes the loop: Actions → Proof → Visualizer → Insight → Archive
#
# Usage:
#   ./tools/edge_loop.sh              # Manual run
#   cron: 0 18 * * * /path/to/repo/tools/edge_loop.sh
#   git hook: add to .git/hooks/post-commit

set +e
cd "$(dirname "$0")/.."

echo "═══════════════════════════════════════════════════════════════"
echo "EDGE LOOP - $(date '+%Y-%m-%d %H:%M:%S')"
echo "═══════════════════════════════════════════════════════════════"

EDGE_PORT="${EDGE_PORT:-8080}"
BASE_URL="http://localhost:${EDGE_PORT}"
PROOF_FILE="proof_viz.html"
step_errors=0

warn() {
    echo "⚠️  $1"
    step_errors=$((step_errors+1))
}

run_or_warn() {
    desc="$1"
    shift
    "$@"
    status=$?
    if [ $status -ne 0 ]; then
        warn "${desc} failed (exit ${status})"
    fi
    return $status
}

# Run visualizer with history tracking
echo ""
echo "[1/5] Running Proof Visualizer..."
run_or_warn "Proof visualizer" python3 tools/proof_visualizer.py --history

# Check CTI drift (pure bash, no pandas)
echo ""
echo "[2/5] Checking CTI drift..."
if [ -f .proof/cti_history.csv ] && [ $(wc -l < .proof/cti_history.csv) -gt 2 ]; then
    tail -2 .proof/cti_history.csv | awk -F',' '
        NR==1 {prev=$3}
        NR==2 {
            curr=$3
            diff=prev-curr
            if (diff > 5) {
                printf "⚠️  CTI DRIFT DETECTED: %.1f%% → %.1f%% (down %.1f%%)\n", prev, curr, diff
            } else if (diff > 0) {
                printf "📉 CTI down slightly: %.1f%% → %.1f%%\n", prev, curr
            } else if (diff < 0) {
                printf "📈 CTI improving: %.1f%% → %.1f%%\n", prev, curr
            } else {
                printf "→ CTI stable at %.1f%%\n", curr
            }
        }'
else
    echo "→ Not enough history for drift comparison"
fi

# Archive report
echo ""
echo "[3/5] Archiving report..."
mkdir -p reports
REPORT_FILE="reports/proof_$(date +%F).html"
if [ -f "$REPORT_FILE" ]; then
    REPORT_FILE="reports/proof_$(date +%F_%H%M%S).html"
fi
if [ -f "$PROOF_FILE" ]; then
    cp "$PROOF_FILE" "$REPORT_FILE"
    echo "→ Saved to $REPORT_FILE"
else
    warn "Missing ${PROOF_FILE}; archive skipped"
fi

# Generate digest
echo ""
echo "[4/5] Generating Edge Digest..."
python3 tools/edge_digest.py 2>/dev/null || warn "Digest generation skipped"

# Ensure live server is running (for browser bookmark)
echo ""
echo "[5/5] Checking Edge Server..."
if command -v curl >/dev/null 2>&1; then
    if curl -s -o /dev/null -w "" "${BASE_URL}/proof_viz.html" 2>/dev/null; then
        echo "→ Edge Server running at ${BASE_URL}/proof_viz.html"
    else
        echo "→ Starting Edge Server on port ${EDGE_PORT}..."
        python3 tools/edge_server.py --no-open &
        server_pid=$!
        started=""
        for i in 1 2 3 4 5; do
            sleep 1
            if curl -s -o /dev/null -w "" "${BASE_URL}/proof_viz.html" 2>/dev/null; then
                started="yes"
                break
            fi
        done
        if [ -n "$started" ]; then
            echo "→ Edge Server started at ${BASE_URL}/proof_viz.html"
        else
            warn "Edge Server did not respond at ${BASE_URL}/proof_viz.html"
        fi
    fi
else
    warn "curl not found; skipping Edge Server check"
fi

echo ""
echo "═══════════════════════════════════════════════════════════════"
echo "EDGE LOOP COMPLETE"
echo "═══════════════════════════════════════════════════════════════"
echo ""
echo "Bookmark: ${BASE_URL}/proof_viz.html"
echo "═══════════════════════════════════════════════════════════════"
