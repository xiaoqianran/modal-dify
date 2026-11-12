"""Offline checks for the minimal Dify MCP tunnel configuration."""
import ast
import base64
import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import re
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
DEPLOY = ROOT / "scripts/deploy.py"


def setup_source():
    module = ast.parse(DEPLOY.read_text())
    return next(n.value.value for n in module.body if isinstance(n, ast.Assign)
                and any(isinstance(t, ast.Name) and t.id == "SETUP" for t in n.targets))


class TestMcpExposure(unittest.TestCase):
    def test_config_keeps_console_protected_and_only_exempts_native_mcp(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "nginx/conf.d").mkdir(parents=True)
            template = ROOT / "vendor/dify-1.19.0/nginx/conf.d/default.conf.template"
            (root / "nginx/conf.d/default.conf.template").write_text(template.read_text())
            secrets = {"edge_password": "testingPassword", "DB_PASSWORD": "testingDB"}
            setup = setup_source().replace('pathlib.Path("/opt/dify/docker")', repr_root(root))
            with patch.dict(os.environ, {"DIFY_SETUP": base64.b64encode(json.dumps(secrets).encode()).decode()}):
                exec(compile(setup, "SETUP", "exec"), {})
            config = (root / "nginx/conf.d/default.conf.template").read_text()
            self.assertIn('auth_basic "Dify evaluation";', config)
            self.assertEqual(config.count('auth_basic off;'), 1)
            self.assertIn('location /mcp {', config)
            self.assertIn('proxy_pass http://$api_upstream;', config)
            matched = re.search(r'location ~ (\S+) \{\s+auth_basic off;', config)
            self.assertIsNotNone(matched)
            pattern = re.compile(matched.group(1))
            for path in ('/mcp/server/test-code/mcp', '/mcp/server/test-code/mcp/'):
                self.assertIsNotNone(pattern.fullmatch(path))
            for path in ('/', '/install', '/console/api', '/mcp', '/mcp/other',
                         '/mcp/server/test-code/mcp/extra', '/mcp/server/test-code/mcpXYZ'):
                self.assertIsNone(pattern.fullmatch(path))
            self.assertNotIn('edge_password=', (root / '.env').read_text())
            plugin_storage = root / 'volumes/plugin_daemon'
            self.assertTrue(plugin_storage.is_dir())
            self.assertEqual((plugin_storage.stat().st_uid, plugin_storage.stat().st_gid), (1001, 1001))

    def test_endpoint_hint_uses_single_tunnel(self):
        spec = importlib.util.spec_from_file_location('deploy', DEPLOY)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        class Tunnel:
            url = 'https://modal.example/'
        class Sandbox:
            def tunnels(self):
                return {80: Tunnel()}
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            module.print_endpoints(Sandbox())
        self.assertEqual(output.getvalue().splitlines(), [
            'DIFY_URL https://modal.example',
            'MCP_URL_FORMAT https://modal.example/mcp/server/<server_code>/mcp',
        ])


def repr_root(path):
    return f'pathlib.Path({str(path)!r})'


if __name__ == '__main__':
    unittest.main()
