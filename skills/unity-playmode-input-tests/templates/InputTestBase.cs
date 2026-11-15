using System;
using System.Collections;
using System.Linq;
using NUnit.Framework;
using UnityEngine;
using UnityEngine.InputSystem;
using UnityEngine.InputSystem.Controls;
using UnityEngine.InputSystem.LowLevel;
using UnityEngine.TestTools;
using UnityEngine.UIElements;

namespace MyGame.Tests
{
    /// <summary>
    /// Base for PlayMode tests that drive the game through REAL input devices: state events queued on keyboard /
    /// mouse / gamepad go through the Input System, the game's actions and the UI input module exactly like hardware.
    /// Use code shortcuts for test setup only, never for the behaviour under test.
    ///
    /// InputTestFixture is deliberately not used: it resets the Input System after the game has enabled its actions
    /// at startup, which leaves those actions with stale state.
    /// </summary>
    public abstract class InputTestBase
    {
        protected Keyboard Keyboard;
        protected Mouse Mouse;
        private Gamepad _addedGamepad;

        private InputSettings.EditorInputBehaviorInPlayMode _savedEditorBehavior;
        private InputSettings.BackgroundBehavior _savedBackground;

        [SetUp]
        public void SetUpDevices()
        {
            // Without this, keyboard/pointer input only reaches the game while the Game view has focus.
            _savedEditorBehavior = InputSystem.settings.editorInputBehaviorInPlayMode;
            _savedBackground = InputSystem.settings.backgroundBehavior;
            InputSystem.settings.editorInputBehaviorInPlayMode = InputSettings.EditorInputBehaviorInPlayMode.AllDeviceInputAlwaysGoesToGameView;
            InputSystem.settings.backgroundBehavior = InputSettings.BackgroundBehavior.IgnoreFocus;
            Keyboard = Keyboard.current ?? InputSystem.AddDevice<Keyboard>();
            Mouse = Mouse.current ?? InputSystem.AddDevice<Mouse>();
            Time.timeScale = 1f;
        }

        [UnityTearDown]
        public IEnumerator TearDownDevices()
        {
            if (Keyboard != null) InputSystem.QueueStateEvent(Keyboard, new KeyboardState());
            if (Mouse != null) Release(Mouse.leftButton);
            if (_addedGamepad != null) InputSystem.QueueStateEvent(_addedGamepad, new GamepadState());
            yield return null; // let the neutral states process before removing devices
            if (_addedGamepad != null) InputSystem.RemoveDevice(_addedGamepad);
            _addedGamepad = null;
            Time.timeScale = 1f;
            InputSystem.settings.editorInputBehaviorInPlayMode = _savedEditorBehavior;
            InputSystem.settings.backgroundBehavior = _savedBackground;
            OnTearDown();
        }

        /// <summary>Project hook: reset pause state, singletons, etc.</summary>
        protected virtual void OnTearDown() { }

        // ------------------------------------------------------------------ devices

        /// <summary>Adds a gamepad for this test (removed in teardown). Add it before the game reads devices if it matters.</summary>
        protected Gamepad AddGamepad()
        {
            _addedGamepad = InputSystem.AddDevice<Gamepad>();
            return _addedGamepad;
        }

        // Every helper below queues a FULL device state event built from the device's state as it is right now.
        // Queued events aren't applied until the next input update, so a second event for the same device in the
        // same frame is built from the old state and undoes the first one (Shift then D in one frame = only D held;
        // centring a stick then tapping a button = stick pushed again). Change several buttons of one device at
        // once with Press(a, b) / Release(a, b), or yield a frame between calls on the same device.

        private static void Write<T>(InputControl<T> control, T value) where T : struct
        {
            using (StateEvent.From(control.device, out var eventPtr))
            {
                control.WriteValueIntoEvent(value, eventPtr);
                InputSystem.QueueEvent(eventPtr);
            }
        }

        private static void WriteButtons(ButtonControl[] buttons, float value)
        {
            foreach (var group in buttons.GroupBy(b => b.device))
            {
                using (StateEvent.From(group.Key, out var eventPtr))
                {
                    foreach (var button in group) button.WriteValueIntoEvent(value, eventPtr);
                    InputSystem.QueueEvent(eventPtr);
                }
            }
        }

