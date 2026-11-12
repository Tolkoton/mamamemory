// Tests of web/upload.js (F3 S2 photo-and-file): the request, the id, the repeats.
import { test } from "node:test";
import assert from "node:assert/strict";

import { uploadFile } from "./upload.js";

const FAILED = "Не вдалося, спробуйте ще раз.";

function recorder(answers) {
  const sent = [];
  const fetchFn = async (url, init) => {
    sent.push({ url, ...init });
    const next = answers.shift();
    if (next instanceof Error) throw next;
    return { ok: true, json: async () => next };
  };
  return { sent, fetchFn };
}

test("файл іде тілом з Content-Type файлу й X-Material-Id; новий id на кожен файл", async () => {
  const { sent, fetchFn } = recorder([{ text: "Поклала в «пані Шмідт»." }, { text: "Поклала в «город»." }]);
  let n = 0;
  const newId = () => `id-${++n}`;
  const photo = { type: "image/jpeg" };
  const pdf = { type: "application/pdf" };
  await uploadFile(fetchFn, newId, photo);
  await uploadFile(fetchFn, newId, pdf);
  assert.equal(sent[0].url, "/api/upload");
  assert.deepEqual(sent[0].headers, { "X-Material-Id": "id-1", "Content-Type": "image/jpeg" });
  assert.equal(sent[0].body, photo);
  assert.deepEqual(sent[1].headers, { "X-Material-Id": "id-2", "Content-Type": "application/pdf" });
});

test("обрив мережі — той самий файл і той самий id ще раз", async () => {
  const { sent, fetchFn } = recorder([new TypeError("network"), { text: "Поклала в «пані Шмідт»." }]);
  const reply = await uploadFile(fetchFn, () => "same", { type: "image/png" });
  assert.equal(reply.text, "Поклала в «пані Шмідт».");
  assert.deepEqual(sent.map((s) => s.headers["X-Material-Id"]), ["same", "same"]);
  assert.equal(sent[1].body.type, "image/png");
});

test("після «Не вдалося» — один повтор лише заголовком, без тіла й Content-Type", async () => {
  const { sent, fetchFn } = recorder([{ text: FAILED }, { text: "Створити справу «пані Шмідт»?" }]);
  const reply = await uploadFile(fetchFn, () => "m-1", { type: "image/png" });
  assert.equal(reply.text, "Створити справу «пані Шмідт»?");
  assert.equal(sent.length, 2);
  assert.deepEqual(sent[1].headers, { "X-Material-Id": "m-1" });
  assert.equal(sent[1].body, undefined);
});
