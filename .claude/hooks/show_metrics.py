#!/usr/bin/env python3
"""
Show Pattern Metrics Dashboard
Usage: python3 show_metrics.py
"""
import sys
import os

# Add hooks directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from pattern_metrics import compute_metrics_summary, format_metrics_report, compute_lesson_metrics, format_lesson_metrics
from state_utils import load_yaml_state


def main():
    print("=" * 60)
    print("   OPERATOR'S EDGE - PATTERN IMPACT DASHBOARD")
    print("=" * 60)
    print()

    # Pattern metrics
    summary = compute_metrics_summary()
    print(format_metrics_report(summary))
    print()

    # Lesson metrics
    state = load_yaml_state()
    if state:
        lesson_metrics = compute_lesson_metrics(state)
        print(format_lesson_metrics(lesson_metrics))
    else:
        print("📚 **Lesson Metrics**: No active_context.yaml found")

    print()
    print("=" * 60)

    # Quick interpretation
    if summary.get("status") == "ok":
        es = summary.get("edit_success", {})
        with_rate = es.get("success_rate_with_patterns")
        without_rate = es.get("success_rate_without_patterns")

        if with_rate is not None and without_rate is not None:
            diff = with_rate - without_rate
            print("\n📈 INTERPRETATION:")
            if diff > 0.1:
                print(f"   ✅ Patterns appear HELPFUL (+{diff:.0%} success rate)")
                print("   → Continue current approach")
            elif diff < -0.1:
                print(f"   ⚠️ Patterns may be UNHELPFUL ({diff:.0%} success rate)")
                print("   → Review pattern relevance and consider simplifying")
            else:
                print("   ➡️ Patterns show NEUTRAL impact")
                print("   → Collect more data before drawing conclusions")


if __name__ == "__main__":
    main()
