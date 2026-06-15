"""MCPFORGE MCP server — exposes scaffold/lint as MCP tools for Cognis.Studio."""
from __future__ import annotations

import json
import sys


def serve() -> int:
    """Start an MCP stdio server. Requires the optional 'mcp' extra:
        pip install "cognis-mcpforge[mcp]"
    """
    try:
        from mcp.server.fastmcp import FastMCP  # type: ignore[import]
    except ImportError:
        print(
            "Install the MCP extra: pip install 'cognis-mcpforge[mcp]'",
            file=sys.stderr,
        )
        return 1

    from mcpforge.core import SpecError, lint_spec, parse_spec

    app = FastMCP("mcpforge")

    @app.tool()
    def mcpforge_lint(spec_json: str) -> str:
        """Lint an MCP server spec (JSON string). Returns JSON report."""
        try:
            spec = parse_spec(spec_json)
            report = lint_spec(spec)
            return json.dumps(report)
        except SpecError as exc:
            return json.dumps({"errors": [{"code": "E_PARSE", "msg": str(exc)}],
                               "warnings": []})

    app.run()
    return 0
