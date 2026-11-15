"""Feeds sample tool calls to the hook scripts and checks each outcome: block, ask, warn (with the rule id) or allow.

Run: python tests/test_hooks.py   (needs Python 3.8+, git, and bash for the shell guard cases)
Each case builds what it needs inside a temporary folder holding a fake Unity project (ProjectSettings/
ProjectVersion.txt) and a plain folder that is not a Unity project.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HOOKS = os.path.join(ROOT, "hooks")
EM = chr(0x2014)
EN = chr(0x2013)
BIG_FILE_BYTES = 11 * 1024 * 1024
GUID_A = "0123456789abcdef0123456789abcdef"
GUID_B = "fedcba9876543210fedcba9876543210"
ALLOW, BLOCK, ASK, WARN = "allow", "block", "ask", "warn"

failures = []
count = 0


def clean_env(extra=None):
    env = {k: v for k, v in os.environ.items() if not k.startswith("BRADENS_") and k != "CLAUDE_PLUGIN_DATA"}
    env.update(extra or {})
    return env


def run_hook(script, event, extra_env=None):
    result = subprocess.run(
        [sys.executable, "-I", os.path.join(HOOKS, script)],
        input=json.dumps(event).encode("utf-8"),
        capture_output=True,
        env=clean_env(extra_env),
    )
    return result.returncode, result.stdout.decode("utf-8", "replace"), result.stderr.decode("utf-8", "replace")


def outcome(code, out):
    if code == 2:
        return BLOCK
    if code != 0:
        return f"exit {code}"
    if not out.strip():
        return ALLOW
    try:
        data = json.loads(out)
    except json.JSONDecodeError:
        return "text"
    specific = data.get("hookSpecificOutput", {})
    if specific.get("permissionDecision") == "ask":
        return ASK
    if specific.get("additionalContext"):
        return WARN
    if data.get("systemMessage"):
        return "message"
    return ALLOW


def check(name, script, event, expect, rule=None, extra_env=None, absent=None):
    global count
    count += 1
    code, out, err = run_hook(script, event, extra_env)
    got = outcome(code, out)
    text = out + err
    ok = got == expect and (rule is None or f"[{rule}]" in text) and (absent is None or f"[{absent}]" not in text)
    if ok:
        print("ok  ", name)
    else:
        failures.append(f"{name}: expected {expect} {rule or ''}, got {got}: {text.strip()[:400]}")
        print("FAIL", name)


def write_ev(path, content, cwd=None):
    return {"tool_name": "Write", "tool_input": {"file_path": path, "content": content}, "cwd": cwd or ""}


def edit_ev(path, old, new, cwd=None):
    return {"tool_name": "Edit", "tool_input": {"file_path": path, "old_string": old, "new_string": new},
            "cwd": cwd or ""}


def cmd_ev(command, cwd, tool="Bash"):
    return {"tool_name": tool, "tool_input": {"command": command}, "cwd": cwd}


def put(path, content="x", binary=False):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb" if binary else "w", encoding=None if binary else "utf-8") as handle:
        handle.write(content)
    return path


def make_unity(folder):
    put(os.path.join(folder, "ProjectSettings", "ProjectVersion.txt"), "m_EditorVersion: 6000.6.9f1\n")
    os.makedirs(os.path.join(folder, "Assets"), exist_ok=True)
    return folder


def git(repo, *args):
    subprocess.run(["git", "-C", repo, *args], check=True, capture_output=True)


# ---- edit guard (PreToolUse) -----------------------------------------------------------------------------------

def edit_guard_cases(unity, plain):
    g = "edit_guard.py"
    p_md = os.path.join(plain, "README.md")
    u_cs = os.path.join(unity, "Assets", "_Project", "Player", "Scripts", "Mover.cs")
    check("dash blocked outside Unity", g, write_ev(p_md, f"Fast {EM} simple"), BLOCK, "dash.text")
    check("en dash in Edit blocked", g, edit_ev(p_md, "x", f"2{EN}4"), BLOCK, "dash.text")
    check("dash only in old_string allowed", g, edit_ev(p_md, f"a {EM} b", "a, b"), ALLOW)
    check("MultiEdit dash blocked", g, {"tool_name": "MultiEdit", "tool_input": {
        "file_path": p_md, "edits": [{"old_string": "a", "new_string": f"b {EM} c"}]}}, BLOCK, "dash.text")
    check("plain hyphen allowed", g, write_ev(p_md, "ranges 2-4 - ok"), ALLOW)
    check("dash group off", g, write_ev(p_md, f"a {EM} b"), ALLOW, extra_env={"BRADENS_DASH_GUARD": "off"})
    check("all guards off", g, write_ev(p_md, f"a {EM} b"), ALLOW, extra_env={"BRADENS_GUARDS": "off"})

    check("legacy Input blocked in Unity", g, write_ev(u_cs, "if (Input.GetKey(KeyCode.Space)) {}"), BLOCK,
          "unity-api.legacy-input")
    check("legacy Input ignored outside Unity", g, write_ev(os.path.join(plain, "A.cs"), "Input.GetKey(k);"), ALLOW)
    check("file outside Unity ignored even from a Unity session", g,
          write_ev(os.path.join(plain, "A.cs"), "Input.GetKey(k);", cwd=unity), ALLOW)
    check("UnityEngine.Input blocked", g, write_ev(u_cs, "var p = UnityEngine.Input.mousePosition;"), BLOCK,
          "unity-api.legacy-input")
    check("Input System allowed", g, write_ev(u_cs, "Keyboard.current.spaceKey.isPressed;"), ALLOW)
    check("PlayerInput allowed", g, write_ev(u_cs, "PlayerInput.GetPlayerByIndex(0);"), ALLOW)
    check("MaterialPropertyBlock blocked", g, write_ev(u_cs, "var b = new MaterialPropertyBlock();"), BLOCK,
          "unity-api.property-block")
    check("MaterialPropertyBlock in XML doc allowed", g,
          write_ev(u_cs, "/// <summary>Not MaterialPropertyBlock.</summary>\nint x;"), ALLOW)

    tp = os.path.join(unity, "Assets", "ThirdParty", "Pack", "Read.txt")
    check("ThirdParty edit blocked", g, write_ev(tp, "hi"), BLOCK, "assets.third-party")
    check("ThirdParty config off", g, write_ev(tp, "hi"), ALLOW, extra_env={"BRADENS_ASSETS_GUARD": "off"})

    meta = put(os.path.join(unity, "Assets", "Thing.prefab.meta"), f"fileFormatVersion: 2\nguid: {GUID_A}\n")
    check("meta guid change via Edit blocked", g, edit_ev(meta, f"guid: {GUID_A}", f"guid: {GUID_B}"), BLOCK,
          "assets.meta-guid")
    check("meta guid change via Write blocked", g, write_ev(meta, f"guid: {GUID_B}\n"), BLOCK, "assets.meta-guid")
    check("meta edit keeping guid allowed", g, write_ev(meta, f"fileFormatVersion: 2\nguid: {GUID_A}\nx: 1\n"),
          ALLOW)

    attributes = put(os.path.join(unity, ".gitattributes"), "*.unity merge=unityyamlmerge eol=lf\n")
    check("untracked .gitattributes allowed", g, edit_ev(attributes, "eol=lf", "eol=lf "), ALLOW)
    git(unity, "add", ".gitattributes")
    check("committed .gitattributes blocked", g, edit_ev(attributes, "eol=lf", "eol=lf "), BLOCK, "git.gitattributes")
    check("committed .gitattributes Write blocked", g, write_ev(attributes, "* text=auto\n"), BLOCK,
          "git.gitattributes")
    check(".gitattributes outside Unity allowed", g,
          edit_ev(os.path.join(plain, ".gitattributes"), "a", "b"), ALLOW)
    put(os.path.join(unity, ".claude", "bradens-unity.json"), json.dumps({"disabledRules": ["git.gitattributes"]}))
    check("config disabledRules turns the rule off", g, edit_ev(attributes, "eol=lf", "eol=lf "), ALLOW)
    os.remove(os.path.join(unity, ".claude", "bradens-unity.json"))


# ---- edit lint (PostToolUse) -----------------------------------------------------------------------------------

GOOD_COMPONENT = """using UnityEngine;

