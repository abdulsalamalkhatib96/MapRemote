"""macOS privileged proxy supervisor and explicit CA trust actions."""
import os, shlex, subprocess, sys, time
from pathlib import Path

JOURNAL = Path('/private/var/db/com.mapremote.proxy/snapshot.plist')

def helper():
    path = Path(__file__).resolve().parent / 'ProxyHelper'
    if sys.platform != 'darwin' or not path.is_file():
        raise ValueError('Build MapRemote.app using Build.command on macOS first.')
    return path

def admin(command):
    script = 'on run argv\nreturn do shell script (item 1 of argv) with administrator privileges\nend run'
    result = subprocess.run(['/usr/bin/osascript', '-e', script, command], capture_output=True, text=True)
    if result.returncode:
        raise ValueError(result.stderr.strip() or 'Administrator authorization failed.')
    return result.stdout.strip()

def startup_command(executable, controller_pid, engine_pid, port):
    # Stage the authorized executable in a private root-owned directory. This
    # also avoids launching it directly from Downloads or a movable app bundle.
    source = shlex.quote(str(executable))
    return f'''set -eu
umask 077
cd /
d=$(/usr/bin/mktemp -d /private/tmp/mapremote.XXXXXXXX)
trap '/bin/rm -rf "$d"' EXIT
/usr/bin/install -m 700 {source} "$d/ProxyHelper"
# macOS nohup may fail to detach from the console inside osascript.
# Ignore SIGHUP in the child and redirect all three standard descriptors.
# exec preserves the PID for readiness diagnostics.
(
  trap '' HUP
  exec "$d/ProxyHelper" run {int(controller_pid)} {int(engine_pid)} {int(port)} "$d/ready"
) </dev/null >"$d/helper.log" 2>&1 &
child=$!
i=0
while [ ! -f "$d/ready" ] && [ "$i" -lt 400 ]; do
  if ! kill -0 "$child" 2>/dev/null; then
    rc=0; wait "$child" || rc=$?
    echo "System proxy helper exited before readiness (status $rc)." >&2
    /bin/cat "$d/helper.log" >&2
    exit 1
  fi
  /bin/sleep 0.1; i=$((i+1))
done
if [ ! -f "$d/ready" ]; then
  echo 'System proxy helper did not become ready within 40 seconds. Last helper messages:' >&2
  /bin/cat "$d/helper.log" >&2
  exit 1
fi
/bin/cat "$d/ready"'''

def enable(pid, port):
    result = admin(startup_command(helper(), os.getpid(), pid, port))
    if result != 'OK': raise ValueError(result or 'Could not activate system proxy.')

def wait_restore(timeout=12):
    deadline = time.monotonic() + timeout
    while JOURNAL.exists() and time.monotonic() < deadline: time.sleep(.2)
    return not JOURNAL.exists()

def recover():
    source = shlex.quote(str(helper()))
    admin(f'''set -eu
umask 077
cd /
d=$(/usr/bin/mktemp -d /private/tmp/mapremote.XXXXXXXX)
trap '/bin/rm -rf "$d"' EXIT
/usr/bin/install -m 700 {source} "$d/ProxyHelper"
"$d/ProxyHelper" recover''')

def _security(args):
    result = subprocess.run(['/usr/bin/security', *args], capture_output=True, text=True)
    if result.returncode:
        raise ValueError(result.stderr.strip() or 'Keychain operation failed.')
    return result.stdout.strip()

def cert_action(path, install):
    if not path.is_file(): raise ValueError('Start the proxy once to generate its CA certificate.')
    if sys.platform != 'darwin': raise ValueError('Certificate trust requires macOS.')
    # Keep the trust operation in the logged-in user's GUI session, not in
    # the elevated, non-interactive osascript shell. User trust is sufficient
    # for browsers using the current user's macOS trust settings.
    import hashlib, ssl
    fingerprint = hashlib.sha1(ssl.PEM_cert_to_DER_cert(path.read_text())).hexdigest().upper()
    keychain = str(Path.home() / 'Library/Keychains/login.keychain-db')
    try:
        if install:
            if cert_trusted(path): return
            _security(['add-trusted-cert', '-r', 'trustRoot', '-p', 'ssl', '-p', 'basic', '-k', keychain, str(path)])
            if not cert_trusted(path):
                raise ValueError('The certificate was imported but trust verification failed.')
        else:
            existing = _security(['find-certificate', '-a', '-Z', keychain])
            if fingerprint in existing.upper():
                _security(['remove-trusted-cert', str(path)])
                _security(['delete-certificate', '-Z', fingerprint, keychain])
            if cert_trusted(path):
                raise ValueError('The CA is still trusted, possibly in the System keychain from v2.0 or a manual installation. Remove the matching certificate in Keychain Access.')
    except ValueError as exc:
        raise ValueError(f'{exc}\nOpen Keychain Access (or the certificate path shown above) to review the MapRemote CA trust settings interactively. Do not change macOS authorization policies.') from exc

def cert_trusted(path):
    if not path.is_file() or sys.platform != 'darwin': return False
    result = subprocess.run(['/usr/bin/security','verify-cert','-c',str(path),'-p','basic'],capture_output=True)
    return result.returncode == 0
