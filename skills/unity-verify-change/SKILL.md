---
name: unity-verify-change
description: Decide when a Unity change is actually done and prove it - a clean compile is not done - by running the PlayMode tests and adding one for the change, driving input through real devices, setting up and reading game state through the debug menu CLI, exiting Play mode afterwards, and listing what still needs a human check. Also covers the working rules around it - Editor dialogs (accept API Updater and reimport, never discard or revert), human-safe generators, and when to notify the user. Use before saying a gameplay, input, UI, flow, rendering or tooling change is finished, when asked to test or verify a Unity change, or when an Editor dialog or a generator script is involved.
---

# Verify a Unity change before calling it done

A clean compile proves nothing about gameplay. A change is done when a test that exercises it passes, the game
state you expected can be read back, and everything that couldn't be automated is listed for the user.

The plugin's Stop hook reminds the user when C# changed in a session; this skill is the checklist behind it.

## Checklist

1. **Compile clean**: no errors and no new warnings in the Console. Not the finish line, only the entry ticket.
2. **PlayMode tests**: run the feature's PlayMode tests (and the suite if shared code changed). Add or extend a test
   for this change. A gameplay, input, UI or flow change without a test that would fail if it broke is not done.
   - Input tests drive real Input System devices with queued state events (unity-playmode-input-tests skill).
     Never autopilots, movement overrides or calling the handler directly; those skip the bindings that break.
   - UI Toolkit tests send real pointer events to the panel.
   - `unity test` refuses a project that's open in an Editor; run tests through the open Editor instead (the
     playmode tests skill has a runner script that can't report a stale or empty run as green).
3. **Game state through the debug menu**: set up and read state with the feature's debug menu section and its
   `unity command debugmenu` CLI mirror, not one-off script evals. If the control you need doesn't exist, add it to
   the feature's section (unity-debug-menu-cli skill); it then serves tests, agents and humans.
4. **Manual check when needed**: Enter Play mode, capture the game view (unity-editor-cli-recovery skill), look.
   Always **exit Play mode** afterwards: recompiles are deferred while playing, so the next edit won't show up.
5. **Report**: say what ran and passed, what was added, and list anything that can't be tested automatically (look
   and feel, VFX timing, audio mix, shader output on other platforms) as items for the user to check by hand.

## Editor dialogs

When a modal dialog blocks the Editor (`unity command` times out while `unity status` says ready), find it with the
unity-editor-cli-recovery skill's dialog script, then:

- **Accept**: the API Updater, reimport prompts, "Enter Safe Mode" (then fix the compile errors in Safe Mode).
- **Never accept**: anything that discards, reverts or deletes (unsaved scene changes, "Revert", "Delete", "Don't
  Save"). Stop and ask the user, quoting the dialog.
- If the Editor hangs or crashes, restart it and tell the user it was restarted.

## Generators and builders

Humans edit and maintain the project, so tools must never overwrite their work.

- Builders that create scenes, prefabs or ScriptableObject data run once and refuse to overwrite an existing asset.
  Prefer an editor tool (UI Toolkit) a human can run and re-run on purpose.
- Generators may only write derived output (icons, VFX, atlases, baked data) into folders marked as generated, and
  skip outputs that already exist unless the user deletes them to rebuild.
- Put a repeated task in a reusable script under `Tools/` or a custom `unity command`, not a one-off eval.

## Notify

Send a push notification when blocked, when a decision is needed, or when the task is finished; not for each step.
