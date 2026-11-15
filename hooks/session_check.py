"""SessionStart hook: in a Unity project, report how its git setup matches the rules. Never changes anything.

- session.yaml-merge: merge.unityyamlmerge.driver is set to a file that exists, and .unity files route to it.
- session.lfs: Git LFS is installed and .gitattributes routes at least one extension to it.
The report goes into Claude's context. Fixes are in the unity-git-setup skill.
"""

import os
import re
import shlex
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import guard_common as gc  # noqa: E402

GIT_TIMEOUT_SECONDS = 10
SAMPLE_SCENE_PATH = "Assets/_check.unity"
MERGE_DRIVER_NAME = "unityyamlmerge"
LFS_FILTER = re.compile(r"filter=lfs")


def git(repo_dir, *args):
    try:
        result = subprocess.run(["git", "-C", repo_dir, *args], capture_output=True, timeout=GIT_TIMEOUT_SECONDS)
    except (OSError, subprocess.SubprocessError):
        return None
    return result.stdout.decode("utf-8", errors="replace").strip() if result.returncode == 0 else None


def driver_binary(driver):
    try:
        parts = shlex.split(driver, posix=True)
    except ValueError:
        return None
    return parts[0] if parts else None


def main():
    event = gc.read_event() or {}
    cwd = event.get("cwd") or os.getcwd()
    ctx = gc.Context(cwd)
    if not ctx.in_unity:
        return
    repo_root = git(ctx.unity_root, "rev-parse", "--show-toplevel")
    problems = []
    if not repo_root:
        problems.append("The project is not in a git repository.")
    else:
        if ctx.enabled("session.yaml-merge"):
            driver = git(repo_root, "config", "--get", "merge.unityyamlmerge.driver")
            binary = driver_binary(driver) if driver else None
            if not driver:
                problems.append("merge.unityyamlmerge.driver is not set in this clone's git config.")
            elif not binary or not os.path.isfile(binary):
                problems.append(f"merge.unityyamlmerge.driver points at a missing file: {binary}.")
            rel = gc.normalize(os.path.relpath(os.path.join(ctx.unity_root, SAMPLE_SCENE_PATH), repo_root))
            attr = git(repo_root, "check-attr", "merge", "--", rel) or ""
            if not attr.endswith(": " + MERGE_DRIVER_NAME):
                problems.append(".gitattributes does not route .unity files to merge=unityyamlmerge.")
        if ctx.enabled("session.lfs"):
            if git(repo_root, "lfs", "version") is None:
                problems.append("Git LFS is not installed (git lfs version failed).")
            attributes = os.path.join(repo_root, ".gitattributes")
            try:
                with open(attributes, encoding="utf-8", errors="replace") as handle:
                    has_lfs = bool(LFS_FILTER.search(handle.read()))
            except OSError:
                has_lfs = False
            if not has_lfs:
                problems.append(".gitattributes routes no file types to Git LFS yet.")

    sys.stdout.reconfigure(encoding="utf-8")
    name = os.path.basename(ctx.unity_root)
    if problems:
        print(f"bradens-unity-skills session check for Unity project {name}:")
        for problem in problems:
            print("- " + problem)
        print("Tell the user once, briefly. To fix, use the unity-git-setup skill; ask before changing a committed "
              ".gitattributes.")
    else:
        print(f"bradens-unity-skills session check for Unity project {name}: UnityYAMLMerge and Git LFS are set up.")


if __name__ == "__main__":
    main()
