"""PreToolUse hook for Bash and PowerShell commands: rules that block a command before it runs.

unity-cli (on every `unity command`):
- unity-cli.project-path: pass --project-path, and when the project config sets projectPath, pass that one.
- unity-cli.caller: pass --caller <name> and --skill <name>.
commit (on `git commit`):
- commit.dash: no em or en dash in the command (that is where -m messages live). Everywhere.
- commit.cache-folders: nothing from a Unity project's Library/, Temp/, Logs/, UserSettings/ or obj/.
- commit.size: no staged file over 10 MB (LFS files are staged as small pointers, so they pass). Everywhere.
- commit.meta-pairing: every added or deleted asset under Assets/ goes with its .meta, and new folders have one.
- commit.editor-path: no absolute Unity Editor path (UnityYAMLMerge, Hub/Editor) in staged changes.
- commit.lfs-binary: textures, models, audio, video and fonts are routed to Git LFS.
assets (shell file operations inside a Unity project):
- assets.shell-meta: rm / mv / git rm / git mv / Remove-Item / Move-Item on an Assets/ path takes its .meta too.
- assets.third-party: nothing under Assets/ThirdParty/ is moved or deleted.

The commit rules read the index when the command starts. When the same command stages everything first
(`git add -A && git commit`, `git add . ; git commit`, or `git commit -a`), the files that will be staged are
checked on disk too. A `git add <some files>` in the same command is not followed.
"""

import os
import re
import shlex
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import guard_common as gc  # noqa: E402

COMMAND_TOOLS = {"Bash", "PowerShell"}
MAX_FILE_BYTES = 10 * 1024 * 1024
GIT_TIMEOUT_SECONDS = 15
UNITY_CACHE_FOLDERS = ("Library", "Temp", "Logs", "UserSettings", "obj")
ASSETS_PREFIX = "Assets/"
THIRD_PARTY_PREFIX = "Assets/ThirdParty/"
META_SUFFIX = ".meta"
DASHES = (chr(0x2014), chr(0x2013))
MAX_SHOWN = 5
LFS_EXTENSIONS = {
    ".png", ".jpg", ".jpeg", ".tga", ".tif", ".tiff", ".psd", ".exr", ".hdr", ".bmp", ".gif",
    ".fbx", ".obj", ".blend", ".max", ".ma", ".mb", ".dae", ".3ds",
    ".wav", ".mp3", ".ogg", ".aif", ".aiff", ".flac",
    ".mp4", ".mov", ".webm", ".avi",
    ".ttf", ".otf",
}

UNITY_COMMAND = re.compile(
    r"(?:^|[;&|(\n]|\b(?:then|do|exec)\b)\s*(?:&\s*)?[\"']?(?:[\w:.~-]*[\\/])*unity(\.exe)?[\"']?\s+command\b"
)
HELP_FLAG = re.compile(r"(^|\s)(--help|-h)(\s|$)")
PROJECT_PATH_VALUE = re.compile(r"--project-path[=\s]+(\"[^\"]*\"|'[^']*'|\S+)")
GIT_COMMIT = re.compile(r"(?<![\w-])git(\.exe)?(\s+-[Cc]\s+(\"[^\"]*\"|'[^']*'|\S+))*\s+commit\b")
GIT_DIR_FLAG = re.compile(r"(?<![\w-])git(?:\.exe)?\s+-C\s+(\"[^\"]*\"|'[^']*'|\S+)")
LEADING_CD = re.compile(r"^\s*(?:cd|Set-Location|sl|pushd)\s+(\"[^\"]*\"|'[^']*'|\S+)\s*(?:&&|;)")
GIT_ADD_ALL_BEFORE_COMMIT = re.compile(
    r"(?<![\w-])git(\.exe)?(\s+-C\s+\S+)?\s+add\s+([^;&|]*\s)?(-A|--all|\.|\*)(\s|;|&|\|)[\s\S]*\bcommit\b"
)
COMMIT_ALL_FLAG = re.compile(r"\bcommit\b[^;&|]*\s(-[a-zA-Z]*a[a-zA-Z]*|--all)\b")
EDITOR_PATH = re.compile(
    r"([A-Za-z]:[\\/]|/Applications/|/opt/|/home/[^/\s]+/)[^'\"\n]*?(UnityYAMLMerge|Hub[\\/]+Editor[\\/])",
    re.IGNORECASE,
)
SEGMENT_SPLIT = re.compile(r"&&|\|\||;|\||\n")
REMOVE_VERBS = {"rm", "del", "erase", "remove-item", "ri", "rmdir", "rd"}
MOVE_VERBS = {"mv", "move", "move-item", "mi", "rename-item", "ren", "rni"}
DESTINATION_FLAGS = {"-destination", "-dest", "-newname"}


