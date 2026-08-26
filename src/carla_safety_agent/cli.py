from __future__ import annotations

import argparse
import json
from pathlib import Path

from .build_plan import build_plan
from .carla_adapter import CarlaAdapter
from .generator import GenerationRequest, ScenarioGenerator
from .io import load_specs, save_specs
from .natural_language import DescriptionError, NaturalLanguageCompiler


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(prog="carla-safety-agent")
    commands = root.add_subparsers(dest="command", required=True)
    generate = commands.add_parser("generate", help="generate reproducible scenario specs")
    generate.add_argument("--family", choices=sorted(ScenarioGenerator.SUPPORTED_FAMILIES), default="cut_in")
    generate.add_argument("--map", default="Town04")
    generate.add_argument("--count", type=int, default=10)
    generate.add_argument("--seed", type=int, default=7)
    generate.add_argument("--output", type=Path, required=True)
    from_text = commands.add_parser("from-text", help="compile natural language into a scenario JSON file")
    from_text.add_argument("description", nargs="?")
    from_text.add_argument("--file", type=Path, help="read description from a UTF-8 text file")
    from_text.add_argument("--seed", type=int, default=7)
    from_text.add_argument("--output", type=Path, required=True)
    build = commands.add_parser("build", help="validate a scenario and emit its CARLA build plan")
    build.add_argument("specs", type=Path)
    build.add_argument("--output", type=Path, required=True)
    run = commands.add_parser("run", help="execute generated specs against a running CARLA server")
    run.add_argument("specs", type=Path)
    run.add_argument("--host", default="127.0.0.1")
    run.add_argument("--port", type=int, default=2000)
    run.add_argument("--timeout", type=float, default=120.0)
    run.add_argument("--output-dir", type=Path, required=True)
    run.add_argument("--limit", type=int)
    render = commands.add_parser("render", help="build, run and capture RGB frames")
    render.add_argument("specs", type=Path)
    render.add_argument("--host", default="127.0.0.1")
    render.add_argument("--port", type=int, default=2000)
    render.add_argument("--timeout", type=float, default=120.0)
    render.add_argument("--output-dir", type=Path, required=True)
    render.add_argument("--limit", type=int, default=1)
    return root


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    if args.command == "generate":
        request = GenerationRequest(args.family, args.map, args.count, args.seed)
        specs = ScenarioGenerator().generate(request)
        save_specs(specs, args.output)
        print(json.dumps({"ok": True, "generated": len(specs), "path": str(args.output)}))
        return 0
    if args.command == "from-text":
        if bool(args.description) == bool(args.file):
            raise SystemExit("provide exactly one of DESCRIPTION or --file")
        description = args.description or args.file.read_text(encoding="utf-8")
        try:
            compilation = NaturalLanguageCompiler().compile(description, args.seed)
        except DescriptionError as exc:
            print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
            return 2
        save_specs([compilation.scenario], args.output)
        print(json.dumps({
            "ok": True,
            "path": str(args.output),
            "interaction": compilation.scenario.family,
            "warnings": compilation.warnings,
            "extracted": compilation.extracted,
        }, ensure_ascii=False))
        return 0
    if args.command == "build":
        plans = [build_plan(spec).to_dict() for spec in load_specs(args.specs)]
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(plans, indent=2), encoding="utf-8")
        print(json.dumps({"ok": True, "built": len(plans), "path": str(args.output)}))
        return 0
    specs = load_specs(args.specs)
    if args.limit is not None:
        specs = specs[:args.limit]
    adapter = CarlaAdapter(args.host, args.port, args.timeout)
    should_render = args.command == "render"
    results = [adapter.run(spec, args.output_dir, render=should_render).to_dict() for spec in specs]
    results.sort(key=lambda item: item["risk_score"], reverse=True)
    summary = args.output_dir / "results.json"
    summary.parent.mkdir(parents=True, exist_ok=True)
    summary.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(json.dumps({"ok": True, "executed": len(results), "results": str(summary)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
