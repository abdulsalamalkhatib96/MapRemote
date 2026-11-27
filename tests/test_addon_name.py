import importlib.util
import os
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch


class AddonRegistrationTest(unittest.TestCase):
    def test_custom_addon_does_not_reuse_builtin_name(self):
        # Simulate mitmproxy's class-derived naming convention without requiring
        # the engine on the test host. This is not a live mitmdump test.
        fake = types.ModuleType('mitmproxy')
        fake.http = types.SimpleNamespace(HTTPFlow=object)
        spec = importlib.util.spec_from_file_location('custom_mapremote_test', Path(__file__).resolve().parents[1] / 'addon.py')
        module = importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules, {'mitmproxy': fake}), patch.dict(os.environ, {'MAPREMOTE_RULES': '/tmp/mapremote-test-rules.json'}):
            spec.loader.exec_module(module)
        names = [type(addon).__name__.lower() for addon in module.addons]
        self.assertEqual(names, ['mapremotecustomaddon'])
        self.assertNotIn('mapremote', names)
        # mitmproxy registers the script module itself as well as its addons.
        # In v2.3 the imported rules.load leaked as a module-level load hook.
        for hook in ('load', 'configure', 'running', 'done', 'request', 'requestheaders', 'response', 'responseheaders', 'error'):
            self.assertFalse(callable(getattr(module, hook, None)), hook)
        self.assertTrue(callable(module.addons[0].requestheaders))

    def test_tls_passthrough_and_live_scope(self):
        fake = types.ModuleType('mitmproxy')
        fake.http = types.SimpleNamespace(HTTPFlow=object)
        spec = importlib.util.spec_from_file_location('mapremote_scope_test', Path(__file__).resolve().parents[1] / 'addon.py')
        module = importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules, {'mitmproxy': fake}), patch.dict(os.environ, {'MAPREMOTE_RULES': '/tmp/mapremote-test-rules.json'}):
            spec.loader.exec_module(module)
        addon = module.addons[0]
        def hello(host, port=443):
            return types.SimpleNamespace(context=types.SimpleNamespace(server=types.SimpleNamespace(address=(host,port))),ignore_connection=False)
        with patch.object(addon, 'refresh_config'):
            addon.config = {'enabled': True, 'rules': [{'enabled': True, 'source': 'https://api.example.com/v1'}]}
            for host, expected in [('api.example.com', False), ('www.example.com', True)]:
                event = hello(host)
                addon.tls_clienthello(event)
                self.assertEqual(event.ignore_connection, expected)
            addon.config['enabled'] = False
            event = hello('api.example.com')
            addon.tls_clienthello(event)
            self.assertTrue(event.ignore_connection)