def unquote(token):
    try:
        parts = shlex.split(token)
    except ValueError:
        return token.strip("\"'")
    return parts[0] if parts else token


def git(repo_dir, *args, stdin=None):
    result = subprocess.run(
        ["git", "-C", repo_dir, *args],
        input=stdin,
        capture_output=True,
        timeout=GIT_TIMEOUT_SECONDS,
    )
    if result.returncode != 0:
        return None
    return result.stdout


def resolve(path, cwd):
    path = os.path.expanduser(unquote(path))
    return path if os.path.isabs(path) else os.path.join(cwd, path)


def repo_dir_for(command, cwd):
    match = GIT_DIR_FLAG.search(command) or LEADING_CD.search(command)
    return resolve(match.group(1), cwd) if match else cwd


def unity_rel(path):
    """(unity root, path relative to it with forward slashes) or (None, None)."""
    root = gc.find_unity_root(path)
    if not root:
        return None, None
    return root, gc.normalize(os.path.relpath(os.path.abspath(path), root))


def shown(paths):
    items = list(paths)
    return ", ".join(items[:MAX_SHOWN]) + (" ..." if len(items) > MAX_SHOWN else "")


# ---- unity command ---------------------------------------------------------------------------------------------

def check_unity_cli(command, ctx, findings):
    if not UNITY_COMMAND.search(command) or HELP_FLAG.search(command):
        return
    if ctx.enabled("unity-cli.project-path"):
        match = PROJECT_PATH_VALUE.search(command)
        expected = ctx.config.get("projectPath")
        if not match:
            findings.add(
                "unity-cli.project-path",
                "`unity command` is missing --project-path. Pass --project-path <project folder> on every call "
                "that reaches the Editor so it targets the right project.",
            )
        elif expected and os.path.normcase(os.path.normpath(unquote(match.group(1)))) != os.path.normcase(
            os.path.normpath(expected)
        ):
            findings.add(
                "unity-cli.project-path",
                f"--project-path {unquote(match.group(1))} does not match this project's configured projectPath "
                f"{expected}.",
            )
    if ctx.enabled("unity-cli.caller") and not ("--caller" in command and "--skill" in command):
        findings.add(
            "unity-cli.caller",
            "`unity command` needs --caller plugin --skill <skill name> so the Editor log shows who sent it.",
        )


# ---- shell file operations on assets ---------------------------------------------------------------------------

def split_tokens(segment, tool_name):
    try:
        return shlex.split(segment, posix=tool_name == "Bash")
    except ValueError:
        return segment.split()


def operation_targets(tokens):
    """(verb kind, source paths) for a remove or move command, else (None, [])."""
    if not tokens:
        return None, []
    words = [token.strip("\"'") for token in tokens]
    if words[0].lower() in ("git", "git.exe") and len(words) > 1:
        words = words[1:]
    verb = words[0].lower()
    if verb in REMOVE_VERBS:
        kind = "remove"
    elif verb in MOVE_VERBS:
        kind = "move"
    else:
        return None, []
    paths = []
    skip_next = False
    for word in words[1:]:
        if skip_next:
            skip_next = False
            continue
        if word.lower() in DESTINATION_FLAGS:
            skip_next = True
            continue
        if word.startswith("-"):
            continue
        paths.append(word)
    if kind == "move" and len(paths) > 1 and not any(w.lower() in DESTINATION_FLAGS for w in words):
        paths = paths[:-1]
    return kind, paths


def check_shell_assets(command, tool_name, cwd, findings):
    for segment in SEGMENT_SPLIT.split(command):
        kind, paths = operation_targets(split_tokens(segment.strip(), tool_name))
        if not kind:
            continue
        named = {gc.normalize(resolve(p, cwd)).lower() for p in paths}
        for raw in paths:
            if "Assets" not in raw:
                continue
            full = resolve(raw, cwd)
            root, rel = unity_rel(full)
            if not root or not rel.startswith(ASSETS_PREFIX):
                continue
            ctx = gc.Context(full)
            if rel.startswith(THIRD_PARTY_PREFIX) and ctx.enabled("assets.third-party"):
                findings.add(
                    "assets.third-party",
                    f"{rel} is part of an imported asset pack. Don't {kind} files under Assets/ThirdParty/.",
                )
                continue
            if rel.endswith(META_SUFFIX) or "*" in raw or not ctx.enabled("assets.shell-meta"):
                continue
            meta = gc.normalize(full.rstrip("/\\") + META_SUFFIX).lower()
            if meta not in named:
                findings.add(
                    "assets.shell-meta",
                    f"This would {kind} {rel} without {os.path.basename(rel.rstrip('/'))}{META_SUFFIX}. Move, "
                    "rename and delete an asset together with its .meta (or do it in the Editor), or every "
                    "reference to it breaks.",
                )


