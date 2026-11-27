import atexit, errno, fcntl, json, os, secrets, shutil, signal, socket, subprocess, threading, time, webbrowser
from collections import deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from rules import load, save, normalize, map_url
import system_proxy as sp

ROOT = Path(__file__).resolve().parent
DATA = Path.home() / 'Library' / 'Application Support' / 'MapRemote'
DATA.mkdir(mode=0o700, parents=True, exist_ok=True)
RULES = DATA / 'rules.json'
CA = DATA / 'ca'
CA.mkdir(mode=0o700, exist_ok=True)
LOCK = open(DATA/'instance.lock','a')
try: fcntl.flock(LOCK, fcntl.LOCK_EX | fcntl.LOCK_NB)
except BlockingIOError: raise SystemExit('MapRemote is already running.')
TOKEN = secrets.token_urlsafe(32)
MUTEX = threading.RLock()
CONFIG = load(RULES)
save(RULES, CONFIG)
PROC = None
SERVER = None
SYSTEM_ACTIVE = False
LAST_ERROR = ""

def engine():
    bundled = ROOT / 'mitmdump'
    if bundled.is_file() and os.access(bundled, os.X_OK):
        return str(bundled)
    if os.environ.get('MAPREMOTE_NATIVE'):
        return None
    return shutil.which('mitmdump') or next((str(p) for p in [Path('/opt/homebrew/bin/mitmdump'),Path('/usr/local/bin/mitmdump'),Path('/Applications/mitmproxy.app/Contents/MacOS/mitmdump')] if p.is_file() and os.access(p,os.X_OK)),None)

def running(): return PROC is not None and PROC.poll() is None

class StartupDiagnostics:
    """Drain engine output without saving request traffic or growing memory."""
    def __init__(self, proc):
        self.lines = deque(maxlen=30)
        self.lock = threading.Lock()
        self.collecting = True
        self.thread = threading.Thread(target=self._drain, args=(proc.stdout,), daemon=True)
        self.thread.start()

    def _drain(self, stream):
        if stream is None:
            return
        try:
            while True:
                chunk = stream.readline(4096)
                if not chunk:
                    break
                with self.lock:
                    if self.collecting:
                        self.lines.append(chunk.decode('utf-8', errors='replace').rstrip())
        finally:
            stream.close()

    def finish(self, failed=False):
        if failed:
            self.thread.join(timeout=1)
        with self.lock:
            detail = '\n'.join(self.lines).strip() if failed else ''
            self.collecting = False
            self.lines.clear()
        return detail


def ensure_listener_available(port, timeout=2):
    """Match the engine's reusable TCP listener, not TIME_WAIT connections."""
    deadline = time.monotonic() + timeout
    while True:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                probe.bind(('127.0.0.1', port))
                # On BSD/macOS, bind alone is not a reliable listener check.
                probe.listen(1)
                return
            except OSError as exc:
                if exc.errno != errno.EADDRINUSE:
                    raise ValueError(f'Cannot open proxy port {port}: {exc}') from exc
                if time.monotonic() >= deadline:
                    raise ValueError(f'Proxy port {port} is occupied by another listener. Close the conflicting proxy or choose another port. Diagnostic: lsof -nP -iTCP:{port} -sTCP:LISTEN') from exc
        time.sleep(.1)


