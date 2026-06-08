# Demo 01 - Basic: weather-mcp

This demo scaffolds a small, realistic MCP server called `weather-mcp` that
exposes two tools (`get_forecast`, `get_alerts`), then proves it actually
runs by driving a real JSON-RPC handshake against the generated code.

## Files

- `spec.json` - the server spec (input to every mcpforge subcommand)

## Walkthrough

1. Lint the spec (catches naming, type, and required-param mistakes):

   ```bash
   python -m mcpforge --format table lint demos/01-basic/spec.json
   ```

   Expected: `0 error(s)` (one warning for the missing param description is
   fine). Exit code 0.

2. Simulate it without writing any files. mcpforge generates the server
   source, compiles it in-process, and runs `initialize` -> `tools/list` ->
   `tools/call` (auto-synthesizing valid example arguments):

   ```bash
   python -m mcpforge --format json simulate demos/01-basic/spec.json --tool get_forecast
   ```

   Expected: `"ok": true`, `protocolVersion: 2024-11-05`, and a `call_result`
   containing the echoed forecast arguments. Exit code 0.

3. Scaffold the real project into a temp dir:

   ```bash
   python -m mcpforge scaffold demos/01-basic/spec.json --out /tmp/weather-mcp
   ```

   This writes `weather_mcp/__main__.py` (a runnable MCP stdio server),
   `weather_mcp/__init__.py`, `README.md`, `pyproject.toml`, and
   `mcp-registry.json`. You can immediately run the generated server:

   ```bash
   cd /tmp/weather-mcp && echo '{"jsonrpc":"2.0","id":1,"method":"tools/list"}' | python -m weather_mcp
   ```

4. Generate publish metadata (refuses if lint errors exist):

   ```bash
   python -m mcpforge --format json publish demos/01-basic/spec.json
   ```

## Why this matters

The MCP ecosystem is exploding and most servers are hand-written boilerplate.
mcpforge turns a 20-line spec into a publish-ready, *already-tested* server
with zero dependencies, so you can ride the gold rush in minutes.
