"""mitmproxy addon; never writes flow content to disk."""
import os, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import rules
from mitmproxy import http

class MapRemoteCustomAddon:
    def __init__(self):
        self.path = Path(os.environ['MAPREMOTE_RULES'])
        self.stamp = None
        self.config = {'enabled':False,'rules':[]}

    def requestheaders(self, flow: http.HTTPFlow):
        # Keep the last good atomic configuration; do not log requests.
        try:
            st = self.path.stat()
            stamp = (st.st_ino, st.st_mtime_ns, st.st_size)
            if stamp != self.stamp:
                self.config = rules.load(self.path); self.stamp = stamp
        except (OSError, ValueError, TypeError):
            pass
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
