#!/usr/bin/env python3
"""Build a relocatable CPython + mitmproxy runtime on the target Mac."""
import hashlib
import json
import os
import platform
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path

PBS_TAG = "20261124"
PYTHON = "3.12.16"
MITMPROXY = "12.3.1"

def get_json(url):
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "MapRemote-build"}
    with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=60) as response:
        return json.load(response)

def asset_for(arch):
    triple = {"arm64": "aarch64", "x86_64": "x86_64"}[arch]
    name = f"cpython-{PYTHON}+{PBS_TAG}-{triple}-apple-darwin-install_only.tar.gz"
    release = get_json(f"https://api.github.com/repos/astral-sh/python-build-standalone/releases/tags/{PBS_TAG}")
    for page in range(1, 21):
        assets = get_json(f"{release['assets_url']}?per_page=100&page={page}")
        for asset in assets:
            if asset["name"] == name:
                digest = asset.get("digest", "")
                if not digest or not digest.startswith("sha256:"):
                    raise RuntimeError("Upstream asset has no SHA-256 digest")
                return asset["browser_download_url"], digest.split(":", 1)[1]
        if len(assets) < 100:
            break
    raise RuntimeError(f"Missing pinned runtime asset: {name}")

def main():
    if sys.platform != "darwin":
        raise SystemExit("Runtime packaging must run on macOS.")
    dest = Path(sys.argv[1]).resolve()
    arch = platform.machine()
    if arch not in ("arm64", "x86_64"):
        raise SystemExit(f"Unsupported architecture: {arch}")
    if dest.exists():
        raise SystemExit(f"Runtime destination already exists: {dest}")
    dest.mkdir(parents=True)
    url, expected = asset_for(arch)
    with tempfile.TemporaryDirectory() as tmp:
        archive = Path(tmp) / "python.tar.gz"
        with urllib.request.urlopen(url, timeout=120) as response, archive.open("wb") as output:
            digest = hashlib.sha256()
            for chunk in iter(lambda: response.read(1024 * 1024), b""):
                output.write(chunk)
                digest.update(chunk)
        if digest.hexdigest() != expected:
            raise RuntimeError("Runtime archive digest mismatch")
        subprocess.run(["/usr/bin/tar", "-xzf", str(archive), "--strip-components", "1", "-C", str(dest)], check=True)
    python = dest / "bin" / "python3"
    env = dict(os.environ, PYTHONNOUSERSITE="1", PYTHONDONTWRITEBYTECODE="1", PIP_DISABLE_PIP_VERSION_CHECK="1")
    for key in ("PYTHONHOME", "PYTHONPATH", "PIP_TARGET", "PIP_PREFIX", "PIP_USER"):
        env.pop(key, None)
    subprocess.run([str(python), "-I", "-m", "pip", "--isolated", "install", "--no-cache-dir", "--only-binary=:all:", f"mitmproxy=={MITMPROXY}"], env=env, check=True)
    subprocess.run([str(python), "-I", "-m", "pip", "check"], env=env, check=True)
    # Record exact resolved versions, preserve all package license metadata.
    with (dest / "installed-packages.txt").open("w") as output:
        subprocess.run([str(python), "-I", "-m", "pip", "freeze", "--all"], env=env, stdout=output, check=True)
    # pip generates console scripts with absolute build paths. The app invokes its own
    # relative entry point instead; remove these non-relocatable launchers.
    for entry in (dest / "bin").iterdir():
        if entry.is_file() and not entry.is_symlink() and not entry.name.startswith("python"):
            with entry.open("rb") as f:
                is_script = f.read(2) == b"#!"
            if is_script:
                entry.unlink()
    # Bytecode can contain build paths and is not required at runtime.
    for item in dest.rglob("*.pyc"):
        item.unlink()
    print(f"Bundled Python {PYTHON}, mitmproxy {MITMPROXY} ({arch})")

if __name__ == "__main__":
    main()
