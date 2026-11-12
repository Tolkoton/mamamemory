// Contract tests of web/speak_button.js (slice speak-control, Seam 4 «кнопка»), written by the slice tester
// from the sealed contract `.engine/slices/speak-control.md`, without the code. The contract writes states,
// events and actions as bare names (`idle`, `press`, `start`); they are the strings of those names, as
// `initialButton()` shows for `state: "idle"`. Only `state`, `label` and `disabled` of a button are compared.
import { test } from "node:test";
import assert from "node:assert/strict";

import { initialButton, onButton } from "./speak_button.js";

const IDLE = { state: "idle", label: "🔊", disabled: false };
const SPEAKING = { state: "speaking", label: "⏹", disabled: false };
const STOPPING = { state: "stopping", label: "⏹", disabled: false };

const shown = (button) => ({ state: button.state, label: button.label, disabled: button.disabled });

/** The button after `events` from the start, and every step's action. */
function run(events) {
  let button = initialButton();
  const actions = [];
  for (const event of events) {
    const out = onButton(button, event);
    button = out.button;
    actions.push(out.action);
  }
  return { button, actions };
}

test("initial_button_is_idle_speaker_not_disabled", () => {
  assert.deepEqual(initialButton(), IDLE);
});

test("press_when_idle_shows_stop_and_starts", () => {
  const out = onButton(initialButton(), "press");
  assert.deepEqual(shown(out.button), SPEAKING);
  assert.equal(out.action, "start");
});

test("press_while_speaking_aborts_and_the_button_stays_enabled", () => {
  const { button, actions } = run(["press", "press"]);
  assert.deepEqual(shown(button), STOPPING);
  assert.deepEqual(actions, ["start", "abort"]);
});

test("finished_while_speaking_or_stopping_returns_to_idle_with_no_action", () => {
  const fromSpeaking = run(["press", "finished"]);
  assert.deepEqual(shown(fromSpeaking.button), IDLE);
  assert.equal(fromSpeaking.actions[1], "none");

  const fromStopping = run(["press", "press", "finished"]);
  assert.deepEqual(shown(fromStopping.button), IDLE);
  assert.equal(fromStopping.actions[2], "none");
});

test("press_while_stopping_changes_nothing_with_no_action", () => {
  const { button, actions } = run(["press", "press", "press"]);
  assert.deepEqual(shown(button), STOPPING);
  assert.equal(actions[2], "none");
});

test("finished_when_idle_changes_nothing", () => {
  const out = onButton(initialButton(), "finished");
  assert.deepEqual(shown(out.button), IDLE);
});

test("no_state_is_ever_disabled", () => {
  const sequences = [
    ["press", "press", "press", "finished", "press", "finished", "finished"],
    ["finished", "press", "finished", "press", "press", "finished", "press", "press", "press"],
  ];
  for (const events of sequences) {
    let button = initialButton();
    assert.equal(button.disabled, false, "the initial button is disabled");
    for (const event of events) {
      button = onButton(button, event).button;
      assert.equal(button.disabled, false, `${events.join(" → ")}: disabled after ${event} in ${button.state}`);
    }
  }
});
