"""Feeds sample tool calls to the hook scripts and checks which ones are blocked.

Run: python tests/test_hooks.py   (needs Python 3.8+, git, and bash for the shell guard cases)
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HOOKS = os.path.join(ROOT, "hooks")
EM = "\u2014"
EN = "\u2013"
BIG_FILE_BYTES = 11 * 1024 * 1024
GUARD_ENVS = (
    "BRADENS_GUARDS", "BRADENS_DASH_GUARD", "BRADENS_UNITY_API_GUARD",
    "BRADENS_UNITY_CLI_GUARD", "BRADENS_COMMIT_GUARD", "BRADENS_SHELL_GUARD",
)

failures = []


def run_hook(script, event, extra_env=None):
    env = {k: v for k, v in os.environ.items() if k not in GUARD_ENVS}
    env.update(extra_env or {})
    result = subprocess.run(
        [sys.executable, "-I", os.path.join(HOOKS, script)],
        input=json.dumps(event).encode("utf-8"),
        capture_output=True,
        env=env,
    )
    return result.returncode, result.stderr.decode("utf-8", errors="replace")


def check(name, script, event, expect_block, extra_env=None):
    code, err = run_hook(script, event, extra_env)
    blocked = code == 2
    if blocked != expect_block:
        failures.append(f"{name}: expected {'block' if expect_block else 'allow'}, got exit {code} {err.strip()}")
        print("FAIL", name)
    else:
        print("ok  ", name)


def write(path, content):
    return {"tool_name": "Write", "tool_input": {"file_path": path, "content": content}}


def edit(path, old, new):
    return {"tool_name": "Edit", "tool_input": {"file_path": path, "old_string": old, "new_string": new}}


def bash(command, cwd, tool="Bash"):
    return {"tool_name": tool, "tool_input": {"command": command}, "cwd": cwd}


def edit_cases():
    g = "edit_guard.py"
    check("em dash in Write", g, write("C:/p/README.md", f"Fast {EM} and simple"), True)
    check("en dash in Edit new_string", g, edit("C:/p/a.md", "x", f"2{EN}4"), True)
    check("dash only in old_string is allowed", g, edit("C:/p/a.md", f"a {EM} b", "a, b"), False)
    check("MultiEdit with dash", g, {"tool_name": "MultiEdit", "tool_input": {
        "file_path": "C:/p/a.md", "edits": [{"old_string": "a", "new_string": f"b {EM} c"}]}}, True)
    check("ThirdParty path skipped", g, write("C:/p/Assets/ThirdParty/x.md", f"a {EM} b"), False)
    check("plain hyphen allowed", g, write("C:/p/a.md", "ranges 2-4 - ok"), False)
    check("dash guard off", g, write("C:/p/a.md", f"a {EM} b"), False, {"BRADENS_DASH_GUARD": "off"})
    check("all guards off", g, write("C:/p/a.md", f"a {EM} b"), False, {"BRADENS_GUARDS": "off"})

    check("Input.GetKey in .cs", g, write("C:/p/A.cs", "if (Input.GetKey(KeyCode.Space)) {}"), True)
    check("UnityEngine.Input in .cs", g, write("C:/p/A.cs", "var p = UnityEngine.Input.mousePosition;"), True)
    check("Input System is fine", g, write("C:/p/A.cs", "Keyboard.current.spaceKey.isPressed; _input.Move;"), False)
    check("PlayerInput.GetPlayerByIndex fine", g, write("C:/p/A.cs", "PlayerInput.GetPlayerByIndex(0);"), False)
    check("MaterialPropertyBlock in .cs", g, write("C:/p/A.cs", "var b = new MaterialPropertyBlock();"), True)
    check("SetPropertyBlock in .cs", g, write("C:/p/A.cs", "r.SetPropertyBlock(b);"), True)
    check("MaterialPropertyBlock in comment ok", g, write("C:/p/A.cs", "/// <summary>Not MaterialPropertyBlock.</summary>\nint x;"), False)
    check("Input.GetKey in .md ok", g, write("C:/p/A.md", "Never call Input.GetKey."), False)
    check("Unity API guard off", g, write("C:/p/A.cs", "Input.GetAxis(\"H\");"), False, {"BRADENS_UNITY_API_GUARD": "off"})


def command_cases(tmp):
    g = "command_guard.py"
    check("unity command without project path", g, bash("unity command debugmenu list --caller plugin", tmp), True)
    check("unity command with project path", g, bash("unity command debugmenu list --project-path C:/p", tmp), False)
    check("unity command via PowerShell", g, bash("unity command play", tmp, "PowerShell"), True)
    check("unity command --help", g, bash("unity command --help", tmp), False)
    check("unity status untouched", g, bash("unity status", tmp), False)
    check("unity cli guard off", g, bash("unity command play", tmp), False, {"BRADENS_UNITY_CLI_GUARD": "off"})

    repo = os.path.join(tmp, "repo")
    os.makedirs(os.path.join(repo, "Game", "ProjectSettings"))
    os.makedirs(os.path.join(repo, "Game", "Library"))
    os.makedirs(os.path.join(repo, "Docs", "Library"))
    git = lambda *a: subprocess.run(["git", "-C", repo, *a], check=True, capture_output=True)
    git("init", "-q")
    with open(os.path.join(repo, "a.txt"), "w") as f:
        f.write("a")
    git("add", "a.txt")
    check("clean commit allowed", g, bash('git commit -m "Add a"', repo), False)
    check("dash in commit message", g, bash(f'git commit -m "Add a {EM} b"', repo), True)
    check("git -C path used", g, bash(f'git -C "{repo}" commit -m "Add a"', tmp), False)

    with open(os.path.join(repo, "Game", "Library", "cache.bin"), "w") as f:
        f.write("x")
    git("add", "-f", "Game/Library/cache.bin")
    check("staged Unity Library blocked", g, bash('git commit -m "x"', repo), True)
    check("found through git -C", g, bash(f'git -C "{repo}" commit -m "x"', tmp), True)
    git("rm", "-q", "--cached", "Game/Library/cache.bin")

    with open(os.path.join(repo, "Docs", "Library", "notes.md"), "w") as f:
        f.write("x")
    git("add", "Docs/Library/notes.md")
    check("Library outside a Unity project ok", g, bash('git commit -m "x"', repo), False)

    big = os.path.join(repo, "big.bin")
    with open(big, "wb") as f:
        f.write(b"\0" * BIG_FILE_BYTES)
    check("unstaged big file ignored", g, bash('git commit -m "x"', repo), False)
    check("git add -A then commit sees big file", g, bash('git add -A && git commit -m "x"', repo), True)
    git("add", "big.bin")
    check("staged big file blocked", g, bash('git commit -m "x"', repo), True)
    check("commit guard off", g, bash('git commit -m "x"', repo), False, {"BRADENS_COMMIT_GUARD": "off"})


def shell_cases(tmp):
    bash_exe = shutil.which("bash")
    if not bash_exe:
        print("skip shell guard cases: no bash on PATH")
        return
    for name, command, expect in [
        ("heredoc blocked", "cat > f <<'EOF'\nhi\nEOF", True),
        ("plain command allowed", "ls -la", False),
    ]:
        event = json.dumps(bash(command, tmp)).encode()
        result = subprocess.run(
            [bash_exe, os.path.join(HOOKS, "shell-guard.sh")],
            input=event, capture_output=True, env={**os.environ, "BRADENS_SHELL_GUARD": "on"},
        )
        if (result.returncode == 2) != expect:
            failures.append(f"{name}: got exit {result.returncode}")
            print("FAIL", name)
        else:
            print("ok  ", name)


def main():
    tmp = tempfile.mkdtemp(prefix="bradens-hook-tests-")
    try:
        edit_cases()
        command_cases(tmp)
        shell_cases(tmp)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print()
    if failures:
        print(f"{len(failures)} failed:")
        for failure in failures:
            print("  " + failure)
        sys.exit(1)
    print("all passed")


if __name__ == "__main__":
    main()
