"""PostToolUse hook for Write, Edit and MultiEdit inside a Unity project: fuzzy rules that only warn.

The edit stands; Claude gets the issues as context to fix. Line rules report only lines the edit wrote, so old
code doesn't nag on every edit. File rules report on Write, or when the edit touches what they look at.

style (.cs):    style.field-naming, style.inline-comment, style.tooltip, style.namespace, style.one-type-per-file,
                style.file-name
perf (.cs):     perf.update-find, perf.update-get-component, perf.update-alloc, perf.update-linq,
                perf.update-string, perf.update-instantiate (inside Update, FixedUpdate and LateUpdate)
tech:           tech.ugui, tech.particle-system, tech.renderer-feature (.cs), tech.new-shader (.shader)
statics (.cs):  statics.reset (outside Editor folders)
yaml:           yaml.hand-edit (.unity, .prefab, .asset, .mat and other serialized assets)
"""

import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import guard_common as gc  # noqa: E402

EDIT_TOOLS = {"Write", "Edit", "MultiEdit"}
PROJECT_FEATURE = re.compile(r"(?:^|/)Assets/_Project/([^/]+)/")
UBER_SHADER_NAME = "UberLit"
YAML_EXTENSIONS = {
    ".unity", ".prefab", ".asset", ".mat", ".anim", ".controller", ".overridecontroller", ".physicmaterial",
    ".playable", ".mask", ".mixer", ".spriteatlas", ".terrainlayer", ".rendertexture", ".preset", ".lighting",
}
UPDATE_METHODS = re.compile(r"\bvoid\s+(Update|FixedUpdate|LateUpdate)\s*\(\s*\)")
STRING_LITERAL = re.compile(r'@?\$?"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])\'')
TYPE_DECLARATION = re.compile(r"\b(class|struct|interface|record|enum)\s+\w+")
FIELD = re.compile(
    r"^\s*(?P<attrs>(?:\[[^\]]*\]\s*)*)"
    r"(?P<mods>(?:(?:private|protected|internal|public|static|readonly|const|volatile|new)\s+)*)"
    r"(?P<event>event\s+)?"
    r"(?P<type>[A-Za-z_][\w.]*(?:<[^;=()]*>)?(?:\[\s*,*\s*\])*\??)\s+"
    r"(?P<name>[A-Za-z_]\w*)\s*(?:=(?!>)[^;]*)?;\s*$"
)
AUTO_PROPERTY = re.compile(r"^\s*(?P<attrs>(?:\[[^\]]*\]\s*)*).*\{\s*(get|set)\s*;")
ATTRIBUTE_ONLY = re.compile(r"^\s*(\[[^\]]*\]\s*)+$")
PRIVATE_FIELD_NAME = re.compile(r"^_[a-z][A-Za-z0-9]*$")
NAMESPACE = re.compile(r"^\s*namespace\s+([\w.]+)", re.MULTILINE)
UNITY_OBJECT_TYPE = re.compile(
    r"\bclass\s+(\w+)(?:<[^>]*>)?\s*:\s*(?:[\w.]+\.)?"
    r"(MonoBehaviour|ScriptableObject|EditorWindow|Editor|StateMachineBehaviour)\b"
)
NON_KEYWORD_TYPES = {"return", "throw", "await", "yield", "using", "goto", "else", "case", "var"}

