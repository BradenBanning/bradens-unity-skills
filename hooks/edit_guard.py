"""PreToolUse hook for Write, Edit and MultiEdit.

Checks only the text being written (Write content, Edit new_string), so a file that already breaks a rule can
still be fixed. Rules:
- Dash guard (BRADENS_DASH_GUARD): no em dash (U+2014) or en dash (U+2013) in any file.
- Unity API guard (BRADENS_UNITY_API_GUARD), .cs files only, comments ignored: no legacy UnityEngine.Input
  (use the Input System through the project's input wrapper) and no MaterialPropertyBlock (it breaks SRP
  batching; use instanced materials).
"""

import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import guard_common  # noqa: E402

DASH_ENV = "BRADENS_DASH_GUARD"
UNITY_API_ENV = "BRADENS_UNITY_API_GUARD"
EDIT_TOOLS = {"Write", "Edit", "MultiEdit"}
SKIPPED_PATH_PARTS = ("/ThirdParty/", "/Library/", "/PackageCache/")
DASHES = {"—": "em dash", "–": "en dash"}

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


def code_lines(text):
    """Lines of C# with // and /// comments removed and block comment lines dropped."""
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith(("*", "/*")):
            continue
        yield LINE_COMMENT.sub("", line)


def dash_problems(path, texts):
    found = sorted({name for text in texts for char, name in DASHES.items() if char in text})
    if not found:
        return []
    return [
        f"{os.path.basename(path) or 'this file'} contains an {' and an '.join(found)}. The project rules ban em "
        "and en dashes in code, docs and UI text. Use a comma, colon, parentheses, a plain hyphen for ranges "
        "(2-4), or two sentences."
    ]


def unity_api_problems(path, texts):
    problems = []
    lines = [line for text in texts for line in code_lines(text)]
    if any(LEGACY_INPUT.search(line) for line in lines):
        problems.append(
            f"{os.path.basename(path)} uses the legacy UnityEngine.Input API. Read input only through the Input "
            "System, via the project's single input wrapper class."
        )
    if any(PROPERTY_BLOCK.search(line) for line in lines):
        problems.append(
            f"{os.path.basename(path)} uses MaterialPropertyBlock, which breaks SRP batching. Use an instanced "
            "material (renderer.material) for per-object effects instead."
        )
    return problems


def main():
    event = guard_common.read_event()
    if not event or event.get("tool_name") not in EDIT_TOOLS:
        return
    tool_input = event.get("tool_input") or {}
    path = (tool_input.get("file_path") or "").replace("\\", "/")
    if any(part in path for part in SKIPPED_PATH_PARTS):
        return
    texts = list(new_texts(tool_input))

    problems = []
    env_names = []
    if guard_common.is_enabled(DASH_ENV):
        found = dash_problems(path, texts)
        problems += found
        env_names += [DASH_ENV] if found else []
    if path.lower().endswith(".cs") and guard_common.is_enabled(UNITY_API_ENV):
        found = unity_api_problems(path, texts)
        problems += found
        env_names += [UNITY_API_ENV] if found else []
    if problems:
        guard_common.block(problems, " or ".join(env_names))


if __name__ == "__main__":
    main()
