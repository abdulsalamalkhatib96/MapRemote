#!/usr/bin/env python3
"""Sign native code inside-out, then seal the enclosing application."""
import os
import subprocess
import sys
from pathlib import Path
from bundle_layout import validate_links

app = Path(sys.argv[1]).resolve()
identity = os.environ.get("MAPREMOTE_SIGN_IDENTITY") or "-"
options = ["--force", "--sign", identity]
if identity != "-":
    options += ["--timestamp", "--options", "runtime"]
else:
    options += ["--timestamp=none"]

def sign(path):
    subprocess.run(["/usr/bin/codesign", *options, str(path)], check=True)

# Mach-O includes native extension modules, executables and dynamic libraries.
magics = {bytes.fromhex(x) for x in ("feedface", "cefaedfe", "feedfacf", "cffaedfe", "cafebabe", "bebafeca", "cafebabf", "bfbafeca")}
validate_links(app)
bundles = []
for root, dirs, files in os.walk(app, followlinks=False):
    for name in dirs:
        path = Path(root) / name
        if not path.is_symlink() and path.suffix in (".app", ".framework", ".xpc", ".appex"):
            bundles.append(path)
    for name in files:
        path = Path(root) / name
        if path.is_symlink() or not path.is_file():
            continue
        with path.open("rb") as stream:
            if stream.read(4) in magics:
                # Avoid treating Java class files as fat Mach-O.
                if "Mach-O" in subprocess.check_output(["/usr/bin/file", "-b", str(path)], text=True):
                    if path == app / "Contents" / "Helpers" / "ProxyHelper":
                        subprocess.run(["/usr/bin/codesign", "--verify", "--strict", str(path)], check=True)
                    else:
                        sign(path)
for path in sorted(bundles, key=lambda p: len(p.parts), reverse=True):
    sign(path)
    subprocess.run(["/usr/bin/codesign", "--verify", "--strict", "--verbose=4", str(path)], check=True)
validate_links(app)
sign(app)
subprocess.run(["/usr/bin/codesign", "--verify", "--deep", "--strict", "--verbose=4", str(app)], check=True)