PERF_RULES = [
    ("perf.update-find", re.compile(
        r"\b(GameObject\.Find\w*|Find\w*ObjectOfType|FindObjectsOfType|FindFirstObjectByType|FindAnyObjectByType|"
        r"FindObjectsByType|FindWithTag|FindGameObjectsWithTag)\s*[<(]|\.Find\s*\("),
     "calls Find in a per-frame method. Cache the reference in Awake/Start or get it injected."),
    ("perf.update-get-component", re.compile(r"\bGetComponents?(InChildren|InParent)?\s*[<(]"),
     "calls GetComponent in a per-frame method. Cache the component in Awake."),
    ("perf.update-alloc", re.compile(
        r"\bnew\s+(List|Dictionary|HashSet|Queue|Stack|StringBuilder|LinkedList)\s*<|\bnew\s+[\w.]+\s*\[[^\]]"),
     "allocates a collection in a per-frame method. Reuse a field or rent from UnityEngine.Pool."),
    ("perf.update-linq", re.compile(
        r"\.(Where|Select|SelectMany|OrderBy|OrderByDescending|ToList|ToArray|ToDictionary|GroupBy|Distinct)\s*\("),
     "uses LINQ in a per-frame method, which allocates. Use a plain loop over a cached collection."),
    ("perf.update-string", re.compile(r'\$"|"\s*\+|\+\s*"|\bstring\.(Format|Concat)\s*\('),
     "builds a string in a per-frame method, which allocates. Update text only when the value changes."),
    ("perf.update-instantiate", re.compile(r"\bInstantiate\s*[<(]"),
     "instantiates in a per-frame method. Pool anything spawned per frame with UnityEngine.Pool."),
]
TECH_LINE_RULES = [
    ("tech.ugui", re.compile(r"^\s*using\s+UnityEngine\.UI\s*;|\bCanvas\b|\bOnGUI\s*\(|\b(Editor)?GUILayout\."),
     "uses uGUI or IMGUI. Build UI, HUD and editor tools with UI Toolkit (UIDocument, VisualElement, CreateGUI)."),
    ("tech.particle-system", re.compile(r"\bParticleSystem\b"),
     "uses the Shuriken ParticleSystem. Use VFX Graph (VisualEffect) for particles."),
]


def strip_strings(line):
    return STRING_LITERAL.sub('""', line)


def comment_free(line):
    """The line without strings and without any // comment."""
    code = strip_strings(line)
    index = code.find("//")
    return code if index < 0 else code[:index]


def new_texts(tool_input):
    if "content" in tool_input:
        yield tool_input.get("content") or ""
    if "new_string" in tool_input:
        yield tool_input.get("new_string") or ""
    for edit in tool_input.get("edits") or []:
        yield edit.get("new_string") or ""


class Source:
    """A C# file split into lines, with brace depth and type-body depths per line."""

    def __init__(self, text):
        self.lines = text.splitlines()
        self.depth_at_start = []
        self.type_body_lines = set()
        depth = 0
        type_depths = set()
        pending_type = False
        for number, line in enumerate(self.lines):
            self.depth_at_start.append(depth)
            code = comment_free(line)
            if depth in type_depths:
                self.type_body_lines.add(number)
            if TYPE_DECLARATION.search(code):
                pending_type = True
            for char in code:
                if char == "{":
                    depth += 1
                    if pending_type:
                        type_depths.add(depth)
                        pending_type = False
                elif char == "}":
                    type_depths.discard(depth)
                    depth -= 1

    def attributes_before(self, number):
        """Attribute text on the lines directly above line number."""
        collected = []
        index = number - 1
        while index >= 0 and ATTRIBUTE_ONLY.match(self.lines[index]):
            collected.append(self.lines[index])
            index -= 1
        return " ".join(collected)

    def method_body_lines(self, pattern):
        """Line numbers inside the bodies of methods whose signature matches pattern."""
        inside = set()
        for number, line in enumerate(self.lines):
            if not pattern.search(comment_free(line)):
                continue
            depth = None
            for index in range(number, len(self.lines)):
                code = comment_free(self.lines[index])
                for char in code:
                    if char == "{":
                        depth = (depth or 0) + 1
                    elif char == "}" and depth is not None:
                        depth -= 1
                if depth is not None:
                    inside.add(index)
                    if depth == 0:
                        break
        return inside


