"""Stop hook: when C# files in a Unity project changed, remind the user to verify. Never blocks.

- session.verify-reminder: shows a one-line reminder (run the PlayMode tests and add one for the change; exit
  Play mode after manual tests). It fires once per set of changed .cs files, not after every turn.
"""

import hashlib
import json
import os
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import guard_common as gc  # noqa: E402

GIT_TIMEOUT_SECONDS = 10
STATE_FOLDER_NAME = "bradens-unity-skills"
PLUGIN_DATA_ENV = "CLAUDE_PLUGIN_DATA"


def changed_scripts(unity_root):
    try:
        result = subprocess.run(
            ["git", "-C", unity_root, "status", "--porcelain", "--untracked-files=all", "--", "*.cs"],
            capture_output=True,
            timeout=GIT_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.SubprocessError):
        return []
    if result.returncode != 0:
        return []
    return sorted(line[3:] for line in result.stdout.decode("utf-8", errors="replace").splitlines() if len(line) > 3)


def signature(unity_root, paths):
    digest = hashlib.sha256()
    top = subprocess.run(["git", "-C", unity_root, "rev-parse", "--show-toplevel"], capture_output=True,
                         timeout=GIT_TIMEOUT_SECONDS).stdout.decode().strip() or unity_root
    for path in paths:
        full = os.path.join(top, path)
        mtime = os.path.getmtime(full) if os.path.exists(full) else 0
        digest.update(f"{path}:{mtime}\n".encode())
    return digest.hexdigest()


def state_file(session_id):
    folder = os.environ.get(PLUGIN_DATA_ENV) or os.path.join(tempfile.gettempdir(), STATE_FOLDER_NAME)
    os.makedirs(folder, exist_ok=True)
    safe_id = "".join(c for c in (session_id or "default") if c.isalnum() or c in "-_")
    return os.path.join(folder, f"verify-reminder-{safe_id}.txt")


def main():
    event = gc.read_event() or {}
    ctx = gc.Context(event.get("cwd") or os.getcwd())
    if not ctx.unity_enabled("session.verify-reminder"):
        return
    paths = changed_scripts(ctx.unity_root)
    if not paths:
        return
    sig = signature(ctx.unity_root, paths)
    path = state_file(event.get("session_id"))
    try:
        with open(path, encoding="utf-8") as handle:
            if handle.read().strip() == sig:
                return
    except OSError:
        pass
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(sig)
    message = (
        f"{len(paths)} C# file(s) changed. Before calling it done: run the PlayMode tests and add or extend one "
        "for the change, and exit Play mode after any manual test (unity-verify-change skill)."
    )
    sys.stdout.reconfigure(encoding="utf-8")
    print(json.dumps({"systemMessage": message}))


if __name__ == "__main__":
    main()
