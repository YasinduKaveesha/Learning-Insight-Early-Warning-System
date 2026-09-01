"""Gate 15 / decision D16 -- the population crosstab for ``practice_trajectory``.

D16 is a REVIEW GATE, NOT A TEST. This script produces the table; the ML lead signs it off
before merge. It does NOT self-certify.

It computes ``practice_trajectory`` for every supervised-grid snapshot of the full research
population using the SAME code path the decision layer uses
(``app.application.decision_layer.trailing_trajectory``, eps = 0.05, trailing w = 4 over
``b_accuracy_rate``), joins the offline audit labels
(``dataset/audit/t3_audit_labels_*.csv`` -- population TD / MLD / DD), and prints counts and
within-group rates so a ``needs_attention`` lift for DD learners can be read off directly.

The audit CSV is opened HERE and only here -- it never enters the backend database
(rule 3-F1). This file lives under ``scripts/`` precisely so nothing importable by the API
touches it.

    conda run -n c3-ews python -m scripts.d16_practice_trajectory_crosstab
"""

from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict
from pathlib import Path

from app.application.decision_layer import EPSILON_PRACTICE, trailing_trajectory
from app.infrastructure.feature_builder import SUPERVISED_GRID

_REPO_ROOT = Path(__file__).resolve().parents[3]
_SOURCE = _REPO_ROOT / "dataset" / "source" / "so2_joined_dataset_seed20260828_n300.jsonl"
_AUDIT = _REPO_ROOT / "dataset" / "audit" / "t3_audit_labels_seed20260828_n300.csv"

_STATES = ("improving", "stable", "needs_attention", "unknown")


def _load_accuracy_series() -> dict[str, list[tuple[int, float | None]]]:
    series: dict[str, list[tuple[int, float | None]]] = defaultdict(list)
    with _SOURCE.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            m = rec["mapping"]
            sid = m["student_id"]
            n = m["intervention_session_number"]
            b = rec.get("b_to_3") or {}
            acc = b.get("accuracy_rate") if m.get("b_present") else None
            series[sid].append((n, acc))
    return series


def _load_population() -> dict[str, str]:
    with _AUDIT.open(encoding="utf-8") as fh:
        return {row["student_id"]: row["population"] for row in csv.DictReader(fh)}


def main() -> None:
    series = _load_accuracy_series()
    population = _load_population()

    # group -> trajectory -> count. Groups: DD, non-DD, and the raw TD/MLD/DD split.
    grid_counts: dict[str, Counter] = defaultdict(Counter)
    for sid, points in series.items():
        pop = population.get(sid, "UNKNOWN")
        dd_group = "DD" if pop == "DD" else "non-DD"
        for t in SUPERVISED_GRID:
            traj = trailing_trajectory(points, t=t, epsilon=EPSILON_PRACTICE)
            grid_counts[dd_group][traj] += 1
            grid_counts[pop][traj] += 1
            grid_counts["ALL"][traj] += 1

    def _print_block(title: str, groups: list[str]) -> None:
        print(f"\n{title}")
        header = f"{'group':<10}" + "".join(f"{s:>16}" for s in _STATES) + f"{'n':>8}"
        print(header)
        print("-" * len(header))
        for g in groups:
            c = grid_counts[g]
            n = sum(c.values())
            cells = "".join(f"{c[s]:>7} ({c[s]/n:>5.1%})" for s in _STATES)
            print(f"{g:<10}{cells}{n:>8}")

    print("=" * 78)
    print("D16 crosstab -- practice_trajectory x DD-status")
    print(f"population: {len(series)} learners x {len(SUPERVISED_GRID)} supervised-grid "
          f"snapshots = {len(series) * len(SUPERVISED_GRID)} rows")
    print(f"eps_practice = {EPSILON_PRACTICE}, trailing window w = 4, over b_accuracy_rate")
    print("=" * 78)

    _print_block("By DD status (snapshot rows):", ["DD", "non-DD", "ALL"])
    _print_block("By population (snapshot rows):", ["TD", "MLD", "DD", "ALL"])

    all_na = grid_counts["ALL"]["needs_attention"] / sum(grid_counts["ALL"].values())
    dd_na = grid_counts["DD"]["needs_attention"] / sum(grid_counts["DD"].values())
    non_dd_na = grid_counts["non-DD"]["needs_attention"] / sum(grid_counts["non-DD"].values())
    print("\nneeds_attention rates:")
    print(f"  DD        : {dd_na:.4f}")
    print(f"  non-DD    : {non_dd_na:.4f}")
    print(f"  population : {all_na:.4f}")
    print(f"\nDD needs_attention LIFT (DD rate / population rate): {dd_na / all_na:.3f}")
    print("  (a lift well below 1.0 -- in the 0.75-0.99 band -- is the inversion that killed")
    print("   engagement_trajectory. >= ~1.0 means DD learners are surfaced at least as often.)")
    print("\nThis table is for ML-lead review. It is not self-certified.")


if __name__ == "__main__":
    main()
