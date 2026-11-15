"""Check or set up git for a Unity project: UnityYAMLMerge driver, LFS routing and ignored Editor folders.

usage:
  python unity_git_setup.py check <project folder>   report only, exit 1 if anything is missing
  python unity_git_setup.py apply <project folder>   set the UnityYAMLMerge driver in this clone's local config

apply only touches local git config. It never edits .gitattributes or .gitignore; copy those from the templates
after asking the user.
"""

import json
import os
import platform
import re
import shlex
import subprocess
import sys

DRIVER_KEY = "merge.unityyamlmerge.driver"
NAME_KEY = "merge.unityyamlmerge.name"
RECURSIVE_KEY = "merge.unityyamlmerge.recursive"
DRIVER_NAME = "Unity SmartMerge"
DRIVER_ARGS = "merge -h -p --force %O %B %A %A"
YAML_SAMPLE = "Assets/_check.unity"
LFS_SAMPLE = "Assets/_check.png"
IGNORED_FOLDERS = ("Library/", "Temp/", "Logs/", "UserSettings/")
VERSION_LINE = re.compile(r"^m_EditorVersion:\s*(\S+)", re.MULTILINE)
GIT_TIMEOUT_SECONDS = 20


def git(repo, *args):
    try:
        result = subprocess.run(["git", "-C", repo, *args], capture_output=True, timeout=GIT_TIMEOUT_SECONDS)
    except (OSError, subprocess.SubprocessError):
        return None
    return result.stdout.decode("utf-8", errors="replace").strip() if result.returncode == 0 else None


def editor_version(project):
    path = os.path.join(project, "ProjectSettings", "ProjectVersion.txt")
    with open(path, encoding="utf-8") as handle:
        match = VERSION_LINE.search(handle.read())
    if not match:
        raise SystemExit(f"No m_EditorVersion in {path}")
    return match.group(1)


def hub_editor_folders():
    system = platform.system()
    folders = []
    if system == "Windows":
        folders.append(os.path.join(os.environ.get("ProgramFiles", r"C:\Program Files"), "Unity", "Hub", "Editor"))
        secondary = os.path.join(os.environ.get("APPDATA", ""), "UnityHub", "secondaryInstallPath.json")
        try:
            with open(secondary, encoding="utf-8") as handle:
                extra = json.load(handle)
            if isinstance(extra, str) and extra:
                folders.append(extra)
        except (OSError, json.JSONDecodeError):
            pass
    elif system == "Darwin":
        folders.append("/Applications/Unity/Hub/Editor")
    else:
        folders.append(os.path.expanduser("~/Unity/Hub/Editor"))
    return folders


def merge_tool_path(version):
    system = platform.system()
    for folder in hub_editor_folders():
        root = os.path.join(folder, version)
        if system == "Windows":
            candidate = os.path.join(root, "Editor", "Data", "Tools", "UnityYAMLMerge.exe")
        elif system == "Darwin":
            candidate = os.path.join(root, "Unity.app", "Contents", "Tools", "UnityYAMLMerge")
        else:
            candidate = os.path.join(root, "Editor", "Data", "Tools", "UnityYAMLMerge")
        if os.path.isfile(candidate):
            return candidate
    return None


def repo_root(project):
    root = git(project, "rev-parse", "--show-toplevel")
    if not root:
        raise SystemExit(f"{project} is not in a git repository.")
    return root


def rel_to_repo(repo, project, path):
    return os.path.relpath(os.path.join(project, path), repo).replace("\\", "/")


def check(project):
    repo = repo_root(project)
    results = []
    driver = git(repo, "config", "--get", DRIVER_KEY)
    binary = None
    if driver:
        try:
            binary = shlex.split(driver)[0]
        except (ValueError, IndexError):
            binary = None
    results.append((bool(binary and os.path.isfile(binary)),
                    f"merge driver: {driver or 'not set'}" + ("" if not driver or (binary and os.path.isfile(binary))
                                                                else " (file missing)")))
    attr = git(repo, "check-attr", "merge", "--", rel_to_repo(repo, project, YAML_SAMPLE)) or ""
    results.append((attr.endswith(": unityyamlmerge"), f".unity files: {attr.split(': ')[-1] or 'unrouted'}"))
    lfs = git(repo, "lfs", "version")
    results.append((lfs is not None, f"git lfs: {lfs or 'not installed'}"))
    filt = git(repo, "check-attr", "filter", "--", rel_to_repo(repo, project, LFS_SAMPLE)) or ""
    results.append((filt.endswith(": lfs"), f".png files: filter {filt.split(': ')[-1] or 'none'}"))
    for folder in IGNORED_FOLDERS:
        ignored = git(repo, "check-ignore", "-q", rel_to_repo(repo, project, folder + "x")) is not None
        results.append((ignored, f"{folder} ignored: {'yes' if ignored else 'no'}"))
    for ok, line in results:
        print(("ok      " if ok else "MISSING ") + line)
    return all(ok for ok, _ in results)


def apply(project):
    repo = repo_root(project)
    version = editor_version(project)
    tool = merge_tool_path(version)
    if not tool:
        print(f"Unity {version} is not installed in the Unity Hub folders ({', '.join(hub_editor_folders())}). "
              "Install that version or tell the user; don't point the driver at another version.")
        return False
    git(repo, "config", NAME_KEY, DRIVER_NAME)
    git(repo, "config", DRIVER_KEY, f"'{tool.replace(os.sep, '/')}' {DRIVER_ARGS}")
    git(repo, "config", RECURSIVE_KEY, "binary")
    print(f"Set {DRIVER_KEY} for this clone to Unity {version}'s UnityYAMLMerge.")
    return check(project)


def main():
    if len(sys.argv) != 3 or sys.argv[1] not in ("check", "apply"):
        print(__doc__)
        sys.exit(2)
    project = os.path.abspath(sys.argv[2])
    ok = check(project) if sys.argv[1] == "check" else apply(project)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
