// Tests of web/message.js (F3 S1 note-to-case): the «так» button under «Створити справу?» and `message_id`.
import { test } from "node:test";
import assert from "node:assert/strict";

import { sendMessage, yesButton } from "./message.js";

test("кнопка «так» під «Створити справу?» шле /api/case/confirm з material_id", () => {
  const reply = { text: "Створити справу «пані Шмідт»?", question: { kind: "case", id: "m-1", fingerprint: null } };
  assert.deepEqual(yesButton(reply), { url: "/api/case/confirm", body: { material_id: "m-1" } });
});

test("кнопка «так» під планом — як раніше, без кнопки під іншими відповідями", () => {
  const plan = { question: { kind: "plan", id: "p", fingerprint: "f" }, plan: { plan_id: "p", fingerprint: "f" } };
  assert.deepEqual(yesButton(plan), { url: "/api/plan/confirm", body: { plan_id: "p", fingerprint: "f" } });
  assert.equal(yesButton({ question: { kind: "duration", id: "p", fingerprint: null }, plan: null }), null);
  assert.equal(yesButton({ question: null, plan: null }), null);
});

test("кожне надсилання — новий message_id, повтор після обриву мережі — той самий", async () => {
  const bodies = [];
  let broken = 1;
  const fetchFn = async (_url, init) => {
    bodies.push(JSON.parse(init.body));
    if (broken-- > 0) throw new TypeError("network");
    return { ok: true };
  };
  let n = 0;
  const newId = () => `id-${++n}`;
  await sendMessage(fetchFn, newId, "запиши до пані Шмідт", null);
  await sendMessage(fetchFn, newId, "друга нотатка", null);
  assert.deepEqual(bodies.map((b) => b.message_id), ["id-1", "id-1", "id-2"]);
  assert.equal(bodies[0].text, "запиши до пані Шмідт");
});

test("під уточненням — дві кнопки з фразами, кожна шле /api/clarify з номером", async () => {
  const { clarifyButtons } = await import("./message.js");
  const reply = {
    text: "Не зовсім зрозуміла: записати нотаткою до справи чи поставити задачею в календар?",
    question: { kind: "clarify", id: "c-1", fingerprint: null },
    choices: ["записати нотаткою до справи", "поставити задачею в календар"],
  };
  assert.deepEqual(clarifyButtons(reply), [
    { label: "записати нотаткою до справи", url: "/api/clarify", body: { clarify_id: "c-1", option: 1 } },
    { label: "поставити задачею в календар", url: "/api/clarify", body: { clarify_id: "c-1", option: 2 } },
  ]);
  assert.deepEqual(clarifyButtons({ question: { kind: "plan", id: "p", fingerprint: "f" } }), []);
});

test("відповідь без питання скидає reply_to наступного повідомлення", async () => {
  const { nextReplyTo } = await import("./message.js");
  assert.deepEqual(nextReplyTo({ question: { kind: "duration", id: "d", fingerprint: null } }), {
    kind: "duration", id: "d", fingerprint: null,
  });
  assert.equal(nextReplyTo({ text: "Поклала в «пан Кох».", question: null }), null);
});
