"""MCPFORGE MCP server — exposes scan() as an MCP tool for Cognis.Studio."""
from __future__ import annotations
from mcpforge.core import scan, to_json

def serve() -> int:
    """Start an MCP stdio server. Requires the optional 'mcp' extra:
        pip install "cognis-mcpforge[mcp]"
    """
    try:
        from mcp.server.fastmcp import FastMCP
    except Exception:
        print("Install the MCP extra: pip install 'cognis-mcpforge[mcp]'")
        return 1
    app = FastMCP("mcpforge")

    @app.tool()
    def mcpforge_scan(target: str) -> str:
        """Scaffold, test, and publish MCP servers in minutes. Returns JSON findings."""
        return to_json(scan(target))

    app.run()
    return 0
