#!/usr/bin/env python3
"""Relocation test: no installed Python, Homebrew, mitmdump, or system proxy."""
import os
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path

def main():
    app = Path(sys.argv[1]).resolve()
    with tempfile.TemporaryDirectory(prefix="mapremote relocation ") as tmp:
        root = Path(tmp)
        copied = root / "Moved MapRemote.app"
        subprocess.run(["/usr/bin/ditto", str(app), str(copied)], check=True)
        subprocess.run(["/usr/bin/codesign", "--verify", "--deep", "--strict", str(copied)], check=True)
        resources = copied / "Contents" / "Resources"
        python = resources / "runtime" / "bin" / "python3"
        engine = resources / "mitmdump"
        home = root / "home"
        home.mkdir()
        env = {
            "PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
            "HOME": str(home),
            "TMPDIR": str(root),
            "MAPREMOTE_NATIVE": "1",
            "MAPREMOTE_ENGINE": str(engine),
        }
        def run(*args):
            return subprocess.run([str(python), "-E", "-s", "-B", *map(str, args)], env=env, cwd=resources, check=True, timeout=120)
        run("-c", "import sys, pathlib, mitmproxy; assert pathlib.Path(sys.prefix).resolve() == pathlib.Path('runtime').resolve(); print(sys.version)")
        run("-c", "import app, pathlib; assert pathlib.Path(app.engine()).resolve() == pathlib.Path('mitmdump').resolve()")
        subprocess.run([str(engine), "--version"], env=env, check=True, timeout=60)
        run(resources / "smoke_test.py")
        p = subprocess.Popen([str(python), "-E", "-s", "-B", str(resources / "app.py")], env=env, cwd=resources, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        try:
            import select
            ready, _, _ = select.select([p.stdout], [], [], 20)
            if not ready:
                raise RuntimeError("Bundled controller readiness timeout")
            line = p.stdout.readline().strip()
            if not line.startswith("MapRemote: http://127.0.0.1:"):
                raise RuntimeError(f"Unexpected controller readiness: {line!r}")
            url = line.removeprefix("MapRemote: ")
            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
            with opener.open(url, timeout=5) as response:
                assert response.status == 200 and b"MapRemote" in response.read()
        finally:
            if p.poll() is None:
                p.terminate()
            try:
                out, err = p.communicate(timeout=10)
            except subprocess.TimeoutExpired:
                p.kill()
                out, err = p.communicate()
            if err:
                print(err, file=sys.stderr)
        assert p.returncode == 0, f"Controller exited {p.returncode}"
        print("PASS: relocated standalone app, bundled runtime and engine, controller UI, HTTP and HTTPS proxy mapping.")

if __name__ == "__main__":
    main()
