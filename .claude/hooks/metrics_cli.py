#!/usr/bin/env python3
"""
Operator's Edge v8.0 - Metrics CLI (Phase 7)

The Voice: A beautiful, minimal interface to v8.0 effectiveness data.

Commands:
  /edge metrics           - Show compact effectiveness report
  /edge metrics --detail  - Show detailed breakdown
  /edge metrics --export  - Export raw data as JSON
  /edge metrics --tune    - Apply recommended threshold adjustments

Design Philosophy:
- Information, not noise
- Beauty in simplicity
- Actionable insights

"Design is not just what it looks like and feels like.
 Design is how it works." - Steve Jobs
"""
import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

# Add hooks directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


# =============================================================================
# PATHS
# =============================================================================

def get_proof_dir() -> Path:
    """Get the .proof directory."""
    # Try relative to this file first
    local_proof = Path(__file__).parent.parent.parent / ".proof"
    if local_proof.exists():
        return local_proof

    # Try current directory
    cwd_proof = Path.cwd() / ".proof"
    if cwd_proof.exists():
        return cwd_proof

    # Return local even if doesn't exist (for error messages)
    return local_proof


def get_config_path() -> Path:
    """Get the config file path."""
    return get_proof_dir() / "v8_config.json"


# =============================================================================
# CONFIGURATION
# =============================================================================

DEFAULT_THRESHOLDS = {
    "file_churn": 3,
    "command_repeat": 2,
    "context_checkpoint": 0.75,
    "auto_fix_confidence": 0.6,
}


def load_thresholds() -> dict:
    """Load current thresholds from config."""
    config_path = get_config_path()
    if config_path.exists():
        try:
            with open(config_path) as f:
                config = json.load(f)
                return config.get("thresholds", DEFAULT_THRESHOLDS.copy())
        except (json.JSONDecodeError, OSError):
            pass
    return DEFAULT_THRESHOLDS.copy()


def save_thresholds(thresholds: dict) -> bool:
    """Save thresholds to config."""
    config_path = get_config_path()
    try:
        # Load existing config or create new
        config = {}
        if config_path.exists():
            try:
                with open(config_path) as f:
                    config = json.load(f)
            except (json.JSONDecodeError, OSError):
                pass

        config["thresholds"] = thresholds
        config["last_tuned"] = datetime.now().isoformat()

        # Ensure directory exists
        config_path.parent.mkdir(parents=True, exist_ok=True)

        with open(config_path, 'w') as f:
            json.dump(config, f, indent=2)

        return True
    except OSError:
        return False


# =============================================================================
# COMMANDS
# =============================================================================

def cmd_metrics(args) -> int:
    """Show effectiveness metrics."""
    try:
        from effectiveness_analyzer import (
            generate_effectiveness_report,
            format_compact_report,
            format_detailed_report
        )
    except ImportError as e:
        print(f"Error: Could not import effectiveness analyzer: {e}", file=sys.stderr)
        return 1

    proof_dir = get_proof_dir()
    if not proof_dir.exists():
        print("No .proof directory found. Run some sessions first.", file=sys.stderr)
        return 1

    # Load current thresholds
    thresholds = load_thresholds()

    # Generate report
    days = args.days if hasattr(args, 'days') else 7
    report = generate_effectiveness_report(proof_dir, days=days, current_thresholds=thresholds)

    if report.sessions_analyzed == 0:
        print(f"No sessions found in the last {days} days.", file=sys.stderr)
        print(f"Try: /edge metrics --days 30", file=sys.stderr)
        return 1

    # Output based on format
    if hasattr(args, 'export') and args.export:
        # JSON export
        print(json.dumps(report.to_dict(), indent=2))
    elif hasattr(args, 'detail') and args.detail:
        # Detailed report
        print(format_detailed_report(report))
    else:
        # Compact report (default)
        print(format_compact_report(report))

    return 0


def cmd_tune(args) -> int:
    """Apply recommended threshold adjustments."""
    try:
        from effectiveness_analyzer import generate_effectiveness_report
    except ImportError as e:
        print(f"Error: Could not import effectiveness analyzer: {e}", file=sys.stderr)
        return 1

    proof_dir = get_proof_dir()
    if not proof_dir.exists():
        print("No .proof directory found.", file=sys.stderr)
        return 1

    # Load current thresholds
    current = load_thresholds()

    # Generate report to get recommendations
    report = generate_effectiveness_report(proof_dir, days=30, current_thresholds=current)

    if not report.threshold_adjustments:
        print("✓ No threshold adjustments recommended at this time.")
        print(f"  Based on {report.sessions_analyzed} sessions analyzed.")
        return 0

    # Show proposed changes
    print("🔧 PROPOSED THRESHOLD ADJUSTMENTS")
    print("-" * 40)
    for key, new_value in report.threshold_adjustments.items():
        old_value = current.get(key, "?")
        print(f"  {key}: {old_value} → {new_value}")
    print()

    # In non-interactive mode or with --yes, apply automatically
    if hasattr(args, 'yes') and args.yes:
        apply = True
    else:
        # This would normally prompt, but in hook context we auto-apply
        apply = True

    if apply:
        # Apply adjustments
        updated = current.copy()
        updated.update(report.threshold_adjustments)

        if save_thresholds(updated):
            print("✓ Thresholds updated successfully.")
            print(f"  Changes will take effect in new sessions.")
            return 0
        else:
            print("Error: Failed to save thresholds.", file=sys.stderr)
            return 1

    return 0


