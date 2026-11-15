# Changelog

Newest first. Bump `version` in both `.claude-plugin/plugin.json` and `.claude-plugin/marketplace.json` for every release, or installed copies won't update.

## 0.2.3 (2026-11-15, `41e3053`)

- **unity-playmode-input-tests:** `Press` and `Release` in the `InputTestBase` template take several buttons and write them into one event per device, so a chord is one call: `Press(Keyboard.leftShiftKey, Keyboard.dKey)`. Two separate events for the same device in one frame undo each other, because each one is built from the device's current state. The gamepad example now waits a frame between centring the stick and tapping a button. A Shift+D example was added, and the skill lists the gotcha. Checked with a probe in a Unity 6.6 Editor.

## 0.2.2 (2026-11-15, `490ff2d`)

- **Hooks:** decide which project's rules apply from the file or repository a call targets. The session's starting folder is only used when a call names no path. Before, a commit in a non-Unity repository made from a Unity session got a false `git.main-branch` warning, and C# outside a Unity project could be checked against Unity rules.

## 0.2.1 (2026-11-15, `6a2f256`)

- **Hooks:** `git.gitattributes` blocks Write and Edit on a committed `.gitattributes` instead of asking. Permission modes that auto-approve let an "ask" hook through without a prompt. Claude is told to show the change and ask in chat first. The plugin no longer uses "ask".

## 0.2.0 (2026-11-15, `dfb7a2f`)

- **Hooks:** rules from a Unity project's CLAUDE.md, each with an id that can be switched off in `.claude/bradens-unity.json` or by environment variable.
  - Block: ThirdParty edits, `.meta` guid changes, moving or deleting assets without their `.meta`, `unity command` without `--caller --skill`, commits with unpaired `.meta` files, Editor paths or binaries outside LFS.
  - Warn after edits: C# style, per-frame Find, GetComponent and allocations, uGUI and IMGUI, ParticleSystem, render passes without Render Graph, new shaders, unreset statics, hand-edited YAML, script eval, commits on main.
  - Session start reports the UnityYAMLMerge and LFS setup; stop reminds to run tests when C# changed.
  - Unity rules only run inside Unity projects.
- **Skills:** `unity-git-setup`, `unity-feature-scaffold`, `unity-uber-shader`, `unity-verify-change`, each with a trigger eval.
- **Tests:** `tests/test_hooks.py` grew to 107 cases.

## 0.1.0 (2026-11-14, `330faf0`)

- Forked from Quin Henshaw's [quins-unity-skills](https://github.com/qhenshaw/quins-unity-skills) 0.7.0 (8 skills, Git Bash shell guard, trigger evals). Em and en dashes removed from the skill docs.
- **Hooks:** dash guard on Write and Edit; Unity API guard (legacy `UnityEngine.Input`, `MaterialPropertyBlock`); `--project-path` on `unity command`; commit guard (Unity cache folders, files over 10 MB, dashes in commit messages).
- **Tests:** `tests/test_hooks.py`.
