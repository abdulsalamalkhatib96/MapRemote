"""Normalize symlinks in a redistributable runtime before it is signed."""
import os
from pathlib import Path

def normalize_links(root):
    root = Path(root).resolve()
    # Only dangling aliases to removed build tools/metadata may be discarded;
    # unresolved runtime library links are fatal rather than silently ignored.
    removed = []
    for path in sorted(root.rglob("*")):
        if not path.is_symlink():
            continue
        raw = os.readlink(path)
        try:
            resolved = path.resolve(strict=True)
        except (FileNotFoundError, RuntimeError, OSError):
            relative = path.relative_to(root)
            target = Path(raw)
            if (relative.parts[0] == "bin" and not path.name.startswith("python")) or (
                target.suffix == ".pyc" or target.name.endswith("-config")
            ):
                path.unlink()
                removed.append(str(relative))
                print(f"Removed obsolete runtime build alias: {relative} -> {raw}", flush=True)
                continue
            # Python Build Standalone can contain absolute install-prefix links.
            # Rebase only when a unique corresponding file inside this runtime
            # exists. Never follow or include a host file.
            candidates = []
            if target.is_absolute():
                for i in range(1, len(target.parts)):
                    candidate = root.joinpath(*target.parts[i:])
                    if candidate.exists() and not candidate.is_symlink():
                        candidates.append(candidate)
            if len(candidates) != 1:
                raise RuntimeError(f"Unresolved runtime symlink: {relative} -> {raw}")
            resolved = candidates[0].resolve(strict=True)
        if not resolved.is_relative_to(root):
            raise RuntimeError(f"Runtime symlink escapes bundle: {path.relative_to(root)} -> {raw}")
        if Path(raw).is_absolute():
            path.unlink()
            path.symlink_to(os.path.relpath(resolved, path.parent), target_is_directory=resolved.is_dir())
    return removed

def validate_links(root):
    root = Path(root).resolve()
    for path in root.rglob("*"):
        if path.is_symlink():
            raw = os.readlink(path)
            try:
                resolved = path.resolve(strict=True)
            except (OSError, RuntimeError) as exc:
                raise RuntimeError(f"Broken bundle link: {path.relative_to(root)} -> {raw}") from exc
            if Path(raw).is_absolute() or not resolved.is_relative_to(root):
                raise RuntimeError(f"Non-relocatable bundle link: {path.relative_to(root)} -> {raw}")
