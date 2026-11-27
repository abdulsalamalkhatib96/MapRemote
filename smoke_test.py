#!/usr/bin/env python3
"""Live loopback-only smoke test. No system proxy or certificate trust changes."""
import http.client
import os
from pathlib import Path
import shutil
import socket
import ssl
import subprocess
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import rules

ROOT = Path(__file__).resolve().parent

class Target(BaseHTTPRequestHandler):
    def log_message(self, *args): pass
    def do_GET(self):
        body = self.path.encode()
        self.send_response(200)
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def main():
    exe = os.environ.get('MAPREMOTE_ENGINE') or shutil.which('mitmdump') or next((str(p) for p in (Path('/opt/homebrew/bin/mitmdump'), Path('/usr/local/bin/mitmdump'), Path('/Applications/mitmproxy.app/Contents/MacOS/mitmdump')) if p.is_file() and os.access(p, os.X_OK)), None)
    if not exe:
        raise SystemExit('mitmdump not found. Install it before running this test.')
    with tempfile.TemporaryDirectory(prefix='mapremote-smoke-') as folder, ThreadingHTTPServer(('127.0.0.1', 0), Target) as target, socket.socket() as reserved:
        thread = threading.Thread(target=target.serve_forever, daemon=True)
        thread.start()
        reserved.bind(('127.0.0.1', 0))
        port = reserved.getsockname()[1]
        reserved.close()
        root = Path(folder)
        config = root / 'rules.json'
        rules.save(config, {'enabled': True, 'port': port, 'rules': [{'enabled': True, 'name': 'smoke', 'source': 'http://mapremote-smoke.invalid/api', 'destination': f'http://127.0.0.1:{target.server_port}/local', 'method': '*', 'match': 'prefix', 'query': 'preserve', 'preserve_host': False}]})
        cfg = rules.load(config)
        https_rule = dict(cfg['rules'][0], name='https-smoke', source='https://mapremote-smoke.invalid/api')
        cfg['rules'].append(https_rule)
        rules.save(config, cfg)
        env = dict(os.environ, MAPREMOTE_RULES=str(config))
        args = [exe, '--listen-host', '127.0.0.1', '--listen-port', str(port), '--mode', 'regular', '--set', f'confdir={root / "ca"}', '--set', 'connection_strategy=lazy', '--set', 'upstream_cert=false', '--set', 'flow_detail=0', '--set', 'termlog_verbosity=error', '--set', 'stream_large_bodies=1m', '-s', str(ROOT / 'addon.py')]
        with tempfile.TemporaryFile() as log:
            proc = subprocess.Popen(args, env=env, stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT)
            try:
                deadline = time.monotonic() + 15
                while time.monotonic() < deadline:
                    if proc.poll() is not None:
                        raise RuntimeError(f'mitmdump exited with {proc.returncode}')
                    try:
                        with socket.create_connection(('127.0.0.1', port), timeout=.2): pass
                        break
                    except OSError: time.sleep(.1)
                else: raise RuntimeError('mitmdump listener timed out')
                conn = http.client.HTTPConnection('127.0.0.1', port, timeout=5)
                try:
                    conn.request('GET', 'http://mapremote-smoke.invalid/api/users?test=1')
                    response = conn.getresponse()
                    body = response.read()
                    if response.status != 200 or body != b'/local/users?test=1':
                        raise RuntimeError(f'Unexpected response: {response.status}, {body[:200]!r}')
                finally: conn.close()
                print('PASS: mitmdump startup, addon loading, HTTP host/path/query mapping.')
                context = ssl.create_default_context(cafile=str(root / 'ca' / 'mitmproxy-ca-cert.pem'))
                conn = http.client.HTTPSConnection('127.0.0.1', port, timeout=10, context=context)
                conn.set_tunnel('mapremote-smoke.invalid', 443)
                try:
                    conn.request('GET', '/api/users?tls=1')
                    response = conn.getresponse()
                    body = response.read()
                    if response.status != 200 or body != b'/local/users?tls=1':
                        raise RuntimeError(f'Unexpected HTTPS response: {response.status}, {body[:200]!r}')
                finally: conn.close()
                print('PASS: HTTPS CONNECT, temporary CA verification and HTTPS-to-HTTP mapping.')
            except (RuntimeError, OSError, http.client.HTTPException) as exc:
                print(f'FAIL: {exc}', flush=True)
                raise SystemExit(1) from exc
            finally:
                if proc.poll() is None:
                    proc.terminate()
                    try: proc.wait(timeout=5)
                    except subprocess.TimeoutExpired: proc.kill(); proc.wait()
                log.seek(0)
                output = log.read(16384).decode('utf-8', errors='replace').strip()
                if output: print(output)
                target.shutdown()

if __name__ == '__main__': main()
