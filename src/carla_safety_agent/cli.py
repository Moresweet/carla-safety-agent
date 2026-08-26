from __future__ import annotations

import argparse
import json
from pathlib import Path

from .carla_adapter import CarlaAdapter
from .generator import GenerationRequest, ScenarioGenerator
from .io import load_specs, save_specs


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(prog="carla-safety-agent")
    commands = root.add_subparsers(dest="command", required=True)
    generate = commands.add_parser("generate", help="generate reproducible scenario specs")
    generate.add_argument("--family", choices=sorted(ScenarioGenerator.SUPPORTED_FAMILIES), default="cut_in")
    generate.add_argument("--map", default="Town04")
    generate.add_argument("--count", type=int, default=10)
    generate.add_argument("--seed", type=int, default=7)
    generate.add_argument("--output", type=Path, required=True)
    run = commands.add_parser("run", help="execute generated specs against a running CARLA server")
    run.add_argument("specs", type=Path)
    run.add_argument("--host", default="127.0.0.1")
    run.add_argument("--port", type=int, default=2000)
    run.add_argument("--output-dir", type=Path, required=True)
    run.add_argument("--limit", type=int)
    return root


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    if args.command == "generate":
        request = GenerationRequest(args.family, args.map, args.count, args.seed)
        specs = ScenarioGenerator().generate(request)
        save_specs(specs, args.output)
        print(json.dumps({"ok": True, "generated": len(specs), "path": str(args.output)}))
        return 0
    specs = load_specs(args.specs)
    if args.limit is not None:
        specs = specs[:args.limit]
    adapter = CarlaAdapter(args.host, args.port)
    results = [adapter.run(spec, args.output_dir).to_dict() for spec in specs]
    results.sort(key=lambda item: item["risk_score"], reverse=True)
    summary = args.output_dir / "results.json"
    summary.parent.mkdir(parents=True, exist_ok=True)
    summary.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(json.dumps({"ok": True, "executed": len(results), "results": str(summary)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
