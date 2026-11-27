"""mitmproxy addon; never writes flow content to disk."""
import os, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import rules
from mitmproxy import http

class MapRemoteCustomAddon:
    def __init__(self):
        self.path = Path(os.environ['MAPREMOTE_RULES'])
        self.health_token = os.environ.get('MAPREMOTE_HEALTH_TOKEN')
        self.stamp = None
        self.config = {'enabled':False,'rules':[]}

    def refresh_config(self):
        # Keep the last good atomic configuration; do not log requests.
        try:
            st = self.path.stat()
            stamp = (st.st_ino, st.st_mtime_ns, st.st_size)
            if stamp != self.stamp:
                self.config = rules.load(self.path); self.stamp = stamp
        except (OSError, ValueError, TypeError):
            pass
    def tls_clienthello(self, data):
        # In regular proxy mode the CONNECT authority is the routing target.
        # Unrelated TLS must remain end-to-end (including pinned certificates).
        self.refresh_config()
        address = data.context.server.address
        if not address or not rules.needs_https_interception(self.config, address[0], address[1]):
            data.ignore_connection = True

    def requestheaders(self, flow: http.HTTPFlow):
        if (self.health_token and
                flow.request.url == 'http://mapremote-health.invalid/__mapremote_health' and
                flow.request.headers.get('X-MapRemote-Health') == self.health_token):
            flow.response = http.Response.make(204, b'', {'X-MapRemote-Health': self.health_token})
            return
        self.refresh_config()
        try:
            result = rules.map_url(self.config, flow.request.url, flow.request.method)
        except ValueError:
            return
        if result is None: return
        url, keep_host, _ = result
        old_host = flow.request.host_header
        flow.request.url = url
        if keep_host and old_host is not None:
            flow.request.host_header = old_host

addons = [MapRemoteCustomAddon()]
