// Contract test of web/reply_to.js (slice one-task-to-calendar, Seam 4), written by the slice tester
// from the sealed contract, without the code: the "yes" button under an older plan sends its own reply_to.
import { test } from "node:test";
import assert from "node:assert/strict";

import { confirmBody, replyToOf } from "./reply_to.js";

function planReply(planId, fingerprint, start) {
  return {
    text: "Пропоную: … Записати?",
    question: { kind: "plan", id: planId, fingerprint },
    plan: { plan_id: planId, title: "подзвонити нотаріусу", start, end: start, fingerprint },
  };
}

test("кнопка під старішим планом шле свій reply_to", () => {
  const older = planReply("plan-old", "fp-old", "2026-11-09T10:15:00+01:00");
  const newer = planReply("plan-new", "fp-new", "2026-11-09T12:00:00+01:00");
  // Both messages are on screen; the newer one came last.
  const conversation = [older, newer];

  assert.deepEqual(replyToOf(conversation[0]), { kind: "plan", id: "plan-old", fingerprint: "fp-old" });
  assert.deepEqual(confirmBody(conversation[0]), { plan_id: "plan-old", fingerprint: "fp-old" });
  assert.deepEqual(replyToOf(conversation[1]), { kind: "plan", id: "plan-new", fingerprint: "fp-new" });
  assert.deepEqual(confirmBody(conversation[1]), { plan_id: "plan-new", fingerprint: "fp-new" });
});
