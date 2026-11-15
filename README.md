# bradens-unity-skills

A Claude Code plugin with Unity skills and rule hooks. Forked from Quin Henshaw's
[quins-unity-skills](https://github.com/qhenshaw/quins-unity-skills) 0.7.0; the first eight skills are Quin's work.
The rule hooks and the last four skills turn a Unity project's CLAUDE.md rules into checks and know-how, so a project's
CLAUDE.md can stay short.

## Skills

| Skill | What it does |
|---|---|
| `bradens-unity-skills:unity-git-setup` | UnityYAMLMerge merge driver (per clone), Git LFS by extension, the Unity .gitignore, feature branches and per-feature scenes, and what to do on merge conflicts. Check/apply script and `.gitattributes` / `.gitignore` templates. |
| `bradens-unity-skills:unity-feature-scaffold` | `Assets/_Project/<Feature>/{Scripts,Prefabs,Data,UI,Tests}` with asmdefs and the `<Root>.<Feature>` namespace, plus the C# house style and Unity rules. Scaffold script and component / settings templates. |
| `bradens-unity-skills:unity-uber-shader` | The one SRP Batcher compatible opaque shader (UberLit): template, how to add a feature (property, UnityPerMaterial CBUFFER, `shader_feature_local` in each pass), and instanced materials for per-object effects. |
| `bradens-unity-skills:unity-verify-change` | When a Unity change is done: PlayMode tests plus a new one, real-device input, debug menu CLI for state, exit Play mode, manual-check list; Editor dialog policy, human-safe generators, notifications. |
| `bradens-unity-skills:unity-vfx-from-texture-pack` | Builds gameplay VFX (hits, deaths, explosions, slashes, trails...) as VFX Graph assets generated from code, from a texture / flipbook pack. Generator, runtime `EffectsManager`, PlayMode test, pack inventory scripts. |
| `bradens-unity-skills:unity-playmode-input-tests` | PlayMode tests that drive the game through real Input System devices and UI Toolkit mouse events. Base class, examples, asmdef, and a CLI runner that can't report a stale run as green. |
| `bradens-unity-skills:unity-asset-pack-extraction` | Pulls only the assets you use out of large `.unitypackage` packs with GUIDs preserved, then converts materials to your own shader. |
| `bradens-unity-skills:unity-model-icon-renderer` | Renders prefabs into transparent, outlined, auto-posed sprite icons sized to an item's cell footprint. |
| `bradens-unity-skills:unity-editor-cli-recovery` | Keeps a CLI-driven Editor responsive: clicks blocking dialogs, retries transient failures, refreshes before recompiling, captures the game view. |
| `bradens-unity-skills:unity-debug-menu-cli` | In-game UI Toolkit debug menu where each feature registers its own controls, mirrored as `unity command debugmenu` CLI commands. |
| `bradens-unity-skills:unity-steam-deck-deploy` | Builds a Windows player for the Steam Deck under Proton, smoke-tests it and deploys it to a dev kit over SSH. |
| `bradens-unity-skills:clarify` | On an explicit `/clarify`, grills you through one-click multiple-choice questions until the task is fully specified. |

## Hooks

Skills teach Claude how to do something and load only when a task needs them. Hooks run on every matching tool call.
Clear-cut rules **block** the call before it runs; fuzzy rules **warn** after an edit (the edit stands and Claude gets
the issues to fix), so a false positive never stalls work. Keep judgment rules in CLAUDE.md; a rule belongs here only
when a regex or a git query can decide it.

Rules only run inside a Unity project (the nearest folder above with `ProjectSettings/ProjectVersion.txt`), except
`dash.text`, `commit.dash`, `commit.size` and the shell guard, which run everywhere.

| Rule id | Runs on | Outcome | Checks |
|---|---|---|---|
| shell guard | Bash (Git Bash on Windows) | block | Heredocs, a bare `python -`, multi-line `python -c` |
| `dash.text` | Write, Edit | block | Em or en dashes in the text being written (old text isn't checked, so dashes can be removed) |
| `unity-api.legacy-input` | Write, Edit `.cs` | block | `UnityEngine.Input` calls |
| `unity-api.property-block` | Write, Edit `.cs` | block | `MaterialPropertyBlock` / `SetPropertyBlock` outside comments |
| `assets.third-party` | Write, Edit, rm, mv | block | Changing, moving or deleting anything under `Assets/ThirdParty/` |
| `assets.meta-guid` | Write, Edit `.meta` | block | Changing or removing a `.meta` file's guid |
| `assets.shell-meta` | rm, mv, git rm, git mv, Remove-Item, Move-Item | block | Moving or deleting an `Assets/` path without its `.meta` |
| `git.gitattributes` | Write, Edit | block | Changing a committed `.gitattributes`; Claude must ask you in chat first. (It blocks rather than asks: permission modes that auto-approve let an "ask" hook through without a prompt.) |
| `unity-cli.project-path` | Bash, PowerShell | block | `unity command` without `--project-path` (or not the configured `projectPath`) |
| `unity-cli.caller` | Bash, PowerShell | block | `unity command` without `--caller` and `--skill` |
| `commit.dash` | `git commit` | block | Em or en dashes in the commit command |
| `commit.size` | `git commit` | block | Staged files over 10 MB (LFS pointers pass) |
| `commit.cache-folders` | `git commit` | block | Staged files from `Library/`, `Temp/`, `Logs/`, `UserSettings/`, `obj/` |
| `commit.meta-pairing` | `git commit` | block | An asset or new folder staged without its `.meta`, or a `.meta` without its asset |
| `commit.editor-path` | `git commit` | block | An absolute Unity Editor path (UnityYAMLMerge, `Hub/Editor/`) in staged changes |
| `commit.lfs-binary` | `git commit` | block | Textures, models, audio, video or fonts not routed to Git LFS |
| `style.field-naming` | Write, Edit `.cs` | warn | Private fields not `_camelCase` (constants exempt) |
| `style.inline-comment` | Write, Edit `.cs` | warn | `//` or `/* */` comments (XML `///` is fine) |
| `style.tooltip` | Write, Edit `.cs` | warn | `[SerializeField]` / `[field: SerializeField]` without `[Tooltip]` |
| `style.namespace` | Write, Edit `.cs` | warn | Missing namespace, or not `<Root>.<Feature>` under `Assets/_Project/<Feature>/` |
| `style.one-type-per-file` | Write, Edit `.cs` | warn | More than one MonoBehaviour / ScriptableObject in a file |
| `style.file-name` | Write, Edit `.cs` | warn | A MonoBehaviour / ScriptableObject in a file not named after it |
| `perf.update-*` | Write, Edit `.cs` | warn | Find, GetComponent, collection allocations, LINQ, string building or Instantiate inside Update, FixedUpdate, LateUpdate |
| `tech.ugui` | Write, Edit `.cs` | warn | `using UnityEngine.UI`, Canvas, `OnGUI`, GUILayout (use UI Toolkit) |
| `tech.particle-system` | Write, Edit `.cs` | warn | `ParticleSystem` (use VFX Graph) |
| `tech.renderer-feature` | Write, Edit `.cs` | warn | Render passes using Execute / CommandBufferPool without `RecordRenderGraph` |
| `tech.new-shader` | Write `.shader` | warn | A new shader other than UberLit |
| `statics.reset` | Write, Edit `.cs` | warn | Mutable statics without a `SubsystemRegistration` reset (outside `Editor/`) |
| `yaml.hand-edit` | Write, Edit | warn | Hand edits to `.unity`, `.prefab`, `.asset`, `.mat` and other serialized assets |
| `unity-cli.script-eval` | Bash, PowerShell | warn | `unity command script eval` (prefer a custom command or a Tools/ script) |
| `git.main-branch` | `git commit` | warn | A commit that landed on main or master |
| `session.yaml-merge`, `session.lfs` | session start | report | UnityYAMLMerge driver and LFS setup (read only) |
| `session.verify-reminder` | stop | message | C# changed: run PlayMode tests, exit Play mode. Once per set of changes |

Line rules (naming, comments, tooltips, per-frame code, tech) only report lines the edit wrote, so old code doesn't nag
on every edit. Paths under `ThirdParty/`, `Library/` and `PackageCache/` are skipped.

### Turning rules off

- One rule or a whole group for a project: list ids or groups in `.claude/bradens-unity.json` at the Unity project
  root, for example `{"disabledRules": ["style.inline-comment", "perf"]}`.
- A group for a session: `BRADENS_<GROUP>_GUARD=off`, for example `BRADENS_STYLE_GUARD=off`, `BRADENS_ASSETS_GUARD=off`.
- Everything: `BRADENS_GUARDS=off`.

### Project config

`.claude/bradens-unity.json` is optional:

```json
{
  "namespaceRoot": "MyGame",
  "projectPath": "C:/Repos/MyGame",
  "disabledRules": []
}
```

Without it, `namespaceRoot` is the project folder name and `projectPath` isn't compared.

### Limits

- The Python hooks need Python 3.8+ (`python3`, `python` or `py -3`); with no Python they allow everything. Each
  launch takes about 0.25 s.
- The commit rules read the index when the command starts. `git add -A`, `git add .` and `git commit -a` in the same
  command are followed; `git add <some files> && git commit` is not, and a message passed with `-F <file>` isn't
  read. A git pre-commit hook in the project would also catch human commits.
- The C# checks are regex based, not a compiler: they can miss things and occasionally warn on fine code, which is why
  they warn instead of block.

Test the hooks after changing them:

```
python tests/test_hooks.py
```

## Install

From GitHub:

```
/plugin marketplace add BradenBanning/bradens-unity-skills
/plugin install bradens-unity-skills@bradens-unity-skills
```

To try local changes before pushing:

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
- Quin's debug menu templates predate the new style rules (inline comments, non-underscore fields), so code copied from
  them gets style warnings until it's tidied.
- The VFX scripts need Python 3 with Pillow and numpy; the asset pack and readout scripts need Python 3. The Steam Deck
  scripts need bash, ssh and tar and a Deck paired with the SteamOS Devkit Client.
- The upstream repo has no license file. Ask Quin before publishing this fork publicly.
