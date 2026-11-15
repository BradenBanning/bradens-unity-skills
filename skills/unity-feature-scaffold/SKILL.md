---
name: unity-feature-scaffold
description: Start a new gameplay feature in a Unity project the conventional way - Assets/_Project/<Feature>/{Scripts,Prefabs,Data,UI,Tests} with its own asmdef, the <Root>.<Feature> namespace, a ScriptableObject for tuning, editable prefabs, and a row in the project's CLAUDE.md layout table - and write its C# to the house style and Unity rules. Use when adding a new feature, system, mechanic or tool folder to a Unity project, when creating the first scripts of a feature, or when asked how a new feature should be laid out or written.
---

# Scaffold a Unity feature

Every feature lives in its own folder with its own assembly, so features compile separately, two people rarely touch
the same files, and the rules below are easy to check.

```
Assets/_Project/<Feature>/
  Scripts/   <Root>.<Feature>.asmdef, runtime C#
  Prefabs/   editable prefabs (nested, variants) - the feature's scene content
  Data/      ScriptableObject assets holding all tuning
  UI/        UXML, USS, PanelSettings (UI Toolkit)
  Tests/     <Root>.<Feature>.Tests.asmdef, PlayMode tests
  Editor/    optional: <Root>.<Feature>.Editor.asmdef, UI Toolkit editor tools
  CLAUDE.md  optional, for larger features; list it in the root CLAUDE.md
```

`<Root>` is `namespaceRoot` from `.claude/bradens-unity.json`, else the project folder name. The plugin's lint uses
the same rule, so a file in `Assets/_Project/Gym/` must use namespace `<Root>.Gym`.

## Steps

1. Pick a PascalCase feature name and the assemblies it needs (other features, `Unity.InputSystem`,
   `Unity.VisualEffectGraph.Runtime`, `Unity.Cinemachine`...).
2. Create the folders and asmdefs:
   ```
   python <skill>/scripts/scaffold_feature.py <project> <Feature> --references Unity.InputSystem,<Root>.Player [--editor]
   ```
   It refuses an existing folder and writes no .meta files. Refresh the Editor afterwards
   (`unity command ... refresh` or focus the Editor) so Unity imports the folders and assigns GUIDs, then commit the
   .meta files with the assets.
3. Put tuning in a ScriptableObject (`templates/FeatureSettings.cs`) and create its asset in `Data/`. Components
   reference the asset (`templates/FeatureComponent.cs`).
4. Build scene content as prefabs in `Prefabs/` and keep the feature's objects out of shared scenes where possible
   (its own scene or additive sub-scene).
5. Add a debug menu section for the feature's state and actions (unity-debug-menu-cli skill), and a PlayMode test in
   `Tests/` (unity-playmode-input-tests skill).
6. Add the feature's row to the layout table in the project's CLAUDE.md.

## C# house style

- Standard C# conventions; private fields `_camelCase`; namespace `<Root>.<Feature>`.
- One MonoBehaviour or ScriptableObject per file, file named after the class.
- Tunables: `[SerializeField]` or `[field: SerializeField]` plus `[Tooltip]`.
- No magic strings or numbers: named constants, serialized fields or ScriptableObjects.
- No inline comments; XML `<summary>` on public types and non-obvious members.
- No em or en dashes anywhere (code, docs, UI text, commit messages).
- Plain, readable code over clever patterns.

## Unity rules

- Input only through the Input System, via the project's single input wrapper class. Never `UnityEngine.Input`.
- UI Toolkit for all UI, HUD and editor tools (no uGUI Canvas, no IMGUI `OnGUI`).
- VFX Graph for particles; Shader Graph for transparent effects; opaque surfaces extend the one UberLit shader
  (unity-uber-shader skill).
- Per-object material effects use instanced materials (`renderer.material`, destroyed in `OnDestroy`), never
  MaterialPropertyBlocks.
- Custom rendering is a ScriptableRendererFeature using the Render Graph API.
- Pool anything spawned per frame (`UnityEngine.Pool`). No Find*, GetComponent or allocations in Update.
- With domain reload off, reset every mutable static and static event in a
  `[RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.SubsystemRegistration)]` method.
- Humans maintain the project: make editable prefabs, scenes and ScriptableObject data. Builders and generators never
  overwrite human edits; generators write only derived output into folders marked as generated, and skip assets
  that already exist.

The plugin's hooks check most of these as you write: hard rules block the edit, style and performance rules come back
as warnings to fix.
