"""MCPFORGE - Scaffold, test, and publish MCP servers in minutes.

A zero-dependency, standard-library-only toolkit for the MCP gold rush.
Generate a fully working Model Context Protocol (MCP) stdio server from a
spec, lint it, simulate a JSON-RPC handshake + tool call against the
generated server, and emit publish-ready packaging metadata.
"""
from .core import (
    ToolSpec,
    ServerSpec,
    parse_spec,
    scaffold,
    lint_spec,
    simulate,
    publish_manifest,
    SpecError,
)

TOOL_NAME = "mcpforge"
TOOL_VERSION = "1.0.0"

__all__ = [
    "ToolSpec",
    "ServerSpec",
    "parse_spec",
    "scaffold",
    "lint_spec",
    "simulate",
    "publish_manifest",
    "SpecError",
    "TOOL_NAME",
    "TOOL_VERSION",
]