namespace DemoGame.Player
{
    /// <summary>Moves the player.</summary>
    public class Mover : MonoBehaviour
    {
        private const float MaxSpeed = 5f;
        private static readonly int SpeedId = 1;

        [SerializeField, Tooltip("Units per second.")]
        private float _speed = 2f;

        [Tooltip("Body to move.")]
        [SerializeField]
        private Rigidbody _body;

        [field: SerializeField, Tooltip("Jump height.")]
        public float JumpHeight { get; private set; }

        private void Update()
        {
            _body.linearVelocity = Vector3.forward * _speed;
        }
    }
}
"""


def lint_file(unity, rel, content):
    path = put(os.path.join(unity, *rel.split("/")), content)
    return write_ev(path, content)


def lint_edit(unity, rel, content, new):
    path = put(os.path.join(unity, *rel.split("/")), content)
    return edit_ev(path, "OLD", new)


def edit_lint_cases(unity, plain):
    g = "edit_lint.py"
    mover = "Assets/_Project/Player/Scripts/Mover.cs"
    check("clean component passes", g, lint_file(unity, mover, GOOD_COMPONENT), ALLOW)
    check("lint ignored outside Unity", g,
          write_ev(put(os.path.join(plain, "A.cs"), "class A { int bad; // c\n}"), "class A { int bad; // c\n}"),
          ALLOW)
    check("lint ignored outside Unity from a Unity session", g,
          write_ev(os.path.join(plain, "A.cs"), "class A { int bad; // c\n}", cwd=unity), ALLOW)

    bad_name = GOOD_COMPONENT.replace("private float _speed = 2f;", "private float speed = 2f;")
    check("field naming warns", g, lint_file(unity, mover, bad_name), WARN, "style.field-naming")
    implicit = GOOD_COMPONENT.replace("private Rigidbody _body;", "Rigidbody body;")
    check("implicit private naming warns", g, lint_file(unity, mover, implicit), WARN, "style.field-naming")
    public_field = GOOD_COMPONENT.replace("private float _speed = 2f;", "public float Speed = 2f;")
    check("public field not renamed", g, lint_file(unity, mover, public_field), ALLOW, absent="style.field-naming")
    comment = GOOD_COMPONENT.replace("* _speed;", "* _speed; // move")
    check("inline comment warns", g, lint_file(unity, mover, comment), WARN, "style.inline-comment")
    url = GOOD_COMPONENT.replace('"Units per second."', '"See http://x.y"')
    check("// inside a string is fine", g, lint_file(unity, mover, url), ALLOW)
    no_tip = GOOD_COMPONENT.replace('[SerializeField, Tooltip("Units per second.")]', "[SerializeField]")
    check("SerializeField without Tooltip warns", g, lint_file(unity, mover, no_tip), WARN, "style.tooltip")
    no_tip_prop = GOOD_COMPONENT.replace('[field: SerializeField, Tooltip("Jump height.")]',
                                         "[field: SerializeField]")
    check("field: SerializeField without Tooltip warns", g, lint_file(unity, mover, no_tip_prop), WARN,
          "style.tooltip")

    check("namespace wrong feature warns", g,
          lint_file(unity, mover, GOOD_COMPONENT.replace("DemoGame.Player", "DemoGame.Enemies")),
          WARN, "style.namespace")
    put(os.path.join(unity, ".claude", "bradens-unity.json"), json.dumps({"namespaceRoot": "Game"}))
    check("config namespaceRoot honoured", g,
          lint_file(unity, mover, GOOD_COMPONENT.replace("DemoGame.Player", "Game.Player")), ALLOW)
    check("config namespaceRoot mismatch warns", g, lint_file(unity, mover, GOOD_COMPONENT), WARN, "style.namespace")
    os.remove(os.path.join(unity, ".claude", "bradens-unity.json"))
    no_ns = "using UnityEngine;\npublic class Mover : MonoBehaviour\n{\n}\n"
    check("missing namespace warns", g, lint_file(unity, mover, no_ns), WARN, "style.namespace")
    two = GOOD_COMPONENT.replace("    }\n}\n", "    }\n\n    public class Other : MonoBehaviour\n    {\n    }\n}\n")
    check("two MonoBehaviours warn", g, lint_file(unity, mover, two), WARN, "style.one-type-per-file")
    check("file name mismatch warns", g,
          lint_file(unity, "Assets/_Project/Player/Scripts/Walker.cs", GOOD_COMPONENT), WARN, "style.file-name")

    def update_body(line):
        return GOOD_COMPONENT.replace("_body.linearVelocity = Vector3.forward * _speed;", line)

    for rule, line in [
        ("perf.update-find", 'var p = GameObject.Find("Player");'),
        ("perf.update-find", "var c = FindFirstObjectByType<Camera>();"),
        ("perf.update-get-component", "var r = GetComponent<Renderer>();"),
        ("perf.update-alloc", "var list = new List<int>();"),
        ("perf.update-alloc", "var hits = new RaycastHit[8];"),
        ("perf.update-linq", "var n = _items.Where(IsAlive).ToList();"),
        ("perf.update-string", 'label = "Speed " + _speed;'),
        ("perf.update-string", 'label = $"Speed {_speed}";'),
        ("perf.update-instantiate", "Instantiate(_prefab);"),
    ]:
        check(f"{rule}: {line}", g, lint_file(unity, mover, update_body(line)), WARN, rule)
    awake = GOOD_COMPONENT.replace("private void Update()", "private void Awake()").replace(
        "_body.linearVelocity = Vector3.forward * _speed;", "_body = GetComponent<Rigidbody>();")
    check("GetComponent in Awake is fine", g, lint_file(unity, mover, awake), ALLOW)
    old_code = update_body("var r = GetComponent<Renderer>();").replace("OLD", "")
    check("old per-frame issue not re-reported on unrelated Edit", g,
          lint_edit(unity, mover, old_code, "private const float MaxSpeed = 5f;"), ALLOW)

    check("uGUI using warns", g, lint_file(unity, mover, "using UnityEngine.UI;\n" + GOOD_COMPONENT), WARN,
          "tech.ugui")
    check("OnGUI warns", g, lint_file(unity, mover, GOOD_COMPONENT.replace("private void Update()",
                                                                           "private void OnGUI()")), WARN, "tech.ugui")
    check("ParticleSystem warns", g,
          lint_file(unity, mover, update_body("GetComponent<ParticleSystem>();").replace(
              "private void Update()", "private void Awake()")), WARN, "tech.particle-system")
    old_feature = ("using UnityEngine.Rendering;\nusing UnityEngine.Rendering.Universal;\nnamespace DemoGame.Player\n{\n"
                   "    /// <summary>Pass.</summary>\n    public class OutlinePass : ScriptableRenderPass\n    {\n"
                   "        public override void Execute(ScriptableRenderContext context, ref RenderingData data)\n"
                   "        {\n            var cmd = CommandBufferPool.Get();\n        }\n    }\n}\n")
    check("Execute-style renderer pass warns", g,
          lint_file(unity, "Assets/_Project/Player/Scripts/OutlinePass.cs", old_feature), WARN,
          "tech.renderer-feature")
    graph = old_feature.replace("public override void Execute(ScriptableRenderContext context, ref RenderingData data)",
                                "public override void RecordRenderGraph(RenderGraph g, ContextContainer f)"
                                ).replace("var cmd = CommandBufferPool.Get();", "")
    check("RecordRenderGraph pass passes", g,
          lint_file(unity, "Assets/_Project/Player/Scripts/OutlinePass.cs", graph), ALLOW)
    check("new shader warns", g, lint_file(unity, "Assets/_Project/Fx/Glow.shader", "Shader \"X\" {}"), WARN,
          "tech.new-shader")
    check("UberLit shader edit passes", g, lint_file(unity, "Assets/_Project/Fx/UberLit.shader", "Shader \"X\" {}"),
          ALLOW)

    statics = GOOD_COMPONENT.replace("private const float MaxSpeed = 5f;",
                                     "private const float MaxSpeed = 5f;\n        private static int _count;")
    check("mutable static without reset warns", g, lint_file(unity, mover, statics), WARN, "statics.reset")
    reset = statics.replace(
        "private void Update()",
        "[RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.SubsystemRegistration)]\n"
        "        private static void ResetStatics() => _count = 0;\n\n        private void Update()")
    check("static with SubsystemRegistration reset passes", g, lint_file(unity, mover, reset), ALLOW)
    check("statics in Editor folder skipped", g,
          lint_file(unity, "Assets/_Project/Player/Editor/Mover.cs", statics), ALLOW, absent="statics.reset")

    check("hand-edited prefab warns", g, lint_file(unity, "Assets/_Project/Player/Player.prefab", "%YAML 1.1\n"),
          WARN, "yaml.hand-edit")
    check("style group off", g, lint_file(unity, mover, bad_name), ALLOW, extra_env={"BRADENS_STYLE_GUARD": "off"})
    check("ThirdParty C# not linted", g, lint_file(unity, "Assets/ThirdParty/Pack/Mover.cs", bad_name), ALLOW)


# ---- command guard (PreToolUse) --------------------------------------------------------------------------------

def command_guard_cases(tmp, unity, plain):
    g = "command_guard.py"
    full = "unity command debugmenu list --project-path C:/p --caller plugin --skill unity-cli"
    check("unity command complete passes", g, cmd_ev(full, plain), ALLOW)
    check("missing --project-path blocked", g, cmd_ev("unity command play --caller plugin --skill x", plain), BLOCK,
          "unity-cli.project-path")
    check("missing --caller/--skill blocked", g, cmd_ev("unity command play --project-path C:/p", plain), BLOCK,
          "unity-cli.caller")
    check("PowerShell checked too", g, cmd_ev("unity command play", plain, "PowerShell"), BLOCK, "unity-cli.caller")
    check("unity command --help passes", g, cmd_ev("unity command --help", plain), ALLOW)
    check("unity status untouched", g, cmd_ev("unity status", plain), ALLOW)
    check("words in a commit message ignored", g,
          cmd_ev('git commit -m "Check unity command flags"', plain), ALLOW)
    check("full path to unity.exe checked", g,
          cmd_ev('& "C:/Users/me/AppData/Local/Unity/bin/unity.exe" command play', plain, "PowerShell"), BLOCK,
          "unity-cli.caller")
    check("after cd && checked", g, cmd_ev("cd proj && unity command play --project-path p", plain), BLOCK,
          "unity-cli.caller")
    put(os.path.join(unity, ".claude", "bradens-unity.json"), json.dumps({"projectPath": "C:/Repos/Game"}))
    check("configured projectPath mismatch blocked", g, cmd_ev(full, unity), BLOCK, "unity-cli.project-path")
    check("configured projectPath match passes", g, cmd_ev(full.replace("C:/p", "C:/Repos/Game"), unity), ALLOW)
    os.remove(os.path.join(unity, ".claude", "bradens-unity.json"))

    asset = put(os.path.join(unity, "Assets", "_Project", "A.png"), "x")
    put(asset + ".meta", f"guid: {GUID_A}\n")
    check("rm asset without meta blocked", g, cmd_ev("rm Assets/_Project/A.png", unity), BLOCK, "assets.shell-meta")
    check("rm asset with meta passes", g, cmd_ev("rm Assets/_Project/A.png Assets/_Project/A.png.meta", unity),
          ALLOW)
    check("git mv without meta blocked", g, cmd_ev("git mv Assets/_Project/A.png Assets/_Project/B.png", unity),
          BLOCK, "assets.shell-meta")
    check("mv with meta passes", g, cmd_ev(
        "mv Assets/_Project/A.png Assets/_Project/B.png && mv Assets/_Project/A.png.meta Assets/_Project/B.png.meta",
        unity), BLOCK, "assets.shell-meta")
    check("Remove-Item without meta blocked", g,
          cmd_ev("Remove-Item -Path Assets/_Project/A.png", unity, "PowerShell"), BLOCK, "assets.shell-meta")
    check("glob with meta passes", g, cmd_ev("rm Assets/_Project/A.png*", unity), ALLOW)
    check("rm ThirdParty blocked", g, cmd_ev("rm -rf Assets/ThirdParty/Pack", unity), BLOCK, "assets.third-party")
    check("rm outside Unity passes", g, cmd_ev("rm Assets/x.png", plain), ALLOW)


def commit_cases(tmp, unity):
    g = "command_guard.py"
    repo = unity
    put(os.path.join(repo, "notes.txt"), "a")
    git(repo, "add", "notes.txt")
    check("clean commit passes", g, cmd_ev('git commit -m "Add notes"', repo), ALLOW)
    check("dash in commit message blocked", g, cmd_ev(f'git commit -m "Add {EM} notes"', repo), BLOCK, "commit.dash")
    check("git -C path used", g, cmd_ev(f'git -C "{repo}" commit -m "Add notes"', tmp), ALLOW)
    git(repo, "commit", "-q", "-m", "base")

    put(os.path.join(repo, "Library", "cache.bin"), "x")
    git(repo, "add", "-f", "Library/cache.bin")
    check("Library staged blocked", g, cmd_ev('git commit -m "x"', repo), BLOCK, "commit.cache-folders")
    git(repo, "rm", "-q", "--cached", "Library/cache.bin")

    folder = os.path.join(repo, "Assets", "_Project", "Gym")
    script = put(os.path.join(folder, "Gate.cs"), "class Gate {}")
    git(repo, "add", "Assets/_Project/Gym/Gate.cs")
    check("asset without meta blocked", g, cmd_ev('git commit -m "x"', repo), BLOCK, "commit.meta-pairing")
    put(script + ".meta", f"guid: {GUID_B}\n")
    git(repo, "add", "Assets/_Project/Gym/Gate.cs.meta")
    check("new folder without meta blocked", g, cmd_ev('git commit -m "x"', repo), BLOCK, "commit.meta-pairing")
    put(os.path.join(repo, "Assets", "_Project.meta"), f"guid: {GUID_A}\n")
    put(folder + ".meta", f"guid: {GUID_A[::-1]}\n")
    git(repo, "add", "Assets/_Project.meta", "Assets/_Project/Gym.meta")
    check("asset with metas passes", g, cmd_ev('git commit -m "x"', repo), ALLOW)
    git(repo, "commit", "-q", "-m", "gate")
    git(repo, "rm", "-q", "--cached", "Assets/_Project/Gym/Gate.cs")
    check("deleting asset but keeping meta blocked", g, cmd_ev('git commit -m "x"', repo), BLOCK,
          "commit.meta-pairing")
    git(repo, "reset", "-q")

    attributes = put(os.path.join(repo, "settings.txt"), "driver = 'C:/Program Files/Unity/Hub/Editor/6000.6.9f1/"
                                                         "Editor/Data/Tools/UnityYAMLMerge.exe' merge\n")
    git(repo, "add", "settings.txt")
    check("Editor path staged blocked", g, cmd_ev('git commit -m "x"', repo), BLOCK, "commit.editor-path")
    git(repo, "rm", "-q", "--cached", "settings.txt")
    os.remove(attributes)

    texture = put(os.path.join(repo, "Assets", "_Project", "Gym", "Floor.png"), b"\x89PNG", binary=True)
    put(texture + ".meta", f"guid: {GUID_B[::-1]}\n")
    git(repo, "add", "Assets/_Project/Gym/Floor.png", "Assets/_Project/Gym/Floor.png.meta")
    check("texture not in LFS blocked", g, cmd_ev('git commit -m "x"', repo), BLOCK, "commit.lfs-binary")
    git(repo, "reset", "-q")
    put(os.path.join(repo, ".gitattributes"), "*.png filter=lfs diff=lfs merge=lfs -text\n")
    git(repo, "add", ".gitattributes")
    git(repo, "commit", "-q", "-m", "lfs")
    git(repo, "add", "Assets/_Project/Gym/Floor.png", "Assets/_Project/Gym/Floor.png.meta")
    check("texture routed to LFS passes", g, cmd_ev('git commit -m "x"', repo), ALLOW)
    git(repo, "reset", "-q")

    big = os.path.join(repo, "big.bin")
    put(big, b"\0" * BIG_FILE_BYTES, binary=True)
    check("unstaged big file ignored", g, cmd_ev('git commit -m "x"', repo), ALLOW)
    check("git add -A then commit sees big file", g, cmd_ev('git add -A && git commit -m "x"', repo), BLOCK,
          "commit.size")
    git(repo, "add", "big.bin")
    check("staged big file blocked", g, cmd_ev('git commit -m "x"', repo), BLOCK, "commit.size")
    check("commit group off", g, cmd_ev('git commit -m "x"', repo), ALLOW, extra_env={"BRADENS_COMMIT_GUARD": "off"})
    git(repo, "reset", "-q")
    os.remove(big)


# ---- command lint, session and stop ----------------------------------------------------------------------------

def command_lint_cases(unity, plain):
    g = "command_lint.py"
    check("script eval warns", g, cmd_ev("unity command script eval --file x.cs --project-path p", unity), WARN,
          "unity-cli.script-eval")
    check("script eval outside Unity ignored", g, cmd_ev("unity command script eval --file x.cs", plain), ALLOW)
    check("unity-eval.sh warns", g, cmd_ev("bash scripts/unity-eval.sh C:/p show.cs", unity), WARN,
          "unity-cli.script-eval")
    check("script eval named in a message ignored", g,
          cmd_ev('git commit -m "Avoid unity command script eval"', unity), ALLOW, absent="unity-cli.script-eval")
    git(unity, "switch", "-q", "-c", "main")
    check("commit on main warns", g, cmd_ev('git commit -m "x"', unity), WARN, "git.main-branch")
    other = os.path.join(os.path.dirname(unity), "plugin-repo")
    os.makedirs(other, exist_ok=True)
    subprocess.run(["git", "-C", other, "init", "-q", "-b", "main"], check=True, capture_output=True)
    check("cd into a non-Unity repo from a Unity session", g,
          cmd_ev(f'cd "{other}"; git commit -m "x"', unity, "PowerShell"), ALLOW)
    check("git -C a non-Unity repo from a Unity session", g, cmd_ev(f'git -C "{other}" commit -m "x"', unity), ALLOW)
    git(unity, "switch", "-q", "-c", "feature/gate")
    check("commit on feature branch passes", g, cmd_ev('git commit -m "x"', unity), ALLOW)


def session_cases(tmp, unity, plain):
    global count
    count += 1
    code, out, _ = run_hook("session_check.py", {"cwd": unity})
    if code == 0 and "merge.unityyamlmerge.driver is not set" in out:
        print("ok  ", "session check reports missing YAMLMerge")
    else:
        failures.append(f"session check: {code} {out}")
        print("FAIL", "session check reports missing YAMLMerge")
    count += 1
    code, out, _ = run_hook("session_check.py", {"cwd": plain})
    if code == 0 and not out.strip():
        print("ok  ", "session check silent outside Unity")
    else:
        failures.append(f"session check outside Unity: {code} {out}")
        print("FAIL", "session check silent outside Unity")

    data = os.path.join(tmp, "plugin-data")
    env = {"CLAUDE_PLUGIN_DATA": data}
    stop = {"cwd": unity, "session_id": "test-session"}
    check("stop silent outside Unity", "stop_check.py", {"cwd": plain, "session_id": "s"}, ALLOW, extra_env=env)
    check("stop reminds when C# changed", "stop_check.py", stop, "message", extra_env=env)
    check("stop does not repeat for same change", "stop_check.py", stop, ALLOW, extra_env=env)
    put(os.path.join(unity, "Assets", "_Project", "Gym", "Gate2.cs"), "class Gate2 { int _x; }")
    check("stop reminds again after a new change", "stop_check.py", stop, "message", extra_env=env)


def shell_cases(tmp):
    bash_exe = shutil.which("bash")
    if not bash_exe:
        print("skip shell guard cases: no bash on PATH")
        return
    global count
    for name, command, expect in [
        ("heredoc blocked", "cat > f <<'EOF'\nhi\nEOF", True),
        ("plain command allowed", "ls -la", False),
    ]:
        count += 1
        event = json.dumps(cmd_ev(command, tmp)).encode()
        result = subprocess.run(
            [bash_exe, os.path.join(HOOKS, "shell-guard.sh")],
            input=event, capture_output=True, env=clean_env({"BRADENS_SHELL_GUARD": "on"}),
        )
        if (result.returncode == 2) != expect:
            failures.append(f"{name}: got exit {result.returncode}")
            print("FAIL", name)
        else:
            print("ok  ", name)


def main():
    tmp = tempfile.mkdtemp(prefix="bradens-hook-tests-")
    try:
        unity = make_unity(os.path.join(tmp, "DemoGame"))
        plain = os.path.join(tmp, "plain")
        os.makedirs(plain)
        git(unity, "init", "-q", "-b", "work")
        git(unity, "config", "user.email", "test@example.invalid")
        git(unity, "config", "user.name", "Hook Tests")
        edit_guard_cases(unity, plain)
        edit_lint_cases(unity, plain)
        command_guard_cases(tmp, unity, plain)
        commit_cases(tmp, unity)
        command_lint_cases(unity, plain)
        session_cases(tmp, unity, plain)
        shell_cases(tmp)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print()
    if failures:
        print(f"{len(failures)} of {count} failed:")
        for failure in failures:
            print("  " + failure)
        sys.exit(1)
    print(f"all {count} passed")


if __name__ == "__main__":
    main()