# ---- git commit ------------------------------------------------------------------------------------------------

def staged_entries(repo_root):
    """(status letter, path) for the index against HEAD, renames split into delete + add."""
    raw = git(repo_root, "diff", "--cached", "--name-status", "-z", "--no-renames")
    if not raw:
        return []
    fields = raw.decode("utf-8", errors="replace").split("\0")
    return [(fields[i][:1], fields[i + 1]) for i in range(0, len(fields) - 1, 2)]


def staged_blob_sizes(repo_root):
    raw = git(repo_root, "diff", "--cached", "--raw", "-z", "--no-abbrev", "--diff-filter=d")
    if not raw:
        return {}
    fields = raw.decode("utf-8", errors="replace").split("\0")
    shas = {}
    for i in range(0, len(fields) - 1, 2):
        meta = fields[i].split()
        if len(meta) >= 4 and set(meta[3]) != {"0"}:
            shas[fields[i + 1]] = meta[3]
    if not shas:
        return {}
    out = git(repo_root, "cat-file", "--batch-check=%(objectname) %(objectsize)",
              stdin="\n".join(shas.values()).encode()) or b""
    by_sha = {}
    for line in out.decode().splitlines():
        parts = line.split()
        if len(parts) == 2 and parts[1].isdigit():
            by_sha[parts[0]] = int(parts[1])
    return {path: by_sha.get(sha, 0) for path, sha in shas.items()}


def pending_paths(repo_root, include_untracked):
    """Files `git add -A` (with untracked) or `commit -a` (without) will stage."""
    raw = git(repo_root, "status", "--porcelain", "-z", "--untracked-files=all")
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


def lfs_paths(repo_root, paths):
    if not paths:
        return set()
    out = git(repo_root, "check-attr", "-z", "filter", "--stdin", stdin="\0".join(paths).encode() + b"\0")
    if not out:
        return set()
    fields = out.decode("utf-8", errors="replace").split("\0")
    return {fields[i] for i in range(0, len(fields) - 2, 3) if fields[i + 2] == "lfs"}


def is_unity_cache_path(repo_root, rel_path):
    parts = rel_path.split("/")
    for index, part in enumerate(parts[:-1]):
        if part in UNITY_CACHE_FOLDERS:
            project_root = os.path.join(repo_root, *parts[:index])
            if os.path.isfile(os.path.join(project_root, gc.PROJECT_VERSION_FILE)):
                return True
    return False


def unity_asset_rel(repo_root, path):
    """Path relative to its Unity project if it is under that project's Assets/, else None."""
    root, rel = unity_rel(os.path.join(repo_root, path))
    if root and rel.startswith(ASSETS_PREFIX):
        return rel
    return None


def check_meta_pairing(repo_root, entries, findings):
    index_raw = git(repo_root, "ls-files", "-z") or b""
    index = set(index_raw.decode("utf-8", errors="replace").split("\0"))
    index.update(path for status, path in entries if status != "D")
    folders = set()
    for path in index:
        parts = path.split("/")
        for depth in range(1, len(parts)):
            folders.add("/".join(parts[:depth]))
    missing = []
    orphaned = []
    for status, path in entries:
        rel = unity_asset_rel(repo_root, path)
        if not rel or not gc.Context(os.path.join(repo_root, path)).enabled("commit.meta-pairing"):
            continue
        if path.endswith(META_SUFFIX):
            asset = path[: -len(META_SUFFIX)]
            if status == "A" and asset not in index and asset not in folders:
                orphaned.append(path)
            continue
        meta = path + META_SUFFIX
        if status == "A" and meta not in index:
            missing.append(path)
        if status == "D" and meta in index:
            orphaned.append(meta)
        if status == "A":
            parts = path.split("/")
            for depth in range(1, len(parts)):
                folder = "/".join(parts[:depth])
                if unity_asset_rel(repo_root, folder) and folder + META_SUFFIX not in index:
                    missing.append(folder + "/")
    missing = sorted(set(missing))
    orphaned = sorted(set(orphaned))
    if missing:
        findings.add(
            "commit.meta-pairing",
            f"Assets staged without their .meta: {shown(missing)}. Let the Editor import them (it writes the "
            ".meta) and stage the .meta files too.",
        )
    if orphaned:
        findings.add(
            "commit.meta-pairing",
            f".meta files without their asset: {shown(orphaned)}. Delete or move each .meta together with its "
            "asset.",
        )


