"""Deterministic URL mapping; independent of the proxy engine."""
import json, os, tempfile
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit
import re

DEFAULT = {'enabled': True, 'port': 9090, 'rules': []}
METHODS = {'*','GET','POST','PUT','PATCH','DELETE','HEAD','OPTIONS','CONNECT','TRACE'}

def parts(value, source=False):
    if not isinstance(value, str) or not value or any(c.isspace() or ord(c)<32 for c in value):
        raise ValueError('Enter a full HTTP or HTTPS URL without whitespace.')
    u = urlsplit(value)
    if u.scheme not in ('http','https') or not u.hostname or u.username is not None or u.password is not None or u.fragment or '#' in value:
        raise ValueError('Only HTTP(S) URLs without credentials or fragments are supported.')
    if source and ('?' in value):
        raise ValueError('Source query matching is not supported; queries are preserved by default.')
    if '*' in u.netloc:
        if not source or not u.hostname.startswith('*.') or u.hostname.count('*') != 1:
            raise ValueError('Use a wildcard only as a source hostname prefix: *.example.com')
    if not u.hostname.isascii() or any(c in u.hostname for c in '\\/%'):
        raise ValueError('Use ASCII or punycode hostnames and valid IP addresses.')
    if u.port is not None and not 1 <= u.port <= 65535:
        raise ValueError('Invalid URL port.')
    return u

def normalize(config):
    if not isinstance(config, dict) or type(config.get('enabled')) is not bool or type(config.get('port')) is not int or not 1024 <= config['port'] <= 65535:
        raise ValueError('Proxy port must be between 1024 and 65535.')
    if not isinstance(config.get('rules'), list) or len(config['rules']) > 500:
        raise ValueError('A maximum of 500 rules is supported.')
    out = {'enabled': config['enabled'], 'port': config['port'], 'rules': []}
    for r in config['rules']:
        if not isinstance(r, dict) or type(r.get('enabled')) is not bool or type(r.get('preserve_host')) is not bool:
            raise ValueError('Invalid rule flags.')
        if r.get('method') not in METHODS or r.get('match') not in ('exact','prefix') or r.get('query') not in ('preserve','replace'):
            raise ValueError('Invalid rule options.')
        s, d = parts(r.get('source'), True), parts(r.get('destination'))
        if r['query'] == 'preserve' and '?' in r['destination']:
            raise ValueError('Choose Replace query when the destination contains a query.')
        if d.hostname in ('localhost','127.0.0.1','::1') and (d.port or default_port(d.scheme)) == out['port']:
            raise ValueError('Destination cannot point to the proxy listener itself.')
        name = r.get('name','')
        if not isinstance(name,str) or len(name)>200: raise ValueError('Invalid rule name.')
        out['rules'].append({k:r[k] for k in ('enabled','source','destination','method','match','query','preserve_host')} | {'name':name})
    return out

def default_port(s): return 443 if s == 'https' else 80

def map_url(config, url, method):
    if not config['enabled']: return None
    u = urlsplit(url)
    for i,r in enumerate(config['rules']):
        if not r['enabled'] or r['method'] not in ('*',method.upper()): continue
        s,d = urlsplit(r['source']),urlsplit(r['destination'])
        if u.scheme != s.scheme or (u.port or default_port(u.scheme)) != (s.port or default_port(s.scheme)): continue
        host = u.hostname or ''
        if s.hostname.startswith('*.'):
            if not host.endswith(s.hostname[1:]) or host == s.hostname[2:]: continue
        elif host != s.hostname: continue
        path, base = u.path or '/', s.path or '/'
        if r['match'] == 'exact':
            if path != base: continue
            suffix = ''
        else:
            if path == base: suffix = ''
            elif base.endswith('/') and path.startswith(base): suffix = path[len(base):]
            elif path.startswith(base + '/'): suffix = path[len(base):]
            else: continue
        target = d.path or '/'
        if suffix:
            target = target.rstrip('/') + (suffix if suffix.startswith('/') and not base.endswith('/') else '/' + suffix)
        query = u.query if r['query'] == 'preserve' else d.query
        return (urlunsplit((d.scheme,d.netloc,target,query,'')), r['preserve_host'], i)
    return None

def save(path, config):
    config = normalize(config)
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix='.rules-')
    try:
        with os.fdopen(fd,'w') as f:
            json.dump(config,f,indent=2); f.flush(); os.fsync(f.fileno())
        os.replace(tmp,path)
    finally:
        if os.path.exists(tmp): os.unlink(tmp)
    return config

def load(path):
    try:
        with open(path) as f: return normalize(json.load(f))
    except FileNotFoundError: return DEFAULT.copy() | {'rules': []}
