# bradens-unity-skills

A Claude Code plugin with Unity skills and rule hooks. Forked from Quin Henshaw's
[quins-unity-skills](https://github.com/qhenshaw/quins-unity-skills) 0.7.0; the skills are Quin's work, the rule hooks
are new.

## Skills

| Skill | What it does |
|---|---|
| `bradens-unity-skills:unity-vfx-from-texture-pack` | Builds gameplay VFX (hits, deaths, explosions, slashes, trails...) as VFX Graph assets generated from code, from a texture / flipbook pack. Generator, runtime `EffectsManager`, PlayMode test, pack inventory scripts. |
| `bradens-unity-skills:unity-playmode-input-tests` | PlayMode tests that drive the game through real Input System devices and UI Toolkit mouse events. Base class, examples, asmdef, and a CLI runner that can't report a stale run as green. |
| `bradens-unity-skills:unity-asset-pack-extraction` | Pulls only the assets you use out of large `.unitypackage` packs with GUIDs preserved, then converts materials to your own shader. |
| `bradens-unity-skills:unity-model-icon-renderer` | Renders prefabs into transparent, outlined, auto-posed sprite icons sized to an item's cell footprint. |
| `bradens-unity-skills:unity-editor-cli-recovery` | Keeps a CLI-driven Editor responsive: clicks blocking dialogs, retries transient failures, refreshes before recompiling, captures the game view. |
| `bradens-unity-skills:unity-debug-menu-cli` | In-game UI Toolkit debug menu where each feature registers its own controls, mirrored as `unity command debugmenu` CLI commands. |
| `bradens-unity-skills:unity-steam-deck-deploy` | Builds a Windows player for the Steam Deck under Proton, smoke-tests it and deploys it to a dev kit over SSH. |
| `bradens-unity-skills:clarify` | On an explicit `/clarify`, grills you through one-click multiple-choice questions until the task is fully specified. |

## Hooks

Skills teach Claude how to do something and load only when a task needs them. Hooks run on every matching tool call
and block it when a rule a script can check is broken. Keep judgment rules in CLAUDE.md; put a rule here only when
breaking it is costly and a regex or git query can decide it.

| Hook | Runs on | Blocks | Off switch |
|---|---|---|---|
| Shell guard (`shell-guard.sh`) | Bash, Git Bash on Windows only | Heredocs, a bare `python -`, multi-line `python -c` | `BRADENS_SHELL_GUARD=off` |
| Dash guard (`edit_guard.py`) | Write, Edit, MultiEdit | Em or en dashes in the text being written (old text is not checked, so existing dashes can be removed). Skips `ThirdParty/`, `Library/` and `PackageCache/` paths | `BRADENS_DASH_GUARD=off` |
| Unity API guard (`edit_guard.py`) | Write, Edit, MultiEdit on `.cs` | Legacy `UnityEngine.Input` calls and `MaterialPropertyBlock` / `SetPropertyBlock` outside comments | `BRADENS_UNITY_API_GUARD=off` |
| Unity CLI guard (`command_guard.py`) | Bash, PowerShell | `unity command` without `--project-path` | `BRADENS_UNITY_CLI_GUARD=off` |
| Commit guard (`command_guard.py`) | Bash, PowerShell on `git commit` | Em or en dashes in the command, staged files from a Unity project's `Library/`, `Temp/`, `Logs/`, `UserSettings/` or `obj/`, and staged files over 10 MB (LFS pointers pass) | `BRADENS_COMMIT_GUARD=off` |

`BRADENS_GUARDS=off` turns them all off. The Python hooks need Python 3.8+ (`python3`, `python` or `py -3`); with no
Python they allow everything instead of failing. Each launch takes about 0.25 s.

Limits of the commit guard: it reads the index when the command starts. `git add -A`, `git add .` and `git commit -a`
in the same command are followed (files checked on disk); `git add <some files> && git commit` is not, and a message
passed with `-F <file>` is not read. A git pre-commit hook in the project would also catch human commits.

Test the hooks after changing them:

```
python tests/test_hooks.py
```

## Install

Locally:

```
/plugin marketplace add C:/Repos/bradens-unity-skills
/plugin install bradens-unity-skills@bradens-unity-skills
```

Uninstall `quins-unity-skills` first, or every skill shows up twice under two prefixes.

## Layout

```
.claude-plugin/plugin.json        plugin manifest (bump "version" when publishing changes)
.claude-plugin/marketplace.json   lets this repo act as its own marketplace (bump its "version" too)
skills/<skill-name>/SKILL.md      one folder per skill (+ templates/, scripts/, references/)
hooks/hooks.json                  hook registrations; the scripts sit next to it
tests/test_hooks.py               sample tool calls for every hook rule
evals/                            skill trigger evals
```

Add a skill by creating `skills/<new-skill>/SKILL.md` with `name` and `description` frontmatter, and copy a `trigger-*`
folder in `evals/` for it.

## Evals

`evals/` checks that each skill is picked up from a realistic request that doesn't name it, and that none load for an
unrelated task:

```
claude plugin eval . --ablation none --no-publish -j 4
```

Results go to `evals/results/` (git-ignored).

## Notes

- No licensed art is included.
- The VFX scripts need Python 3 with Pillow and numpy; the asset pack and readout scripts need Python 3. The Steam Deck
  scripts need bash, ssh and tar and a Deck paired with the SteamOS Devkit Client.
- The upstream repo has no license file. Ask Quin before publishing this fork publicly.
