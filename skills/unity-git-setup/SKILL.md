---
name: unity-git-setup
description: Set up and check git for a Unity project worked on by several people - UnityYAMLMerge as the merge driver for scenes, prefabs and assets, Git LFS by file extension, the Unity .gitignore, short-lived feature branches and per-feature scenes and prefabs, plus what to do when a merge still conflicts. Use when a Unity project is put under git or cloned on a new machine, when the session check reports UnityYAMLMerge or LFS missing, before adding textures, models, audio or video, when a scene or prefab merge conflicts, or when planning how several contributors share scenes.
---

# Unity git setup for several contributors

Unity scenes, prefabs and assets are YAML that a plain text merge corrupts, binaries bloat history, and the
Editor's caches must never be committed. Three pieces fix that: UnityYAMLMerge as the merge driver, Git LFS by
extension, and a .gitignore for the Editor's folders. The first is per clone (local git config); the other two are
committed and shared.

The plugin's hooks back this up: the session check reports a missing driver or LFS setup, and the commit guard
blocks cache folders, files over 10 MB, binaries outside LFS, assets without .meta files, and Editor paths in
committed files.

## 1. Check what is set up

```
python <skill>/scripts/unity_git_setup.py check <project folder>
```

It prints one line per item: merge driver configured and pointing at a file that exists, `.unity` files routed to
`merge=unityyamlmerge`, Git LFS installed, extensions routed to LFS, and the Unity folders ignored. It changes
nothing. Exit code 0 means all good.

## 2. Merge driver (local config, every clone)

```
python <skill>/scripts/unity_git_setup.py apply <project folder>
```

It reads the Editor version from `ProjectSettings/ProjectVersion.txt`, finds that Editor through Unity Hub's
install folders (Windows `C:\Program Files\Unity\Hub\Editor\<version>\Editor\Data\Tools\UnityYAMLMerge.exe` and the
Hub secondary install path, macOS `/Applications/Unity/Hub/Editor/<version>/Unity.app/Contents/Tools/UnityYAMLMerge`,
Linux `~/Unity/Hub/Editor/<version>/Editor/Data/Tools/UnityYAMLMerge`) and sets, in this clone only:

```
git config merge.unityyamlmerge.name "Unity SmartMerge"
git config merge.unityyamlmerge.driver "'<path>' merge -h -p --force %O %B %A %A"
git config merge.unityyamlmerge.recursive binary
```

- Never put that path in a committed file; the commit guard blocks it.
- If the matching Editor isn't installed, the script says so and stops. Tell the user which version is missing;
  never guess a path or point at a different Editor version.

## 3. Committed files

Ask the user in chat before changing a committed `.gitattributes`, showing the exact change (the edit hook blocks
Write and Edit on it). For a new project, start
from the templates:

- `templates/unity.gitattributes`: `merge=unityyamlmerge eol=lf` for `*.unity *.prefab *.asset *.mat *.anim
  *.controller *.overrideController *.physicMaterial *.playable *.mask *.mixer *.spriteatlas *.terrainlayer
  *.renderTexture *.preset`, and `filter=lfs diff=lfs merge=lfs -text` for textures, models, audio, video and fonts.
  Copy it to the repository root as `.gitattributes`.
- `templates/unity.gitignore`: Library/, Temp/, Logs/, UserSettings/, obj/, Build(s)/, IDE files. Copy it as
  `.gitignore`.

Set up LFS before the first binary is added: `git lfs install` (once per machine), commit `.gitattributes`, then add
the binaries. A binary committed before that sits in history as a full blob; `git lfs migrate import
--include="*.png"` rewrites history, so ask the user first if the branch is shared.

## 4. Working together

- Short-lived feature branches off main (`feature/<name>`); merge main in before finishing, then merge back.
- Split scenes and prefabs per feature (a feature's own scene or additive sub-scene, nested prefabs) so two people
  rarely edit the same file. Put shared tuning in ScriptableObject assets rather than in a scene.
- Commit every `.meta` with its asset, and move, rename or delete them together (better: in the Editor).
- Check every commit for files over 10 MB.

## 5. When a merge still conflicts

If UnityYAMLMerge leaves conflicts in a scene, prefab or asset: stop and ask the user. Don't hand-merge the YAML
(fileIDs and references break silently). Options to offer: take one side (`git checkout --ours/--theirs <file>`)
and redo the other side's change in the Editor, or have the person who owns that file resolve it.