def check_style(src, text, rel, name, ctx, new_lines, is_write, findings):
    for number, line in enumerate(src.lines):
        if line.strip() not in new_lines:
            continue
        code = strip_strings(line)
        index = code.find("//")
        if (index >= 0 and not code[index:].startswith("///")) or "/*" in code:
            if ctx.enabled("style.inline-comment"):
                findings.add("style.inline-comment",
                             f"{name}:{number + 1} has an inline comment. Use XML <summary> on public types and "
                             "non-obvious members instead, or make the code say it.")
        if number not in src.type_body_lines:
            continue
        attrs = src.attributes_before(number)
        field = FIELD.match(comment_free(line))
        if field and field.group("type") not in NON_KEYWORD_TYPES and not field.group("event"):
            mods = field.group("mods").split()
            attrs += " " + field.group("attrs")
            serialized = "SerializeField" in attrs
            is_constant = "const" in mods or ("static" in mods and "readonly" in mods)
            is_private = not ({"public", "protected", "internal"} & set(mods))
            if is_private and not is_constant and not PRIVATE_FIELD_NAME.match(field.group("name")):
                if ctx.enabled("style.field-naming"):
                    findings.add("style.field-naming",
                                 f"{name}:{number + 1} private field '{field.group('name')}' should be _camelCase.")
            if serialized and "Tooltip" not in attrs and ctx.enabled("style.tooltip"):
                findings.add("style.tooltip",
                             f"{name}:{number + 1} serialized field '{field.group('name')}' has no [Tooltip].")
            continue
        prop = AUTO_PROPERTY.match(comment_free(line))
        if prop:
            attrs += " " + prop.group("attrs")
            if "SerializeField" in attrs and "Tooltip" not in attrs and ctx.enabled("style.tooltip"):
                findings.add("style.tooltip",
                             f"{name}:{number + 1} [field: SerializeField] property has no [field: Tooltip].")

    if not (is_write or "namespace" in "".join(new_lines) or "class " in "".join(new_lines)):
        return
    namespaces = NAMESPACE.findall(text)
    root = gc.namespace_root(ctx.unity_root, ctx.config)
    feature = PROJECT_FEATURE.search(rel)
    if ctx.enabled("style.namespace"):
        if not namespaces and (TYPE_DECLARATION.search(text)):
            expected = f"{root}.{feature.group(1)}" if feature and root else f"{root}.<Feature>"
            findings.add("style.namespace", f"{name} declares types outside a namespace. Use {expected}.")
        elif namespaces and feature and root:
            expected = f"{root}.{feature.group(1)}"
            wrong = [ns for ns in namespaces if not (ns == expected or ns.startswith(expected + "."))]
            if wrong:
                findings.add("style.namespace",
                             f"{name} uses namespace {wrong[0]}; files in Assets/_Project/{feature.group(1)}/ use "
                             f"{expected}.")
    unity_types = UNITY_OBJECT_TYPE.findall(comment_free_text(text))
    if len(unity_types) > 1 and ctx.enabled("style.one-type-per-file"):
        findings.add("style.one-type-per-file",
                     f"{name} declares {len(unity_types)} MonoBehaviour/ScriptableObject types "
                     f"({', '.join(t for t, _ in unity_types)}). Put each in its own file named after the class.")
    stem = os.path.splitext(name)[0]
    if len(unity_types) == 1 and unity_types[0][0] != stem and ctx.enabled("style.file-name"):
        findings.add("style.file-name",
                     f"{name} holds {unity_types[0][0]}. Unity needs the file named {unity_types[0][0]}.cs, or "
                     "the component can't be added and serialized references break.")


def comment_free_text(text):
    return "\n".join(comment_free(line) for line in text.splitlines())


def check_perf(src, name, ctx, new_lines, findings):
    for number in sorted(src.method_body_lines(UPDATE_METHODS)):
        line = src.lines[number]
        if line.strip() not in new_lines:
            continue
        for rule_id, pattern, advice in PERF_RULES:
            target = strip_comment(line) if rule_id == "perf.update-string" else comment_free(line)
            if pattern.search(target) and ctx.enabled(rule_id):
                findings.add(rule_id, f"{name}:{number + 1} {advice}")


def strip_comment(line):
    """The line with its // comment removed but string literals kept."""
    in_string = False
    previous = ""
    for index, char in enumerate(line):
        if char == '"' and previous != "\\":
            in_string = not in_string
        if not in_string and line.startswith("//", index):
            return line[:index]
        previous = char
    return line


