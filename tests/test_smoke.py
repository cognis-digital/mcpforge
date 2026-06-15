"""Smoke tests for mcpforge. Standard library only, no network."""
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mcpforge import (  # noqa: E402
    TOOL_NAME,
    TOOL_VERSION,
    parse_spec,
    lint_spec,
    scaffold,
    simulate,
    publish_manifest,
    SpecError,
)
from mcpforge.cli import main  # noqa: E402

GOOD = {
    "name": "weather-mcp",
    "version": "0.1.0",
    "description": "weather server",
    "tools": [
        {"name": "get_forecast", "description": "forecast",
         "params": {"location": "string", "days": "integer"},
         "required": ["location"], "returns": "string"},
    ],
}


class TestCore(unittest.TestCase):
    def test_meta(self):
        self.assertEqual(TOOL_NAME, "mcpforge")
        self.assertRegex(TOOL_VERSION, r"^\d+\.\d+\.\d+$")

    def test_parse_and_lint_clean(self):
        spec = parse_spec(GOOD)
        report = lint_spec(spec)
        self.assertEqual(report["errors"], [])

    def test_lint_catches_errors(self):
        bad = {"name": "Bad Name!", "tools": [
            {"name": "1bad", "params": {"x": "notatype"}, "required": ["y"]},
            {"name": "1bad"},
        ]}
        report = lint_spec(parse_spec(bad))
        codes = {e["code"] for e in report["errors"]}
        self.assertIn("E_NAME", codes)
        self.assertIn("E_TOOLNAME", codes)
        self.assertIn("E_TYPE", codes)
        self.assertIn("E_REQ", codes)
        self.assertIn("E_DUP", codes)

    def test_parse_rejects_bad(self):
        with self.assertRaises(SpecError):
            parse_spec({"tools": []})
        with self.assertRaises(SpecError):
            parse_spec("{not json")

    def test_scaffold_files(self):
        files = scaffold(parse_spec(GOOD))
        self.assertIn("weather_mcp/__main__.py", files)
        self.assertIn("pyproject.toml", files)
        self.assertIn("mcp-registry.json", files)
        # generated server source must compile
        compile(files["weather_mcp/__main__.py"], "<gen>", "exec")

    def test_simulate_runs_generated_server(self):
        result = simulate(parse_spec(GOOD), tool="get_forecast")
        self.assertTrue(result["ok"])
        self.assertEqual(result["protocolVersion"], "2024-11-05")
        self.assertIn("get_forecast", result["tools_listed"])
        self.assertIn("location", json.dumps(result["call_result"]))

    def test_publish_manifest(self):
        man = publish_manifest(parse_spec(GOOD))
        self.assertIn("weather-mcp", man["pyproject.toml"])
        self.assertEqual(man["mcp-registry.json"]["tools"], ["get_forecast"])


class TestCLI(unittest.TestCase):
    def _write(self, obj):
        fd, path = tempfile.mkstemp(suffix=".json")
        with os.fdopen(fd, "w") as fh:
            json.dump(obj, fh)
        self.addCleanup(os.unlink, path)
        return path

    def test_lint_ok_exit0(self):
        self.assertEqual(main(["--format", "json", "lint",
                               self._write(GOOD)]), 0)

    def test_lint_errors_exit1(self):
        path = self._write({"name": "X X", "tools": []})
        self.assertEqual(main(["lint", path]), 1)

    def test_simulate_exit0(self):
        self.assertEqual(main(["--format", "json", "simulate",
                               self._write(GOOD)]), 0)

    def test_scaffold_writes(self):
        out = tempfile.mkdtemp()
        rc = main(["scaffold", self._write(GOOD), "--out", out])
        self.assertEqual(rc, 0)
        self.assertTrue(os.path.isfile(
            os.path.join(out, "weather_mcp", "__main__.py")))

    def test_missing_spec_exit2(self):
        self.assertEqual(main(["lint", "/no/such/spec.json"]), 2)

    def test_publish_exit0(self):
        self.assertEqual(main(["--format", "json", "publish",
                               self._write(GOOD)]), 0)


class TestHardening(unittest.TestCase):
    """Tests for hardened error-handling and edge-case paths."""

    def test_simulate_unknown_tool_raises(self):
        """Requesting a non-existent tool name must raise SpecError, not KeyError."""
        from mcpforge.core import SpecError, simulate
        spec = parse_spec(GOOD)
        with self.assertRaises(SpecError) as ctx:
            simulate(spec, tool="no_such_tool")
        self.assertIn("no_such_tool", str(ctx.exception))

    def test_simulate_no_tools_ok(self):
        """A spec with no tools (lint will flag it, but simulate should not crash)."""
        from mcpforge.core import simulate
        spec = parse_spec({"name": "empty-srv", "tools": []})
        result = simulate(spec, tool=None)
        # ok may be True or False depending on lint, but it must not raise
        self.assertIsNone(result["called"])

    def test_py_module_avoids_keyword(self):
        """Server names that map to Python keywords must get a safe module name."""
        spec = parse_spec({"name": "for", "tools": [{"name": "run"}]})
        mod = spec.py_module()
        import keyword as kw
        self.assertFalse(kw.iskeyword(mod), f"py_module() returned keyword: {mod!r}")

    def test_mcp_server_imports_cleanly(self):
        """mcp_server.py must be importable without an ImportError."""
        import importlib
        # This would previously raise ImportError for missing scan/to_json
        mod = importlib.import_module("mcpforge.mcp_server")
        self.assertTrue(callable(mod.serve))

    def test_cli_simulate_unknown_tool_exit2(self):
        """CLI: simulate with --tool pointing at a non-existent tool exits 2."""
        fd, path = tempfile.mkstemp(suffix=".json")
        with os.fdopen(fd, "w") as fh:
            json.dump(GOOD, fh)
        try:
            rc = main(["simulate", path, "--tool", "nonexistent_tool"])
            self.assertEqual(rc, 2)
        finally:
            os.unlink(path)

    def test_cli_invalid_args_json_exit2(self):
        """CLI: simulate with malformed --args JSON exits 2 with clean error."""
        fd, path = tempfile.mkstemp(suffix=".json")
        with os.fdopen(fd, "w") as fh:
            json.dump(GOOD, fh)
        try:
            rc = main(["simulate", path, "--args", "{not valid json"])
            self.assertEqual(rc, 2)
        finally:
            os.unlink(path)


if __name__ == "__main__":
    unittest.main()
