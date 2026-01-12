# Edge Loop - Close the Feedback Cycle

Run the Edge Loop to close the feedback cycle:
- Generates proof visualization with CTI tracking
- Checks for CTI drift (warns if >5% drop)
- Archives daily report to `reports/`
- Generates Edge Digest (non-fatal)
- Ensures live server is running (honors `EDGE_PORT`)

## Usage

```bash
/edge-loop
```

## What It Does

1. Runs `tools/proof_visualizer.py --history`
2. Checks CTI drift via pure bash (no dependencies)
3. Archives `proof_viz.html` to `reports/proof_YYYY-MM-DD.html`
4. Generates Edge Digest (warn-only on failure)
5. Verifies Edge Server (starts if missing)

## When to Use

- End of work session (manual reflection)
- After completing an objective
- Anytime you want to see the current state

Note: This also runs automatically after `/edge-prune`.

## Instructions

Run the edge loop script:

```bash
bash tools/edge_loop.sh
```

Display the output to the user.

Notes:
- Set `EDGE_PORT` to use a custom port (default 8080).
- If the daily report filename already exists, the loop adds a time suffix.
