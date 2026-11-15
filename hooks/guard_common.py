"""Shared helpers for the bradens-unity-skills hooks.

A hook reads the tool call as JSON on stdin. Exit code 2 blocks the call and shows stderr to Claude.
Every guard can be turned off with its own environment variable set to "off", or all at once with
BRADENS_GUARDS=off.
"""

import json
import os
import sys

BLOCK_EXIT_CODE = 2
ALL_GUARDS_ENV = "BRADENS_GUARDS"


def is_enabled(env_name):
    """True unless the guard or all guards are switched off."""
    if os.environ.get(ALL_GUARDS_ENV, "").lower() == "off":
        return False
    return os.environ.get(env_name, "").lower() != "off"


def read_event():
    """Parse the hook event from stdin, or None if it is not JSON."""
    raw = sys.stdin.buffer.read().decode("utf-8", errors="replace")
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


def block(problems, env_name):
    """Print every problem and block the tool call."""
    sys.stderr.reconfigure(encoding="utf-8")
    print("Blocked by bradens-unity-skills:", file=sys.stderr)
    for problem in problems:
        print("- " + problem, file=sys.stderr)
    print(f"(If this is a false positive, the user can set {env_name}=off.)", file=sys.stderr)
    sys.exit(BLOCK_EXIT_CODE)
