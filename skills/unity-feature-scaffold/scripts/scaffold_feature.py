"""Create a feature folder in a Unity project: Assets/_Project/<Feature>/{Scripts,Prefabs,Data,UI,Tests}.

usage:
  python scaffold_feature.py <project folder> <Feature> [--references A,B] [--no-tests] [--editor]

- Scripts/<Root>.<Feature>.asmdef with rootNamespace <Root>.<Feature> and the given assembly references.
- Tests/<Root>.<Feature>.Tests.asmdef (PlayMode, NUnit, Input System) unless --no-tests.
- Editor/<Root>.<Feature>.Editor.asmdef (Editor platform only) with --editor.
<Root> is namespaceRoot from .claude/bradens-unity.json, else the project folder name.

It refuses to touch a feature folder that already exists, and writes no .meta files: refresh the Editor
afterwards so Unity imports the folders and assigns GUIDs.
"""

import argparse
import json
import os
import re
import sys

PROJECT_FOLDER = os.path.join("Assets", "_Project")
CONFIG_PATH = os.path.join(".claude", "bradens-unity.json")
FOLDERS = ("Scripts", "Prefabs", "Data", "UI", "Tests")
FEATURE_NAME = re.compile(r"^[A-Z][A-Za-z0-9]*$")
TEST_REFERENCES = ["Unity.InputSystem", "UnityEngine.TestRunner", "UnityEditor.TestRunner"]
EDITOR_PLATFORM = "Editor"


def namespace_root(project):
    try:
        with open(os.path.join(project, CONFIG_PATH), encoding="utf-8") as handle:
            configured = json.load(handle).get("namespaceRoot")
    except (OSError, json.JSONDecodeError, AttributeError):
        configured = None
    if configured:
        return configured
    name = re.sub(r"[^A-Za-z0-9_]", "", os.path.basename(os.path.normpath(project)))
    return "_" + name if name[:1].isdigit() else name


def asmdef(name, references, include_platforms=None, tests=False):
    data = {
        "name": name,
        "rootNamespace": name,
        "references": references,
        "includePlatforms": include_platforms or [],
        "excludePlatforms": [],
        "allowUnsafeCode": False,
        "overrideReferences": tests,
        "precompiledReferences": ["nunit.framework.dll"] if tests else [],
        "autoReferenced": not tests and not include_platforms,
        "defineConstraints": ["UNITY_INCLUDE_TESTS"] if tests else [],
        "versionDefines": [],
        "noEngineReferences": False,
    }
    return json.dumps(data, indent=4) + "\n"


def write(path, text):
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)
    print("created", path)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("project")
    parser.add_argument("feature")
    parser.add_argument("--references", default="", help="comma-separated assembly names for the runtime asmdef")
    parser.add_argument("--no-tests", action="store_true")
    parser.add_argument("--editor", action="store_true")
    args = parser.parse_args()

    project = os.path.abspath(args.project)
    if not os.path.isfile(os.path.join(project, "ProjectSettings", "ProjectVersion.txt")):
        sys.exit(f"{project} is not a Unity project (no ProjectSettings/ProjectVersion.txt).")
    if not FEATURE_NAME.match(args.feature):
        sys.exit(f"Feature name '{args.feature}' must be PascalCase letters and digits.")
    feature_dir = os.path.join(project, PROJECT_FOLDER, args.feature)
    if os.path.exists(feature_dir):
        sys.exit(f"{feature_dir} already exists; not touching it.")

    root = namespace_root(project)
    runtime = f"{root}.{args.feature}"
    references = [r.strip() for r in args.references.split(",") if r.strip()]

    for folder in FOLDERS if not args.no_tests else [f for f in FOLDERS if f != "Tests"]:
        os.makedirs(os.path.join(feature_dir, folder))
    write(os.path.join(feature_dir, "Scripts", f"{runtime}.asmdef"), asmdef(runtime, references))
    if not args.no_tests:
        write(os.path.join(feature_dir, "Tests", f"{runtime}.Tests.asmdef"),
              asmdef(f"{runtime}.Tests", [runtime, *TEST_REFERENCES], tests=True))
    if args.editor:
        os.makedirs(os.path.join(feature_dir, "Editor"))
        write(os.path.join(feature_dir, "Editor", f"{runtime}.Editor.asmdef"),
              asmdef(f"{runtime}.Editor", [runtime], include_platforms=[EDITOR_PLATFORM]))
    print(f"Namespace: {runtime}. Refresh the Editor so it imports the new folders and writes their .meta files.")


if __name__ == "__main__":
    main()
