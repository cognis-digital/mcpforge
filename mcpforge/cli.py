"""Command-line interface for MCPFORGE.

Subcommands:
  scaffold <spec.json> [--out DIR] [--dry-run]  generate a full MCP project
  lint     <spec.json>                          structural lint of a spec
  simulate <spec.json> [--tool NAME] [--args J] run JSON-RPC against output
  publish  <spec.json>                          emit packaging metadata

Global:
  --version            print tool version
  --format {table,json}

Exit code is non-zero on any failure (bad spec, lint errors, sim failure).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any, List, Optional

from . import TOOL_NAME, TOOL_VERSION
from .core import (
    SpecError,
    lint_spec,
    parse_spec,
    publish_manifest,
    scaffold,
    simulate,
)


def _load_spec(path: str):
    if not os.path.isfile(path):
        raise SpecError(f"spec file not found: {path}")
    with open(path, "r", encoding="utf-8") as fh:
        return parse_spec(fh.read())


def _emit(payload: Any, fmt: str, table_rows: Optional[List[str]] = None) -> None:
    if fmt == "json":
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        if table_rows is not None:
            for row in table_rows:
                print(row)
        else:
            print(json.dumps(payload, indent=2, sort_keys=True))


def _cmd_lint(args, fmt) -> int:
    spec = _load_spec(args.spec)
    report = lint_spec(spec)
    rows = [f"{spec.name}: {len(report['errors'])} error(s), "
            f"{len(report['warnings'])} warning(s)"]
    for e in report["errors"]:
        rows.append(f"  ERROR [{e['code']}] {e['msg']}")
    for w in report["warnings"]:
        rows.append(f"  WARN  [{w['code']}] {w['msg']}")
    _emit(report, fmt, rows)
    return 1 if report["errors"] else 0


def _cmd_scaffold(args, fmt) -> int:
    spec = _load_spec(args.spec)
    report = lint_spec(spec)
    if report["errors"]:
        _emit({"ok": False, "errors": report["errors"]}, fmt,
              [f"refusing to scaffold: {len(report['errors'])} lint error(s)"]
              + [f"  [{e['code']}] {e['msg']}" for e in report["errors"]])
        return 1
    files = scaffold(spec)
    written: List[str] = []
    if not args.dry_run:
        try:
            for rel, content in files.items():
                dest = os.path.join(args.out, rel)
                os.makedirs(os.path.dirname(dest) or ".", exist_ok=True)
                with open(dest, "w", encoding="utf-8") as fh:
                    fh.write(content)
                written.append(dest)
        except OSError as exc:
            raise SpecError(f"cannot write output files: {exc}") from exc
    payload = {"ok": True, "server": spec.name, "out": args.out,
               "files": sorted(files.keys()),
               "written": sorted(written), "dry_run": args.dry_run}
    rows = [f"scaffolded '{spec.name}' → {len(files)} file(s)"
            + (" (dry-run)" if args.dry_run else f" in {args.out}")]
    rows += [f"  {p}" for p in sorted(files.keys())]
    _emit(payload, fmt, rows)
    return 0


def _cmd_simulate(args, fmt) -> int:
    spec = _load_spec(args.spec)
    arguments = None
    if args.args:
        try:
            arguments = json.loads(args.args)
        except json.JSONDecodeError as exc:
            raise SpecError(f"--args is not valid JSON: {exc}") from exc
    result = simulate(spec, tool=args.tool, arguments=arguments)
    rows = [f"simulate '{spec.name}': {'OK' if result['ok'] else 'FAIL'}",
            f"  protocol: {result['protocolVersion']}",
            f"  tools:    {', '.join(result['tools_listed']) or '(none)'}",
            f"  called:   {result['called']}",
            f"  result:   {result['call_result']}"]
    _emit(result, fmt, rows)
    return 0 if result["ok"] else 1


def _cmd_publish(args, fmt) -> int:
    spec = _load_spec(args.spec)
    report = lint_spec(spec)
    if report["errors"]:
        _emit({"ok": False, "errors": report["errors"]}, fmt,
              ["refusing to publish: lint errors present"])
        return 1
    man = publish_manifest(spec)
    rows = [f"publish manifest for '{spec.name}' v{spec.version}",
            "  pyproject.toml + mcp-registry.json generated"]
    _emit({"ok": True, **man}, fmt, rows)
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog=TOOL_NAME,
        description="Scaffold, test, and publish MCP servers in minutes.")
    p.add_argument("--version", action="version",
                   version=f"{TOOL_NAME} {TOOL_VERSION}")
    p.add_argument("--format", choices=("table", "json"), default="table")
    sub = p.add_subparsers(dest="cmd", required=True)

    sp = sub.add_parser("scaffold", help="generate a full MCP server project")
    sp.add_argument("spec")
    sp.add_argument("--out", default=".")
    sp.add_argument("--dry-run", action="store_true")
    sp.set_defaults(func=_cmd_scaffold)

    lp = sub.add_parser("lint", help="structural lint of a server spec")
    lp.add_argument("spec")
    lp.set_defaults(func=_cmd_lint)

    mp = sub.add_parser("simulate", help="run a JSON-RPC exchange in-process")
    mp.add_argument("spec")
    mp.add_argument("--tool", default=None)
    mp.add_argument("--args", default=None, help="JSON object of arguments")
    mp.set_defaults(func=_cmd_simulate)

    pp = sub.add_parser("publish", help="emit publish-ready packaging metadata")
    pp.add_argument("spec")
    pp.set_defaults(func=_cmd_publish)

    return p


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    fmt = getattr(args, "format", "table")
    try:
        return args.func(args, fmt)
    except SpecError as exc:
        msg = {"ok": False, "error": str(exc)}
        if fmt == "json":
            print(json.dumps(msg, indent=2))
        else:
            print(f"error: {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("interrupted", file=sys.stderr)
        return 130
    except Exception as exc:  # noqa: BLE001
        msg = {"ok": False, "error": f"unexpected error: {exc}"}
        if fmt == "json":
            print(json.dumps(msg, indent=2))
        else:
            print(f"unexpected error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