        /// <summary>Press one or more buttons in one event per device, e.g. Press(Keyboard.leftShiftKey, Keyboard.dKey).</summary>
        protected static void Press(params ButtonControl[] buttons) => WriteButtons(buttons, 1f);

        /// <summary>Release one or more buttons in one event per device.</summary>
        protected static void Release(params ButtonControl[] buttons) => WriteButtons(buttons, 0f);

        /// <summary>Set a stick. One event per device per frame (see the note above).</summary>
        protected static void Set(Vector2Control control, Vector2 value) => Write(control, value);

        /// <summary>Set a single axis such as a trigger. One event per device per frame.</summary>
        protected static void Set(AxisControl control, float value) => Write(control, value);

        /// <summary>Press, hold for two frames, release, wait two frames (enough for "performed" + UI submit).</summary>
        protected static IEnumerator Tap(ButtonControl button)
        {
            Press(button);
            yield return null;
            yield return null;
            Release(button);
            yield return null;
            yield return null;
        }

        // ------------------------------------------------------------------ waiting

        /// <summary>Waits (unscaled time, so it works while paused) until the condition holds, else fails the test.</summary>
        protected static IEnumerator WaitFor(Func<bool> condition, float timeout, string what)
        {
            float t = 0;
            while (!condition())
            {
                t += Time.unscaledDeltaTime;
                if (t > timeout) Assert.Fail($"Timed out after {timeout}s waiting for: {what}");
                yield return null;
            }
        }

        /// <summary>For GPU readbacks (e.g. VisualEffect.aliveParticleCount) that lag a few frames.</summary>
        protected static IEnumerator PollFrames(Func<bool> condition, int frames = 30)
        {
            for (int i = 0; i < frames && !condition(); i++) yield return null;
        }

        // ------------------------------------------------------------------ UI Toolkit mouse

        /// <summary>UI Toolkit panel position (origin top-left, panel scale) → mouse screen position (origin bottom-left).</summary>
        protected static Vector2 PanelToScreen(VisualElement anyInPanel, Vector2 panelPos)
        {
            var r = anyInPanel.panel.visualTree.layout;
            return new Vector2(panelPos.x * Screen.width / r.width, Screen.height - panelPos.y * Screen.height / r.height);
        }

        /// <summary>Screen centre of an element's world bound.</summary>
        protected static Vector2 ScreenCenter(VisualElement e) => PanelToScreen(e, e.worldBound.center);

        /// <summary>
        /// Moves the mouse. Nudges it away first: if the pointer is already at the target (left there by a previous
        /// test), no move event fires and hover code never runs.
        /// </summary>
        protected IEnumerator MoveMouse(Vector2 screenPos, int frames = 2)
        {
            if ((Mouse.position.ReadValue() - screenPos).sqrMagnitude < 4f)
            {
                Set(Mouse.position, screenPos + new Vector2(40f, 40f));
                yield return null;
            }
            Set(Mouse.position, screenPos);
            for (int i = 0; i < frames; i++) yield return null;
        }

        protected IEnumerator Click(Vector2 screenPos)
        {
            yield return MoveMouse(screenPos);
            Press(Mouse.leftButton);
            yield return null;
            yield return null;
            Release(Mouse.leftButton);
            yield return null;
            yield return null;
        }

        /// <summary>Press at from, move through the midpoint, release at to.</summary>
        protected IEnumerator Drag(Vector2 from, Vector2 to)
        {
            yield return MoveMouse(from);
            Press(Mouse.leftButton);
            yield return null;
            yield return null;
            yield return MoveMouse(Vector2.Lerp(from, to, 0.5f));
            yield return MoveMouse(to);
            Release(Mouse.leftButton);
            yield return null;
            yield return null;
        }

        // ------------------------------------------------------------------ project hooks (fill these in)

        // Examples:
        // protected static VisualElement HudRoot =>
        //     UnityEngine.Object.FindAnyObjectByType<GameUI>().GetComponent<UIDocument>().rootVisualElement;
        //
        // protected IEnumerator StartGame()
        // {
        //     SceneManager.LoadScene("Game");
        //     yield return WaitFor(() => GameManager.Instance != null && GameManager.Instance.IsPlaying, 15f, "game start");
        // }
    }
}
