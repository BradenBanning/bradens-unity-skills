"""PreToolUse hook for Bash and PowerShell commands.

Rules:
- Unity CLI guard (BRADENS_UNITY_CLI_GUARD): every `unity command` call passes --project-path, so it reaches the
  right Editor when several are open.
- Commit guard (BRADENS_COMMIT_GUARD), on `git commit`:
  - no em or en dash in the command (that is where -m messages live);
  - nothing staged from a Unity project's Library/, Temp/, Logs/, UserSettings/ or obj/ folders;
  - no staged file over 10 MB (LFS files are staged as small pointers, so they pass).
  It checks what is staged when the command starts. When the same command stages everything first
  (`git add -A && git commit`, `git add . ; git commit`, or `git commit -a`), the files that will be staged are
  checked by size on disk too. A `git add <some files>` in the same command is not followed.
"""

import os
import re
import shlex
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import guard_common  # noqa: E402

UNITY_CLI_ENV = "BRADENS_UNITY_CLI_GUARD"
COMMIT_ENV = "BRADENS_COMMIT_GUARD"
COMMAND_TOOLS = {"Bash", "PowerShell"}
MAX_FILE_BYTES = 10 * 1024 * 1024
GIT_TIMEOUT_SECONDS = 10
UNITY_CACHE_FOLDERS = ("Library", "Temp", "Logs", "UserSettings", "obj")
UNITY_PROJECT_MARKER = "ProjectSettings"
EMPTY_SHA = "0" * 40

UNITY_COMMAND = re.compile(r"(?<![\w-])unity(\.exe)?[\"']?\s+command\b")
HELP_FLAG = re.compile(r"(^|\s)(--help|-h)(\s|$)")
GIT_COMMIT = re.compile(r"(?<![\w-])git(\.exe)?(\s+-[Cc]\s+(\"[^\"]*\"|'[^']*'|\S+))*\s+commit\b")
GIT_DIR_FLAG = re.compile(r"(?<![\w-])git(?:\.exe)?\s+-C\s+(\"[^\"]*\"|'[^']*'|\S+)")
LEADING_CD = re.compile(r"^\s*(?:cd|Set-Location|sl|pushd)\s+(\"[^\"]*\"|'[^']*'|\S+)\s*(?:&&|;)")
GIT_ADD_ALL_BEFORE_COMMIT = re.compile(
    r"(?<![\w-])git(\.exe)?(\s+-C\s+\S+)?\s+add\s+([^;&|]*\s)?(-A|--all|\.|\*)(\s|;|&|\|)[\s\S]*\bcommit\b"
)
COMMIT_ALL_FLAG = re.compile(r"\bcommit\b[^;&|]*\s(-[a-zA-Z]*a[a-zA-Z]*|--all)\b")
DASHES = ("—", "–")


def unquote(token):
    try:
        parts = shlex.split(token)
    except ValueError:
        return token.strip("\"'")
    return parts[0] if parts else token


def git(repo_dir, *args):
    result = subprocess.run(
        ["git", "-C", repo_dir, *args],
        capture_output=True,
        timeout=GIT_TIMEOUT_SECONDS,
    )
    if result.returncode != 0:
        return None
    return result.stdout


def repo_dir_for(command, cwd):
    match = GIT_DIR_FLAG.search(command) or LEADING_CD.search(command)
    if not match:
        return cwd
    path = os.path.expanduser(unquote(match.group(1)))
    return path if os.path.isabs(path) else os.path.join(cwd, path)


def is_unity_cache_path(repo_root, rel_path):
    parts = rel_path.split("/")
    for index, part in enumerate(parts[:-1]):
        if part in UNITY_CACHE_FOLDERS:
            project_root = os.path.join(repo_root, *parts[:index])
            if os.path.isdir(os.path.join(project_root, UNITY_PROJECT_MARKER)):
                return True
    return False


def staged_blobs(repo_dir):
    """(path, blob sha) for every file added or changed in the index."""
    raw = git(repo_dir, "diff", "--cached", "--raw", "-z", "--no-abbrev", "--diff-filter=d")
    if not raw:
        return []
    fields = raw.decode("utf-8", errors="replace").split("\0")
    blobs = []
    for index in range(0, len(fields) - 1, 2):
        meta = fields[index].split()
        if len(meta) >= 4 and meta[3] != EMPTY_SHA:
            blobs.append((fields[index + 1], meta[3]))
    return blobs


