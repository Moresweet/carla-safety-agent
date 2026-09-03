#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json

from carla_safety_agent.e2e_benchmark import write_failure_report


def main() -> None:
    parser = argparse.ArgumentParser(description="Rank UniAD/Bench2Drive runs by safety criticality")
    parser.add_argument("results", help="Bench2Drive checkpoint JSON")
    parser.add_argument("--output", default="runs/uniad/failure-report.json")
    args = parser.parse_args()
    path = write_failure_report(args.results, args.output)
    report = json.loads(path.read_text(encoding="utf-8"))
    ranked = report["ranked_failures"]
    print(f"Wrote {len(ranked)} ranked routes to {path}")
    for item in ranked[:10]:
        print(f"{item['criticality_score']:8.2f}  {item['route_id']}  {item['scenario_name']}")


if __name__ == "__main__":
    main()