def cmd_status(args) -> int:
    """Show v8.0 status."""
    print()
    print("v8.0 CONTEXT ENGINEERING STATUS")
    print("=" * 40)

    # Check modules
    modules = [
        ("drift_detector", "Drift Detection"),
        ("context_monitor", "Context Monitor"),
        ("codebase_knowledge", "Codebase Knowledge"),
        ("session_handoff", "Session Handoff"),
        ("session_metrics", "Session Metrics"),
        ("smart_suggestions", "Smart Suggestions"),
        ("effectiveness_analyzer", "Effectiveness Analyzer"),
        ("course_correction", "Course Correction"),
    ]

    print("\nModules:")
    for module, name in modules:
        try:
            __import__(module)
            print(f"  ✓ {name}")
        except ImportError:
            print(f"  ✗ {name} (not available)")

    # Check data
    proof_dir = get_proof_dir()
    sessions_dir = proof_dir / "sessions"

    print("\nData:")
    if proof_dir.exists():
        print(f"  ✓ .proof directory exists")
        if sessions_dir.exists():
            session_count = len(list(sessions_dir.glob("*.jsonl")))
            print(f"  ✓ {session_count} session logs")
        else:
            print(f"  ✗ No sessions directory")

        knowledge_file = proof_dir / "codebase_knowledge.json"
        if knowledge_file.exists():
            print(f"  ✓ Codebase knowledge exists")
        else:
            print(f"  ○ No codebase knowledge yet")
    else:
        print(f"  ✗ No .proof directory")

    # Check thresholds
    print("\nThresholds:")
    thresholds = load_thresholds()
    for key, value in thresholds.items():
        default = DEFAULT_THRESHOLDS.get(key, "?")
        if value != default:
            print(f"  {key}: {value} (tuned from {default})")
        else:
            print(f"  {key}: {value}")

    print()
    return 0


# =============================================================================
# MAIN
# =============================================================================

def main(argv=None):
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="v8.0 Metrics CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  metrics_cli.py              # Show compact report
  metrics_cli.py --detail     # Show detailed report
  metrics_cli.py --export     # Export as JSON
  metrics_cli.py --tune       # Apply threshold adjustments
  metrics_cli.py --status     # Show v8.0 status
        """
    )

    parser.add_argument(
        "--detail", "-d",
        action="store_true",
        help="Show detailed report"
    )
    parser.add_argument(
        "--export", "-e",
        action="store_true",
        help="Export as JSON"
    )
    parser.add_argument(
        "--tune", "-t",
        action="store_true",
        help="Apply recommended threshold adjustments"
    )
    parser.add_argument(
        "--status", "-s",
        action="store_true",
        help="Show v8.0 status"
    )
    parser.add_argument(
        "--days",
        type=int,
        default=7,
        help="Number of days to analyze (default: 7)"
    )
    parser.add_argument(
        "--yes", "-y",
        action="store_true",
        help="Auto-confirm threshold changes"
    )

    args = parser.parse_args(argv)

    # Route to command
    if args.status:
        return cmd_status(args)
    elif args.tune:
        return cmd_tune(args)
    else:
        return cmd_metrics(args)


# =============================================================================
# INTEGRATION HELPER
# =============================================================================

def get_metrics_summary() -> str:
    """
    Get a one-line metrics summary for injection into other outputs.

    Returns something like: "v8.0: 78% drift effectiveness, 12 sessions"
    """
    try:
        from effectiveness_analyzer import generate_effectiveness_report

        proof_dir = get_proof_dir()
        if not proof_dir.exists():
            return ""

        report = generate_effectiveness_report(proof_dir, days=7)
        if report.sessions_analyzed == 0:
            return ""

        drift_pct = report.drift_effectiveness.value * 100
        return f"v8.0: {drift_pct:.0f}% drift effectiveness ({report.sessions_analyzed} sessions)"

    except ImportError:
        return ""
    except Exception:
        return ""


# =============================================================================
# QUICK TEST
# =============================================================================

if __name__ == "__main__":
    sys.exit(main())
