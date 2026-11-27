#!/bin/sh
set -eu
ROOT="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
exec "$ROOT/runtime/bin/python3" -I -B "$ROOT/engine_entry.py" "$@"