def check_tech(src, text, name, ctx, new_lines, findings):
    for number, line in enumerate(src.lines):
        if line.strip() not in new_lines:
            continue
        code = comment_free(line)
        for rule_id, pattern, advice in TECH_LINE_RULES:
            if pattern.search(code) and ctx.enabled(rule_id):
                findings.add(rule_id, f"{name}:{number + 1} {advice}")
    joined = "".join(new_lines)
    if (
        ctx.enabled("tech.renderer-feature")
        and any(token in joined for token in ("ScriptableRenderPass", "Execute", "CommandBuffer"))
        and "ScriptableRenderPass" in text
        and re.search(r"\bvoid\s+Execute\s*\(\s*ScriptableRenderContext|CommandBufferPool\.Get", text)
        and "RecordRenderGraph" not in text
    ):
        findings.add("tech.renderer-feature",
                     f"{name} renders through Execute/CommandBuffer. Custom rendering goes through a "
                     "ScriptableRendererFeature with the Render Graph API (override RecordRenderGraph).")


def check_statics(src, text, rel, name, ctx, new_lines, is_write, findings):
    if "/Editor/" in "/" + rel or not ctx.enabled("statics.reset"):
        return
    if not (is_write or any("static" in line for line in new_lines)):
        return
    if "SubsystemRegistration" in text:
        return
    mutable = []
    for number in sorted(src.type_body_lines):
        code = comment_free(src.lines[number])
        field = FIELD.match(code)
        if not field:
            continue
        mods = field.group("mods").split()
        if "static" in mods and "readonly" not in mods and "const" not in mods:
            mutable.append(field.group("name"))
    if mutable:
        findings.add("statics.reset",
                     f"{name} has mutable statics ({', '.join(mutable[:5])}) but no reset. Domain reload is off, so "
                     "they keep values between Play sessions: reset them in a "
                     "[RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.SubsystemRegistration)] method.")


def main():
    event = gc.read_event()
    if not event or event.get("tool_name") not in EDIT_TOOLS:
        return
    tool_input = event.get("tool_input") or {}
    path = tool_input.get("file_path") or ""
    ctx = gc.Context(path, event.get("cwd"))
    if not ctx.in_unity or gc.is_skipped_path(path):
        return
    rel = gc.normalize(os.path.relpath(os.path.abspath(path), ctx.unity_root))
    name = os.path.basename(path)
    extension = os.path.splitext(path)[1].lower()
    is_write = event["tool_name"] == "Write"
    findings = gc.Findings()

    if extension in YAML_EXTENSIONS and ctx.enabled("yaml.hand-edit"):
        findings.add("yaml.hand-edit",
                     f"{name} is serialized Unity YAML edited by hand. Prefer letting the Editor change it (a CLI "
                     "command, an editor script, or the Inspector); check it still loads without errors.")
    if extension == ".shader" and is_write and UBER_SHADER_NAME not in name and ctx.enabled("tech.new-shader"):
        findings.add("tech.new-shader",
                     f"{name} is a new shader. Opaque surfaces extend the one SRP Batcher compatible "
                     f"{UBER_SHADER_NAME} shader; transparent effects use Shader Graph.")

    if extension == ".cs":
        try:
            with open(path, encoding="utf-8-sig", errors="replace") as handle:
                text = handle.read()
        except OSError:
            text = "\n".join(new_texts(tool_input))
        new_lines = {line.strip() for t in new_texts(tool_input) for line in t.splitlines() if line.strip()}
        src = Source(text)
        check_style(src, text, rel, name, ctx, new_lines, is_write, findings)
        check_perf(src, name, ctx, new_lines, findings)
        check_tech(src, text, name, ctx, new_lines, findings)
        check_statics(src, text, rel, name, ctx, new_lines, is_write, findings)

    if findings:
        gc.warn(findings)


if __name__ == "__main__":
    main()