def blob_sizes(repo_dir, shas):
    if not shas:
        return {}
    result = subprocess.run(
        ["git", "-C", repo_dir, "cat-file", "--batch-check=%(objectname) %(objectsize)"],
        input="\n".join(shas).encode(),
        capture_output=True,
        timeout=GIT_TIMEOUT_SECONDS,
    )
    sizes = {}
    for line in result.stdout.decode().splitlines():
        parts = line.split()
        if len(parts) == 2 and parts[1].isdigit():
            sizes[parts[0]] = int(parts[1])
    return sizes


def pending_paths(repo_dir, include_untracked):
    """Files changed in the working tree that `git add -A` (with untracked) or `commit -a` (without) will stage."""
    raw = git(repo_dir, "status", "--porcelain", "-z", "--untracked-files=all")
    if not raw:
        return []
    paths = []
    for entry in raw.decode("utf-8", errors="replace").split("\0"):
        if len(entry) <= 3 or entry[1] in (" ", "D"):
            continue
        if entry.startswith("??") and not include_untracked:
            continue
        paths.append(entry[3:])
    return paths


def is_lfs(repo_dir, rel_path):
    out = git(repo_dir, "check-attr", "filter", "--", rel_path)
    return bool(out) and out.decode().strip().endswith(": lfs")


def commit_problems(command, cwd):
    problems = []
    if any(dash in command for dash in DASHES):
        problems.append(
            "The commit command contains an em or en dash. The project rules ban them in commit messages; use a "
            "comma, colon or plain hyphen."
        )

    repo_dir = repo_dir_for(command, cwd)
    top = git(repo_dir, "rev-parse", "--show-toplevel")
    if not top:
        return problems
    repo_root = top.decode().strip()

    staged = staged_blobs(repo_root)
    sizes = blob_sizes(repo_root, [sha for _, sha in staged])
    candidates = {path: sizes.get(sha, 0) for path, sha in staged}

    adds_all = bool(GIT_ADD_ALL_BEFORE_COMMIT.search(command))
    if adds_all or COMMIT_ALL_FLAG.search(command):
        for path in pending_paths(repo_root, include_untracked=adds_all):
            full = os.path.join(repo_root, path)
            if path not in candidates and os.path.isfile(full) and not is_lfs(repo_root, path):
                candidates[path] = os.path.getsize(full)

    cache_hits = sorted(path for path in candidates if is_unity_cache_path(repo_root, path))
    if cache_hits:
        shown = ", ".join(cache_hits[:5]) + (" ..." if len(cache_hits) > 5 else "")
        problems.append(
            f"Files from Unity cache folders would be committed ({shown}). Never commit Library/, Temp/, Logs/, "
            "UserSettings/ or obj/: unstage them and add the folders to .gitignore."
        )

    too_big = sorted((path, size) for path, size in candidates.items() if size > MAX_FILE_BYTES)
    if too_big:
        shown = ", ".join(f"{path} ({size / 1024 / 1024:.1f} MB)" for path, size in too_big[:5])
        problems.append(
            f"Files over 10 MB would be committed: {shown}. Track that extension with Git LFS in .gitattributes "
            "(ask the user before changing a committed .gitattributes), then re-add the files."
        )
    return problems


def main():
    event = guard_common.read_event()
    if not event or event.get("tool_name") not in COMMAND_TOOLS:
        return
    command = (event.get("tool_input") or {}).get("command") or ""
    cwd = event.get("cwd") or os.getcwd()

    problems = []
    env_names = []
    if guard_common.is_enabled(UNITY_CLI_ENV):
        if UNITY_COMMAND.search(command) and "--project-path" not in command and not HELP_FLAG.search(command):
            problems.append(
                "`unity command` is missing --project-path. Pass --project-path <project folder> on every call "
                "that reaches the Editor so it targets the right project."
            )
            env_names.append(UNITY_CLI_ENV)
    if guard_common.is_enabled(COMMIT_ENV) and GIT_COMMIT.search(command):
        try:
            found = commit_problems(command, cwd)
        except (OSError, subprocess.SubprocessError):
            found = []
        problems += found
        env_names += [COMMIT_ENV] if found else []
    if problems:
        guard_common.block(problems, " or ".join(env_names))


if __name__ == "__main__":
    main()
