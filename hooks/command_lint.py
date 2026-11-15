"""PostToolUse hook for Bash and PowerShell commands inside a Unity project: rules that only warn.

- unity-cli.script-eval: `unity command script eval` (or unity-eval.sh) ran. Prefer a custom CLI command or a
  reusable script under Tools/.
- git.main-branch: a commit landed directly on main or master. Use short-lived feature branches off main.
"""

import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import guard_common as gc  # noqa: E402

COMMAND_TOOLS = {"Bash", "PowerShell"}
GIT_TIMEOUT_SECONDS = 10
MAIN_BRANCHES = {"main", "master"}
SCRIPT_EVAL = re.compile(
    r"(?:^|[;&|(\n]|\b(?:then|do|exec)\b)\s*(?:&\s*)?[\"']?(?:[\w:.~-]*[\\/])*unity(\.exe)?[\"']?\s+command\s+script"
    r"\s+eval\b|(?:^|[;&|\n]|\bbash\s+)\s*[\"']?(?:[\w:.~-]*[\\/])*unity-eval\.sh"
)
GIT_COMMIT = re.compile(r"(?<![\w-])git(\.exe)?(\s+-[Cc]\s+(\"[^\"]*\"|'[^']*'|\S+))*\s+commit\b")
GIT_DIR_FLAG = re.compile(r"(?<![\w-])git(?:\.exe)?\s+-C\s+(\"[^\"]*\"|'[^']*'|\S+)")
LEADING_CD = re.compile(r"^\s*(?:cd|Set-Location|sl|pushd)\s+(\"[^\"]*\"|'[^']*'|\S+)\s*(?:&&|;)")


def repo_dir_for(command, cwd):
    match = GIT_DIR_FLAG.search(command) or LEADING_CD.search(command)
    if not match:
        return cwd
    path = os.path.expanduser(match.group(1).strip("\"'"))
    return path if os.path.isabs(path) else os.path.join(cwd, path)


def current_branch(repo_dir):
    try:
        result = subprocess.run(
            ["git", "-C", repo_dir, "branch", "--show-current"],
            capture_output=True,
            timeout=GIT_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return result.stdout.decode().strip() if result.returncode == 0 else None


def main():
    event = gc.read_event()
    if not event or event.get("tool_name") not in COMMAND_TOOLS:
        return
    command = (event.get("tool_input") or {}).get("command") or ""
    cwd = event.get("cwd") or os.getcwd()
    repo_dir = repo_dir_for(command, cwd)
    ctx = gc.Context(repo_dir, cwd)
    if not ctx.in_unity:
        return

    findings = gc.Findings()
    if SCRIPT_EVAL.search(command) and ctx.enabled("unity-cli.script-eval"):
        findings.add(
            "unity-cli.script-eval",
            "That used script eval. For anything you'll run again, write a custom `unity command` (or a debug "
            "menu control) or a reusable script under Tools/ instead of one-off evals.",
        )
    if GIT_COMMIT.search(command) and ctx.enabled("git.main-branch"):
        branch = current_branch(repo_dir)
        if branch in MAIN_BRANCHES:
            findings.add(
                "git.main-branch",
                f"That commit went straight to {branch}. This project uses short-lived feature branches off main; "
                "for the next change, create a branch first and merge main in before finishing.",
            )
    if findings:
        gc.warn(findings)


if __name__ == "__main__":
    main()
