"""PreToolUse hook for Write, Edit and MultiEdit: rules that block a file change before it happens.

Checks only the text being written (Write content, Edit new_string), so a file that already breaks a rule can
still be fixed.

Everywhere:
- dash.text: no em dash or en dash.
Inside a Unity project:
- unity-api.legacy-input / unity-api.property-block (.cs, comments ignored): no UnityEngine.Input, no
  MaterialPropertyBlock.
- assets.third-party: nothing under Assets/ThirdParty/ is edited.
- assets.meta-guid: a .meta file keeps its guid.
- git.gitattributes: a committed .gitattributes is not changed without the user's approval in chat. This blocks
  rather than asks, because permission modes that auto-approve would let an "ask" through unseen.
"""

import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import guard_common as gc  # noqa: E402

EDIT_TOOLS = {"Write", "Edit", "MultiEdit"}
EM_DASH = chr(0x2014)
EN_DASH = chr(0x2013)
DASHES = {EM_DASH: "em dash", EN_DASH: "en dash"}
GIT_TIMEOUT_SECONDS = 10
META_GUID = re.compile(r"^guid:\s*([0-9a-fA-F]{32})\s*$", re.MULTILINE)
THIRD_PARTY_PREFIX = "Assets/ThirdParty/"

LEGACY_INPUT = re.compile(
    r"UnityEngine\.Input\.|(?<![\w.])Input\.(GetKey|GetKeyDown|GetKeyUp|GetAxis|GetAxisRaw|GetButton|"
    r"GetButtonDown|GetButtonUp|GetMouseButton|GetMouseButtonDown|GetMouseButtonUp|GetTouch|mousePosition|"
    r"mouseScrollDelta|touchCount|touches|anyKey|anyKeyDown|inputString|acceleration)\b"
)
PROPERTY_BLOCK = re.compile(r"\bMaterialPropertyBlock\b|\.SetPropertyBlock\s*\(")
LINE_COMMENT = re.compile(r"//.*$")


def new_texts(tool_input):
    """The strings this call would write."""
    if "content" in tool_input:
        yield tool_input.get("content") or ""
    if "new_string" in tool_input:
        yield tool_input.get("new_string") or ""
    for edit in tool_input.get("edits") or []:
        yield edit.get("new_string") or ""


def old_texts(tool_input):
    if "old_string" in tool_input:
        yield tool_input.get("old_string") or ""
    for edit in tool_input.get("edits") or []:
        yield edit.get("old_string") or ""


def code_lines(text):
    """Lines of C# with // and /// comments removed and block comment lines dropped."""
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith(("*", "/*")):
            continue
        yield LINE_COMMENT.sub("", line)


def project_relative(ctx, path):
    if not ctx.in_unity or not path:
        return None
    rel = os.path.relpath(os.path.abspath(path), ctx.unity_root)
    return gc.normalize(rel)


def check_dashes(ctx, path, texts, findings):
    if gc.is_skipped_path(path) or not ctx.enabled("dash.text"):
        return
    found = sorted({name for text in texts for char, name in DASHES.items() if char in text})
    if found:
        findings.add(
            "dash.text",
            f"{os.path.basename(path) or 'this file'} contains an {' and an '.join(found)}. The rules ban em and "
            "en dashes in code, docs and UI text. Use a comma, colon, parentheses, a plain hyphen for ranges "
            "(2-4), or two sentences. In code, build the character with chr(0x2014) or a \\u escape.",
        )


def check_unity_api(ctx, path, texts, findings):
    if not path.lower().endswith(".cs") or gc.is_skipped_path(path):
        return
    lines = [line for text in texts for line in code_lines(text)]
    name = os.path.basename(path)
    if ctx.unity_enabled("unity-api.legacy-input") and any(LEGACY_INPUT.search(line) for line in lines):
        findings.add(
            "unity-api.legacy-input",
            f"{name} uses the legacy UnityEngine.Input API. Read input only through the Input System, via the "
            "project's single input wrapper class.",
        )
    if ctx.unity_enabled("unity-api.property-block") and any(PROPERTY_BLOCK.search(line) for line in lines):
        findings.add(
            "unity-api.property-block",
            f"{name} uses MaterialPropertyBlock, which breaks SRP batching. Use an instanced material "
            "(renderer.material) for per-object effects instead.",
        )


def check_third_party(ctx, rel, findings):
    if rel and rel.startswith(THIRD_PARTY_PREFIX) and ctx.unity_enabled("assets.third-party"):
        findings.add(
            "assets.third-party",
            f"{rel} is an imported asset pack file. Don't edit Assets/ThirdParty/; copy what you need into "
            "Assets/_Project/<Feature>/ or change it through a prefab variant or your own material.",
        )


def guid_of(text):
    match = META_GUID.search(text or "")
    return match.group(1).lower() if match else None


def check_meta_guid(ctx, path, tool_name, tool_input, findings):
    if not path.endswith(".meta") or not ctx.unity_enabled("assets.meta-guid"):
        return
    message = (
        f"This would change or remove the guid in {os.path.basename(path)}. Every reference to the asset uses "
        "that guid; never change it. Move or rename the asset together with its .meta instead."
    )
    if tool_name == "Write":
        try:
            with open(path, encoding="utf-8", errors="replace") as handle:
                old_guid = guid_of(handle.read())
        except OSError:
            return
        if old_guid and guid_of(tool_input.get("content")) != old_guid:
            findings.add("assets.meta-guid", message)
        return
    for old, new in zip(old_texts(tool_input), new_texts(tool_input)):
        old_guid = guid_of(old)
        if old_guid and guid_of(new) != old_guid:
            findings.add("assets.meta-guid", message)
            return


def check_gitattributes(ctx, path, findings):
    if os.path.basename(path) != ".gitattributes" or not ctx.unity_enabled("git.gitattributes"):
        return
    if is_tracked(path):
        findings.add(
            "git.gitattributes",
            "This changes the committed .gitattributes, which routes LFS and the merge driver for every "
            "contributor. Stop and ask the user in chat, showing the exact change. Only after they approve this "
            "specific change, apply it with a shell command (this guard covers Write and Edit only).",
        )


def is_tracked(path):
    folder = os.path.dirname(os.path.abspath(path))
    try:
        result = subprocess.run(
            ["git", "-C", folder, "ls-files", "--error-unmatch", os.path.basename(path)],
            capture_output=True,
            timeout=GIT_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return result.returncode == 0


def main():
    event = gc.read_event()
    if not event or event.get("tool_name") not in EDIT_TOOLS:
        return
    tool_name = event["tool_name"]
    tool_input = event.get("tool_input") or {}
    path = tool_input.get("file_path") or ""
    ctx = gc.Context(path, event.get("cwd"))
    rel = project_relative(ctx, path)
    texts = list(new_texts(tool_input))

    findings = gc.Findings()
    check_third_party(ctx, rel, findings)
    check_meta_guid(ctx, path, tool_name, tool_input, findings)
    check_dashes(ctx, path, texts, findings)
    check_unity_api(ctx, path, texts, findings)
    check_gitattributes(ctx, path, findings)
    if findings:
        gc.block(findings)


if __name__ == "__main__":
    main()
