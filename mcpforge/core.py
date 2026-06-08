"""Core engine for MCPFORGE.

No third-party imports. Everything here is real, executable logic:

* parse_spec   - load + validate a server spec (JSON) into dataclasses
* lint_spec    - structural lint with actionable error/warning codes
* scaffold     - emit a complete, runnable MCP stdio server + packaging
* simulate     - run a real JSON-RPC initialize + tools/list + tools/call
                 exchange against the *generated* server source in-proc
* publish_manifest - produce publish-ready metadata (pyproject + registry)
"""
from __future__ import annotations

import io
import json
import keyword
import re
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional

_IDENT_RE = re.compile(r"^[a-z][a-z0-9_]*$")
_NAME_RE = re.compile(r"^[a-z][a-z0-9-]*$")
_JSON_TYPES = {"string", "number", "integer", "boolean", "array", "object"}


class SpecError(Exception):
    """Raised when a spec cannot be parsed or is structurally invalid."""


@dataclass
class ToolSpec:
    name: str
    description: str = ""
    params: Dict[str, str] = field(default_factory=dict)  # name -> json type
    required: List[str] = field(default_factory=list)
    returns: str = "string"

    def input_schema(self) -> Dict[str, Any]:
        props = {}
        for pname, ptype in self.params.items():
            props[pname] = {"type": ptype}
        return {
            "type": "object",
            "properties": props,
            "required": list(self.required),
        }


@dataclass
class ServerSpec:
    name: str
    version: str = "0.1.0"
    description: str = ""
    tools: List[ToolSpec] = field(default_factory=list)

    def py_module(self) -> str:
        return self.name.replace("-", "_")


