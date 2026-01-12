#!/usr/bin/env python3
"""
Proof Visualizer - Export Functions
Report generation and CTI history management.
"""
import json
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Optional

from proof_viz_analysis import format_duration
from proof_viz_config import CTI_DRIFT_THRESHOLD


def export_anomaly_report(anomalies: List[Dict], path: Path):
    """Export anomaly report to JSON."""
    report = {
        'timestamp': datetime.now().isoformat(),
        'count': len(anomalies),
        'anomalies': anomalies,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, 'w') as f:
        json.dump(report, f, indent=2)


def export_phase_summary(phases: List[Dict], entries: List[Dict], path: Path):
    """Export phase summary to JSON for external analysis."""
    # Compute intent totals
    intent_counts = {}
    intent_durations = {}
    intent_cti = {}

    for phase in phases:
        intent = phase['intent']
        intent_counts[intent] = intent_counts.get(intent, 0) + phase['count']
        if phase['duration_seconds']:
            intent_durations[intent] = intent_durations.get(intent, 0) + phase['duration_seconds']
        intent_cti.setdefault(intent, []).append(phase['cti'])

    # Compute average CTI per intent
    avg_cti = {}
    for intent, cti_list in intent_cti.items():
        avg_cti[intent] = round(sum(cti_list) / len(cti_list), 1) if cti_list else 0

    summary = {
        'timestamp': datetime.now().isoformat(),
        'total_phases': len(phases),
        'total_events': len(entries),
        'by_intent': {
            intent: {
                'events': intent_counts.get(intent, 0),
                'duration_seconds': intent_durations.get(intent, 0),
                'duration_formatted': format_duration(intent_durations.get(intent)),
                'avg_cti': avg_cti.get(intent, 0),
            }
            for intent in ['exploring', 'building', 'debugging', 'executing', 'mixed']
            if intent_counts.get(intent, 0) > 0
        },
        'phases': [
            {
                'index': i + 1,
                'intent': p['intent'],
                'events': p['count'],
                'duration': p['duration_formatted'],
                'cti': p['cti'],
                'start_time': p['start_time'],
                'end_time': p['end_time'],
            }
            for i, p in enumerate(phases)
        ],
    }

    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, 'w') as f:
        json.dump(summary, f, indent=2)
    return summary


def append_cti_history(history_path: Path, stats: Dict):
    """Append current stats to CTI history."""
    is_new = not history_path.exists()
    with open(history_path, 'a') as f:
        if is_new:
            f.write('timestamp,events,cti,success_rate\n')
        cti_val = float(stats['cti'].rstrip('%'))
        sr_val = float(stats['success_rate'].rstrip('%')) if stats['success_rate'] != 'N/A' else 0
        f.write(f"{datetime.now().isoformat()},{stats['total_events']},{cti_val},{sr_val}\n")


def check_drift(history: List[Dict], current_cti: float, threshold: float = CTI_DRIFT_THRESHOLD) -> Optional[str]:
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
