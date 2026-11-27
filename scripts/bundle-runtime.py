#!/usr/bin/env python3
"""Build a relocatable CPython + mitmproxy runtime on the target Mac."""
import hashlib
import os
import platform
import shutil
import subprocess
import sys
import tempfile
import urllib.request
from bundle_layout import normalize_links
from pathlib import Path

PBS_TAG = "20261124"
PYTHON = "3.12.16"
MITMPROXY = "12.3.1"

# Pinned SHA-256 digests from the upstream GitHub release asset metadata.
# No unauthenticated API calls (and no CI credentials) are needed at build time.
ASSETS = {
    "arm64": ("aarch64", "431b99a9c2cdd37ad9b06e425be0e520d2dbce0552abe454257abef592fe3634"),
    "x86_64": ("x86_64", "ccce24cfd3f56f62561d2c9480fcc567ca3a9bac68450cd73e11aeb631befa1f"),
}

def asset_for(arch):
    triple, digest = ASSETS[arch]
    name = f"cpython-{PYTHON}%2B{PBS_TAG}-{triple}-apple-darwin-install_only.tar.gz"
    return f"https://github.com/astral-sh/python-build-standalone/releases/download/{PBS_TAG}/{name}", digest

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
        if not item.is_symlink():
            item.unlink()
    # Drop build-time metadata, never runtime libraries or license notices.
    for directory in (dest / "include", dest / "lib" / "pkgconfig", dest / "share" / "man"):
        if directory.is_dir() and not directory.is_symlink():
            shutil.rmtree(directory)
    # Apple strict code-sign verification rejects dangling or escaping symlinks.
    normalize_links(dest)
    subprocess.run([str(python), "-I", "-B", "-c", "import ssl, sqlite3, mitmproxy; print(ssl.OPENSSL_VERSION)"], env=env, check=True)
    print(f"Bundled Python {PYTHON}, mitmproxy {MITMPROXY} ({arch})")

if __name__ == "__main__":
    main()
