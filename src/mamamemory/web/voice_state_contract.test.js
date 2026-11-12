// Contract tests of web/voice_state.js (slice voice-to-text, Seam 3 and I2), written by the slice tester
// from the sealed contract `.engine/slices/voice-to-text.md`, without the code. Only the actions
// returned by `on` are observed; the shape of the state is the module's own.
import { test } from "node:test";
import assert from "node:assert/strict";

import { initial, on } from "./voice_state.js";

const REPLY_TO = { kind: "duration", id: "q-41", fingerprint: null };
const SAID = "Подзвонити д-ру Müller у п'ятницю о 10:15";
const NOT_HEARD = "Не почула, спробуйте ще раз.";
const FAILED = "Не вдалося, спробуйте ще раз.";

const MIC = { type: "mic" };
const SEND = { type: "send" };
const heard = (text) => ({ type: "transcribed", status: 200, body: { text } });
const refused = (status, error, extra = {}) => ({ type: "transcribed", status, body: { error, ...extra } });

const of = (actions, kind) => actions.filter((a) => a.do === kind);

/** Feed events in order; returns the last state and every step's actions. */
function run(state, events) {
  const steps = [];
  for (const event of events) {
    const out = on(state, event);
    state = out.state;
    steps.push(out.actions);
  }
  return { state, steps };
}

/** The send_message actions of all steps. */
const sent = (steps) => steps.flatMap((actions) => of(actions, "send_message"));

test("request_1_does_not_reset_reply_to", () => {
  const { steps } = run(initial(REPLY_TO), [MIC, SEND, heard(SAID), SEND]);
  assert.equal(of(steps[0], "start_recording").length, 1);
  assert.equal(of(steps[1], "stop_and_transcribe").length, 1);
  assert.deepEqual(sent(steps.slice(0, 3)), []);
  assert.deepEqual(of(steps[3], "send_message"), [{ do: "send_message", text: SAID, reply_to: REPLY_TO }]);
});

test("second_send_sends_the_text_shown", () => {
  const { steps } = run(initial(null), [MIC, SEND, heard(SAID), SEND]);
  assert.deepEqual(of(steps[2], "show_draft"), [{ do: "show_draft", text: SAID }]);
  assert.deepEqual(sent(steps), [{ do: "send_message", text: SAID, reply_to: null }]);
});

test("new_recording_from_text_ready_does_not_send_old_draft", () => {
  const second = "Ні, у четвер";
  const { steps } = run(initial(REPLY_TO), [MIC, SEND, heard(SAID), MIC, SEND, heard(second), SEND]);
  assert.equal(of(steps[3], "start_recording").length, 1);
  assert.deepEqual(of(steps[3], "send_message"), []);
  assert.equal(of(steps[4], "stop_and_transcribe").length, 1);
  assert.deepEqual(sent(steps), [{ do: "send_message", text: second, reply_to: REPLY_TO }]);
});

test("presses_while_transcribing_do_nothing", () => {
  const { steps } = run(initial(REPLY_TO), [MIC, SEND, SEND, MIC, SEND, heard(SAID), SEND]);
  assert.equal(of(steps[1], "stop_and_transcribe").length, 1);
  assert.deepEqual(steps[2], []);
  assert.deepEqual(steps[3], []);
  assert.deepEqual(steps[4], []);
  assert.deepEqual(of(steps[5], "show_draft"), [{ do: "show_draft", text: SAID }]);
  assert.deepEqual(sent(steps), [{ do: "send_message", text: SAID, reply_to: REPLY_TO }]);
});

test("empty_text_ready_does_not_send", () => {
  const { steps } = run(initial(REPLY_TO), [MIC, SEND, heard(""), SEND, MIC]);
  assert.deepEqual(sent(steps), []);
  // Back in silence: the microphone starts a recording again.
  assert.equal(of(steps[4], "start_recording").length, 1);
});

test("non_2xx_answer_is_not_a_draft_and_is_not_sent", () => {
  for (const answer of [refused(400, NOT_HEARD), refused(502, FAILED, { text: "сміття" })]) {
    const { steps } = run(initial(REPLY_TO), [MIC, SEND, answer, SEND, MIC]);
    assert.deepEqual(of(steps[2], "show_error"), [{ do: "show_error", error: answer.body.error }]);
    assert.deepEqual(of(steps[2], "show_draft"), []);
    assert.deepEqual(sent(steps), []);
    // Back in silence.
    assert.equal(of(steps[4], "start_recording").length, 1);
  }
});

test("test_I2_request_1_never_changes_reply_to", () => {
  const cycle = [MIC, SEND, heard(SAID), SEND];
  const sequences = [
    ["plain", REPLY_TO, cycle],
    ["no reply on screen", null, cycle],
    ["after 400", REPLY_TO, [MIC, SEND, refused(400, NOT_HEARD), ...cycle]],
    ["after 502 carrying text", REPLY_TO, [MIC, SEND, refused(502, FAILED, { text: "x" }), ...cycle]],
    ["after empty text", REPLY_TO, [MIC, SEND, heard(""), SEND, ...cycle]],
    ["new recording from text ready", REPLY_TO, [MIC, SEND, heard("стара"), MIC, SEND, heard(SAID), SEND]],
    ["presses while transcribing", REPLY_TO, [MIC, SEND, SEND, MIC, heard(SAID), SEND]],
    ["two failures, then success", REPLY_TO,
      [MIC, SEND, refused(400, NOT_HEARD), MIC, SEND, refused(502, FAILED), ...cycle]],
  ];
  for (const [name, replyTo, events] of sequences) {
    const { steps } = run(initial(replyTo), events);
    assert.deepEqual(sent(steps), [{ do: "send_message", text: SAID, reply_to: replyTo }], name);
  }
});
