#!/usr/bin/env bash
# Runs a hook script from this folder with the first working Python 3 (python3, python, py -3).
# If no Python is found the hook allows the call instead of failing every tool use.
script="$(dirname "$0")/$1"
for candidate in "python3" "python" "py -3"; do
  if $candidate -c "import sys; sys.exit(0 if sys.version_info >= (3, 8) else 1)" >/dev/null 2>&1; then
    exec $candidate -I "$script"
  fi
done
exit 0