def start():
    global PROC, SYSTEM_ACTIVE, LAST_ERROR
    if running(): return
    LAST_ERROR = ""
    exe = engine()
    if not exe: raise ValueError('Bundled proxy engine missing. Reinstall MapRemote from a complete DMG (source developers can install mitmproxy separately).')
    ensure_listener_available(CONFIG['port'])
    env = os.environ.copy(); env['MAPREMOTE_RULES'] = str(RULES)
    env['MAPREMOTE_CONTROLLER_PID'] = str(os.getpid())
    args = [exe,'--listen-host','127.0.0.1','--listen-port',str(CONFIG['port']), '--mode','regular', '--set',f'confdir={CA}', '--set','connection_strategy=lazy','--set','upstream_cert=false','--set','flow_detail=0','--set','termlog_verbosity=error','--set','stream_large_bodies=1m','-s',str(ROOT/'addon.py')]
    PROC = subprocess.Popen(args, env=env, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    diagnostics = StartupDiagnostics(PROC)
    deadline = time.monotonic()+20
    ready_since = None
    while time.monotonic()<deadline:
        if PROC.poll() is not None:
            code = PROC.poll()
            detail = diagnostics.finish(failed=True)
            stop()
            LAST_ERROR = f'Proxy exited during startup (exit {code}).' + (f'\n{detail}' if detail else '\nNo engine diagnostics available.')
            raise ValueError(LAST_ERROR)
        try:
            with socket.create_connection(('127.0.0.1',CONFIG['port']),timeout=.15): pass
            if ready_since is None: ready_since = time.monotonic()
            if time.monotonic() - ready_since >= .3: break
        except OSError:
            ready_since = None
        time.sleep(.1)
    else:
        stop()
        detail = diagnostics.finish(failed=True)
        LAST_ERROR = 'Proxy startup timed out.' + (f'\n{detail}' if detail else '')
        raise ValueError(LAST_ERROR)
    diagnostics.finish()
    try:
        sp.enable(PROC.pid, CONFIG['port'])
        SYSTEM_ACTIVE = True
    except Exception as exc:
        stop()
        if sp.JOURNAL.exists() and not sp.wait_restore():
            LAST_ERROR = 'Startup failed and network restoration is pending. Use Recover network settings.'
        else:
            LAST_ERROR = str(exc)
        raise ValueError(LAST_ERROR if LAST_ERROR == str(exc) else f'{exc}\n{LAST_ERROR}') from exc

def stop():
    global PROC, SYSTEM_ACTIVE, LAST_ERROR
    if running():
        PROC.terminate()
        try: PROC.wait(timeout=5)
        except subprocess.TimeoutExpired: PROC.kill(); PROC.wait()
    PROC=None
    if SYSTEM_ACTIVE:
        SYSTEM_ACTIVE=False
        if not sp.wait_restore():
            LAST_ERROR='Network restore did not complete. Use Recover network settings.'
            raise ValueError(LAST_ERROR)
    LAST_ERROR=''

def cleanup():
    # Quit/parent monitoring can race with a Start request. Serialize them.
    with MUTEX:
        try: stop()
        except Exception: pass

atexit.register(cleanup)

def monitor():
    parent = int(os.environ.get('MAPREMOTE_PARENT_PID','0'))
    while True:
        time.sleep(.5)
        if parent:
            try: os.kill(parent,0)
            except ProcessLookupError:
                cleanup(); SERVER.shutdown(); return
        with MUTEX:
            if SYSTEM_ACTIVE and (not running() or not sp.JOURNAL.exists()):
                try: stop()
                except Exception: pass

def state():
    ca = CA/'mitmproxy-ca-cert.pem'
    return {'config':CONFIG,'running':running() and SYSTEM_ACTIVE,'engine':bool(engine()), 'ca':str(ca), 'ca_exists':ca.exists(), 'ca_trusted':sp.cert_trusted(ca), 'recovery':sp.JOURNAL.exists() and not SYSTEM_ACTIVE, 'error':LAST_ERROR}

class Handler(BaseHTTPRequestHandler):
    def log_message(self,*args): pass
    def valid(self): return self.headers.get('Host') == f'127.0.0.1:{SERVER.server_port}'
    def send_data(self,status,payload,kind='application/json'):
        if isinstance(payload,dict): payload=json.dumps(payload).encode()
        elif isinstance(payload,str): payload=payload.encode()
        self.send_response(status); self.send_header('Content-Type',kind+'; charset=utf-8'); self.send_header('Content-Length',str(len(payload))); self.send_header('Cache-Control','no-store'); self.send_header('X-Content-Type-Options','nosniff'); self.send_header('X-Frame-Options','DENY'); self.send_header('Referrer-Policy','no-referrer'); self.end_headers(); self.wfile.write(payload)
    def do_GET(self):
        if not self.valid(): return self.send_data(403,{'error':'Invalid host'})
        if self.path=='/': return self.send_data(200,(ROOT/'index.html').read_text().replace('__TOKEN__',TOKEN),'text/html')
        if self.path=='/api/state' and self.headers.get('X-MapRemote-Token')==TOKEN:
            with MUTEX: return self.send_data(200,state())
        self.send_data(404,{'error':'Not found'})
    def do_POST(self):
        global CONFIG
        if not self.valid() or self.headers.get('X-MapRemote-Token')!=TOKEN or self.headers.get('Origin')!=f'http://127.0.0.1:{SERVER.server_port}': return self.send_data(403,{'error':'Forbidden'})
        try:
            n=int(self.headers.get('Content-Length','0'))
            if not 0 <= n <= 1_000_000: raise ValueError('Invalid request size')
            data=json.loads(self.rfile.read(n) or b'{}')
            with MUTEX:
                if self.path=='/api/save':
                    new=normalize(data)
                    if running() and new['port']!=CONFIG['port']: raise ValueError('Stop the proxy before changing the port.')
                    CONFIG=save(RULES,new)
                elif self.path=='/api/start': start()
                elif self.path=='/api/stop': stop()
                elif self.path=='/api/cert/install': sp.cert_action(CA/'mitmproxy-ca-cert.pem', True)
                elif self.path=='/api/cert/remove': sp.cert_action(CA/'mitmproxy-ca-cert.pem', False)
                elif self.path=='/api/recover':
                    if running(): raise ValueError('Stop the proxy first.')
                    sp.recover()
                elif self.path=='/api/preview':
                    result=map_url(normalize(data['config']),data['url'],data['method'])
                    return self.send_data(200,{'result':result})
                elif self.path=='/api/quit':
                    stop(); self.send_data(200,{'ok':True}); threading.Thread(target=SERVER.shutdown,daemon=True).start(); return
                else: return self.send_data(404,{'error':'Not found'})
                self.send_data(200,state())
        except (ValueError,KeyError,TypeError,OSError) as e: self.send_data(400,{'error':str(e)})

def main():
    global SERVER
    SERVER=ThreadingHTTPServer(('127.0.0.1',0),Handler)
    url=f'http://127.0.0.1:{SERVER.server_port}'
    print('MapRemote:',url,flush=True)
    if not os.environ.get('MAPREMOTE_NATIVE'): webbrowser.open(url)
    threading.Thread(target=monitor,daemon=True).start()
    def shutdown(*_): raise KeyboardInterrupt
    signal.signal(signal.SIGTERM,shutdown)
    try: SERVER.serve_forever()
    except KeyboardInterrupt: pass
    finally: SERVER.server_close(); cleanup()

if __name__=='__main__': main()