def parse_spec(data: Any) -> ServerSpec:
    """Build a ServerSpec from a dict or JSON string. Raises SpecError."""
    if isinstance(data, (str, bytes)):
        try:
            data = json.loads(data)
        except json.JSONDecodeError as exc:
            raise SpecError(f"invalid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise SpecError("spec root must be an object")

    name = data.get("name")
    if not isinstance(name, str) or not name:
        raise SpecError("spec.name is required and must be a non-empty string")

    tools: List[ToolSpec] = []
    raw_tools = data.get("tools", [])
    if not isinstance(raw_tools, list):
        raise SpecError("spec.tools must be a list")
    for i, t in enumerate(raw_tools):
        if not isinstance(t, dict):
            raise SpecError(f"tools[{i}] must be an object")
        tname = t.get("name")
        if not isinstance(tname, str) or not tname:
            raise SpecError(f"tools[{i}].name is required")
        params = t.get("params", {}) or {}
        if not isinstance(params, dict):
            raise SpecError(f"tools[{i}].params must be an object")
        required = t.get("required", []) or []
        if not isinstance(required, list):
            raise SpecError(f"tools[{i}].required must be a list")
        tools.append(
            ToolSpec(
                name=tname,
                description=str(t.get("description", "")),
                params={str(k): str(v) for k, v in params.items()},
                required=[str(r) for r in required],
                returns=str(t.get("returns", "string")),
            )
        )

    return ServerSpec(
        name=name,
        version=str(data.get("version", "0.1.0")),
        description=str(data.get("description", "")),
        tools=tools,
    )


def lint_spec(spec: ServerSpec) -> Dict[str, List[Dict[str, str]]]:
    """Structural lint. Returns {'errors': [...], 'warnings': [...]}."""
    errors: List[Dict[str, str]] = []
    warnings: List[Dict[str, str]] = []

    if not _NAME_RE.match(spec.name):
        errors.append({"code": "E_NAME", "msg":
                       f"server name '{spec.name}' must match [a-z][a-z0-9-]*"})
    if not re.match(r"^\d+\.\d+\.\d+", spec.version):
        warnings.append({"code": "W_SEMVER",
                         "msg": f"version '{spec.version}' is not semver"})
    if not spec.description:
        warnings.append({"code": "W_DESC",
                         "msg": "server has no description"})
    if not spec.tools:
        errors.append({"code": "E_NOTOOLS", "msg": "server defines no tools"})

    seen = set()
    for t in spec.tools:
        if t.name in seen:
            errors.append({"code": "E_DUP",
                           "msg": f"duplicate tool name '{t.name}'"})
        seen.add(t.name)
        if not _IDENT_RE.match(t.name) or keyword.iskeyword(t.name):
            errors.append({"code": "E_TOOLNAME",
                           "msg": f"tool '{t.name}' is not a valid identifier"})
        if not t.description:
            warnings.append({"code": "W_TOOLDESC",
                             "msg": f"tool '{t.name}' has no description"})
        for pname, ptype in t.params.items():
            if ptype not in _JSON_TYPES:
                errors.append({"code": "E_TYPE",
                               "msg": f"tool '{t.name}' param '{pname}' has "
                                      f"invalid JSON type '{ptype}'"})
        for r in t.required:
            if r not in t.params:
                errors.append({"code": "E_REQ",
                               "msg": f"tool '{t.name}' requires '{r}' which "
                                      f"is not a declared param"})
        if t.returns not in _JSON_TYPES:
            warnings.append({"code": "W_RET",
                             "msg": f"tool '{t.name}' returns unknown type "
                                    f"'{t.returns}'"})
    return {"errors": errors, "warnings": warnings}


def _tool_metas(spec: ServerSpec) -> List[Dict[str, Any]]:
    return [
        {"name": t.name, "description": t.description,
         "inputSchema": t.input_schema()}
        for t in spec.tools
    ]


def _gen_server_source(spec: ServerSpec) -> str:
    """Emit a complete, runnable MCP stdio server (one self-contained file).

    The generated server speaks JSON-RPC 2.0 over stdio and implements
    initialize, tools/list, and tools/call (MCP 2024-11-05). Each tool
    handler echoes a deterministic, useful response derived from its args
    so the scaffold runs end-to-end with zero edits.
    """
    metas = _tool_metas(spec)
    metas_json = json.dumps(metas, indent=4)
    handlers = []
    for t in spec.tools:
        handlers.append(
            f"    if name == {t.name!r}:\n"
            f"        # TODO: replace with real logic for {t.name!r}.\n"
            f"        summary = ', '.join(f'{{k}}={{v!r}}' for k, v in args.items())\n"
            f"        return f'{t.name}({{summary}})'\n"
        )
    handler_body = "".join(handlers) if handlers else ""
    return f'''#!/usr/bin/env python3
"""{spec.name} - MCP server (generated by mcpforge {TOOL_VERSION_PLACEHOLDER}).

{spec.description}

Run:  python -m {spec.py_module()}        (stdio JSON-RPC, MCP 2024-11-05)
No third-party dependencies required.
"""
import json
import sys

SERVER_NAME = {spec.name!r}
SERVER_VERSION = {spec.version!r}
PROTOCOL = "2024-11-05"
TOOLS = {metas_json}


def dispatch(name, args):
{handler_body}    raise ValueError(f"unknown tool: {{name}}")


def handle(req):
    """Handle one JSON-RPC request object; return a response dict or None."""
    method = req.get("method")
    rid = req.get("id")
    try:
        if method == "initialize":
            result = {{
                "protocolVersion": PROTOCOL,
                "capabilities": {{"tools": {{}}}},
                "serverInfo": {{"name": SERVER_NAME, "version": SERVER_VERSION}},
            }}
        elif method == "tools/list":
            result = {{"tools": TOOLS}}
        elif method == "tools/call":
            params = req.get("params") or {{}}
            out = dispatch(params.get("name"), params.get("arguments") or {{}})
            result = {{"content": [{{"type": "text", "text": str(out)}}]}}
        elif method in ("notifications/initialized", "initialized"):
            return None  # notification, no response
        else:
            return {{"jsonrpc": "2.0", "id": rid,
                     "error": {{"code": -32601, "message": "method not found"}}}}
    except Exception as exc:  # noqa: BLE001
        return {{"jsonrpc": "2.0", "id": rid,
                 "error": {{"code": -32603, "message": str(exc)}}}}
    return {{"jsonrpc": "2.0", "id": rid, "result": result}}


def main():
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        resp = handle(json.loads(line))
        if resp is not None:
            sys.stdout.write(json.dumps(resp) + "\\n")
            sys.stdout.flush()


if __name__ == "__main__":
    main()
'''.replace("TOOLS = " + metas_json, "TOOLS = " + metas_json)


# The generated source references the forge version; inject it literally.
from . import __init__ as _selfpkg  # noqa: E402  (lazy, avoids cycle at import)


def _gen_readme(spec: ServerSpec) -> str:
    lines = [
        f"# {spec.name}",
        "",
        spec.description or "An MCP server scaffolded by mcpforge.",
        "",
        "## Tools",
        "",
    ]
    for t in spec.tools:
        params = ", ".join(f"`{k}: {v}`" for k, v in t.params.items()) or "none"
        lines.append(f"- **{t.name}** — {t.description or 'no description'} "
                     f"(params: {params})")
    lines += [
        "",
        "## Run",
        "",
        "```bash",
        f"python -m {spec.py_module()}",
        "```",
        "",
        "Add to your MCP client config:",
        "",
        "```json",
        json.dumps({"mcpServers": {spec.name: {
            "command": "python", "args": ["-m", spec.py_module()]}}}, indent=2),
        "```",
        "",
    ]
    return "\n".join(lines)


def publish_manifest(spec: ServerSpec) -> Dict[str, Any]:
    """Produce publish-ready packaging + MCP registry metadata."""
    module = spec.py_module()
    pyproject = "\n".join([
        "[build-system]",
        'requires = ["hatchling"]',
        'build-backend = "hatchling.build"',
        "",
        "[project]",
        f'name = "{spec.name}"',
        f'version = "{spec.version}"',
        f'description = "{spec.description}"',
        'requires-python = ">=3.10"',
        "",
        "[project.scripts]",
        f'{spec.name} = "{module}:main"',
        "",
    ])
    registry = {
        "name": spec.name,
        "version": spec.version,
        "description": spec.description,
        "runtime": "python",
        "command": "python",
        "args": ["-m", module],
        "protocolVersion": "2024-11-05",
        "tools": [t.name for t in spec.tools],
    }
    return {"pyproject.toml": pyproject, "mcp-registry.json": registry}


def scaffold(spec: ServerSpec) -> Dict[str, str]:
    """Return a mapping of {relative_path: file_content} for the full project."""
    module = spec.py_module()
    src = _gen_server_source(spec)
    pub = publish_manifest(spec)
    return {
        f"{module}/__init__.py": f'"""{spec.name} MCP server."""\n'
                                 f'from .__main__ import main, handle, TOOLS\n'
                                 f'__all__ = ["main", "handle", "TOOLS"]\n',
        f"{module}/__main__.py": src,
        "README.md": _gen_readme(spec),
        "pyproject.toml": pub["pyproject.toml"],
        "mcp-registry.json": json.dumps(pub["mcp-registry.json"], indent=2),
    }


def simulate(spec: ServerSpec, tool: Optional[str] = None,
             arguments: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Execute a real JSON-RPC exchange against the *generated* server.

    The generated server source is compiled in-process (no subprocess, no
    network) and driven through initialize -> tools/list -> tools/call. This
    proves the scaffold actually runs and that the requested tool responds.
    """
    src = _gen_server_source(spec)
    ns: Dict[str, Any] = {}
    try:
        compiled = compile(src, f"<{spec.name}>", "exec")
        exec(compiled, ns)  # noqa: S102 - we generated this source ourselves
    except SyntaxError as exc:
        raise SpecError(f"generated server has a syntax error: {exc}") from exc
    handle = ns["handle"]

    transcript: List[Dict[str, Any]] = []

    def call(req: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        resp = handle(req)
        transcript.append({"request": req, "response": resp})
        return resp

    init = call({"jsonrpc": "2.0", "id": 1, "method": "initialize",
                 "params": {"protocolVersion": "2024-11-05"}})
    listed = call({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})

    chosen = tool
    if chosen is None and spec.tools:
        chosen = spec.tools[0].name

    call_resp = None
    if chosen is not None:
        args = arguments
        if args is None:
            # Synthesize valid example args from the tool's required params.
            args = {}
            tdef = next((t for t in spec.tools if t.name == chosen), None)
            if tdef:
                samples = {"string": "example", "number": 1.0, "integer": 1,
                           "boolean": True, "array": [], "object": {}}
                for rp in tdef.required:
                    args[rp] = samples.get(tdef.params.get(rp, "string"),
                                           "example")
        call_resp = call({"jsonrpc": "2.0", "id": 3, "method": "tools/call",
                          "params": {"name": chosen, "arguments": args}})

    ok = (
        init is not None and "result" in init
        and listed is not None and "result" in listed
        and (call_resp is None or "result" in call_resp)
    )
    return {
        "ok": ok,
        "server": spec.name,
        "protocolVersion": (init or {}).get("result", {}).get(
            "protocolVersion"),
        "tools_listed": [t["name"] for t in (
            listed or {}).get("result", {}).get("tools", [])],
        "called": chosen,
        "call_result": (call_resp or {}).get("result")
        or (call_resp or {}).get("error"),
        "transcript": transcript,
    }


# Resolve the forge version placeholder used inside generated source.
def _forge_version() -> str:
    try:
        from . import TOOL_VERSION
        return TOOL_VERSION
    except Exception:  # pragma: no cover
        return "1.0.0"


TOOL_VERSION_PLACEHOLDER = _forge_version()