def check_editor_path(repo_root, findings):
    diff = git(repo_root, "diff", "--cached", "-U0", "--no-color", "--no-ext-diff") or b""
    hits = []
    current = None
    for line in diff.decode("utf-8", errors="replace").splitlines():
        if line.startswith("+++ "):
            current = line[6:] if line.startswith("+++ b/") else line[4:]
        elif line.startswith("+") and EDITOR_PATH.search(line) and current:
            hits.append(current)
    hits = sorted(set(h for h in hits if gc.find_unity_root(os.path.join(repo_root, h)) or h == ".gitattributes"))
    if hits:
        findings.add(
            "commit.editor-path",
            f"A machine-specific Unity Editor path is staged in {shown(hits)}. Keep Editor paths (UnityYAMLMerge "
            "driver) in local git config only, never in committed files.",
        )


def commit_findings(command, cwd, findings):
    ctx = gc.Context(None)
    if any(dash in command for dash in DASHES) and ctx.enabled("commit.dash"):
        findings.add(
            "commit.dash",
            "The commit command contains an em or en dash. The rules ban them in commit messages; use a comma, "
            "colon or plain hyphen.",
        )

    top = git(repo_dir_for(command, cwd), "rev-parse", "--show-toplevel")
    if not top:
        return
    repo_root = top.decode().strip()

    entries = staged_entries(repo_root)
    sizes = staged_blob_sizes(repo_root)
    candidates = dict(sizes)
    adds_all = bool(GIT_ADD_ALL_BEFORE_COMMIT.search(command))
    if adds_all or COMMIT_ALL_FLAG.search(command):
        pending = [p for p in pending_paths(repo_root, include_untracked=adds_all) if p not in candidates]
        lfs = lfs_paths(repo_root, pending)
        for path in pending:
            full = os.path.join(repo_root, path)
            if os.path.isfile(full):
                candidates[path] = 0 if path in lfs else os.path.getsize(full)
                entries.append(("A", path))

    if ctx.enabled("commit.cache-folders"):
        hits = sorted(p for p in candidates if is_unity_cache_path(repo_root, p))
        if hits:
            findings.add(
                "commit.cache-folders",
                f"Files from Unity cache folders would be committed ({shown(hits)}). Never commit Library/, Temp/, "
                "Logs/, UserSettings/ or obj/: unstage them and add the folders to .gitignore.",
            )

    if ctx.enabled("commit.size"):
        too_big = sorted((p, s) for p, s in candidates.items() if s > MAX_FILE_BYTES)
        if too_big:
            findings.add(
                "commit.size",
                "Files over 10 MB would be committed: "
                + shown(f"{p} ({s / 1024 / 1024:.1f} MB)" for p, s in too_big)
                + ". Track that extension with Git LFS in .gitattributes (ask the user before changing a "
                "committed .gitattributes), then re-add the files.",
            )

    unity_paths = [p for p in candidates if gc.find_unity_root(os.path.join(repo_root, p))]
    if not unity_paths and not any(gc.find_unity_root(os.path.join(repo_root, p)) for _, p in entries):
        return

    check_meta_pairing(repo_root, entries, findings)

    if gc.Context(repo_root, cwd).enabled("commit.editor-path"):
        check_editor_path(repo_root, findings)

    binaries = [p for p in unity_paths if os.path.splitext(p)[1].lower() in LFS_EXTENSIONS]
    if binaries and gc.Context(repo_root, cwd).enabled("commit.lfs-binary"):
        not_lfs = sorted(set(binaries) - lfs_paths(repo_root, binaries))
        if not_lfs:
            findings.add(
                "commit.lfs-binary",
                f"Binary assets not routed to Git LFS: {shown(not_lfs)}. Add their extensions to .gitattributes "
                "with filter=lfs (ask the user before changing a committed .gitattributes), run git lfs install, "
                "then unstage and re-add them.",
            )


def main():
    event = gc.read_event()
    if not event or event.get("tool_name") not in COMMAND_TOOLS:
        return
    tool_name = event["tool_name"]
    command = (event.get("tool_input") or {}).get("command") or ""
    cwd = event.get("cwd") or os.getcwd()
    ctx = gc.Context(repo_dir_for(command, cwd))

    findings = gc.Findings()
    check_unity_cli(command, ctx, findings)
    try:
        check_shell_assets(command, tool_name, cwd, findings)
        if GIT_COMMIT.search(command):
            commit_findings(command, cwd, findings)
    except (OSError, subprocess.SubprocessError, ValueError):
        pass
    if findings:
        gc.block(findings)


if __name__ == "__main__":
    main()
