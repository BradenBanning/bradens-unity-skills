"""Shared helpers for the bradens-unity-skills hooks.

A hook reads the tool call as JSON on stdin. Two outcomes:
- block: exit code 2, stderr is shown to Claude and the call does not run (PreToolUse).
- warn: the call already ran; Claude gets the issues as extra context (PostToolUse).
There is no "ask" outcome on purpose: permission modes that auto-approve can let an ask through without the user
seeing it, so anything that needs the user's say blocks and tells Claude to ask in chat.

Every rule has an id "<group>.<name>". A rule is off when any of these holds:
- BRADENS_GUARDS=off (all rules),
- BRADENS_<GROUP>_GUARD=off (the group, dashes in the group become underscores),
- the Unity project's .claude/bradens-unity.json lists the rule id or the group in "disabledRules".
"""

import json
import os
import re
import sys

BLOCK_EXIT_CODE = 2
ALL_GUARDS_ENV = "BRADENS_GUARDS"
CONFIG_RELATIVE_PATH = os.path.join(".claude", "bradens-unity.json")
PROJECT_VERSION_FILE = os.path.join("ProjectSettings", "ProjectVersion.txt")
SKIPPED_PATH_PARTS = ("/ThirdParty/", "/Library/", "/PackageCache/")
GENERIC_FOLDER_NAMES = {"Scripts", "Runtime", "Editor", "Tests", "Prefabs", "Data", "UI"}


def group_env_name(group):
    return "BRADENS_" + group.upper().replace("-", "_") + "_GUARD"


def normalize(path):
    return (path or "").replace("\\", "/")


def find_unity_root(path):
    """The nearest folder at or above path that has ProjectSettings/ProjectVersion.txt, or None."""
    if not path:
        return None
    current = os.path.abspath(path)
    if os.path.isfile(current) or not os.path.exists(current):
        current = os.path.dirname(current)
    while True:
        if os.path.isfile(os.path.join(current, PROJECT_VERSION_FILE)):
            return current
        parent = os.path.dirname(current)
        if parent == current:
            return None
        current = parent


def load_config(unity_root):
    """The project's optional .claude/bradens-unity.json, or an empty dict."""
    if not unity_root:
        return {}
    config_path = os.path.join(unity_root, CONFIG_RELATIVE_PATH)
    try:
        with open(config_path, encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def namespace_root(unity_root, config):
    """Config namespaceRoot, else the project folder name made into a C# identifier."""
    configured = config.get("namespaceRoot")
    if configured:
        return configured
    name = os.path.basename(os.path.normpath(unity_root or ""))
    name = re.sub(r"[^A-Za-z0-9_]", "", name)
    if name and name[0].isdigit():
        name = "_" + name
    return name


class Context:
    """The Unity project a tool call touches, plus its config.

    path_hint is the file or folder the call acts on. The session folder (cwd) is used only when the call names no
    path, so a file or repo outside any Unity project never picks up the rules of the folder the session started in.
    """

    def __init__(self, path_hint, cwd=None):
        target = path_hint or cwd
        self.unity_root = find_unity_root(target) if target else None
        self.config = load_config(self.unity_root)

    @property
    def in_unity(self):
        return self.unity_root is not None

    def enabled(self, rule_id):
        if os.environ.get(ALL_GUARDS_ENV, "").lower() == "off":
            return False
        group = rule_id.split(".", 1)[0]
        if os.environ.get(group_env_name(group), "").lower() == "off":
            return False
        disabled = self.config.get("disabledRules") or []
        return rule_id not in disabled and group not in disabled

    def unity_enabled(self, rule_id):
        return self.in_unity and self.enabled(rule_id)


def is_skipped_path(path):
    path = "/" + normalize(path).lstrip("/")
    return any(part in path for part in SKIPPED_PATH_PARTS)


def read_event():
    """Parse the hook event from stdin, or None if it is not JSON."""
    raw = sys.stdin.buffer.read().decode("utf-8", errors="replace")
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


class Findings:
    """Problems found by one hook run, each tagged with its rule id."""

    def __init__(self):
        self.items = []

    def add(self, rule_id, message):
        self.items.append((rule_id, message))

    def __bool__(self):
        return bool(self.items)

    def lines(self):
        return [f"- [{rule_id}] {message}" for rule_id, message in self.items]

    def off_switch_hint(self):
        groups = sorted({rule_id.split(".", 1)[0] for rule_id, _ in self.items})
        envs = ", ".join(f"{group_env_name(group)}=off" for group in groups)
        return f"(False positive? Add the rule id to disabledRules in {CONFIG_RELATIVE_PATH}, or set {envs}.)"


def block(findings):
    """Print every problem and block the tool call."""
    sys.stderr.reconfigure(encoding="utf-8")
    print("Blocked by bradens-unity-skills:", file=sys.stderr)
    for line in findings.lines():
        print(line, file=sys.stderr)
    print(findings.off_switch_hint(), file=sys.stderr)
    sys.exit(BLOCK_EXIT_CODE)


def warn(findings, event_name="PostToolUse"):
    """Let the call stand and hand Claude the issues to fix."""
    text = "\n".join(
        ["bradens-unity-skills found rule issues in what just ran. Fix them now unless there is a good reason:"]
        + findings.lines()
        + [findings.off_switch_hint()]
    )
    output = {"hookSpecificOutput": {"hookEventName": event_name, "additionalContext": text}}
    sys.stdout.reconfigure(encoding="utf-8")
    print(json.dumps(output))
    sys.exit(0)
