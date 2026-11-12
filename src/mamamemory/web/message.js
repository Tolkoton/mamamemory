// message.js — F3 S1: тіло повідомлення з `message_id` і кнопка «так» під «Створити справу?». Чистий модуль,
// без DOM: `fetch` і генератор id — параметрами. Не робить: показу (це app.js), голосу.

/** Кнопка «так» під відповіддю: план — POST /api/plan/confirm, «Створити справу?» — /api/case/confirm. */
export function yesButton(reply) {
  if (reply.plan) {
    return { url: "/api/plan/confirm", body: { plan_id: reply.plan.plan_id, fingerprint: reply.plan.fingerprint } };
  }
  if (reply.question && reply.question.kind === "case") {
    return { url: "/api/case/confirm", body: { material_id: reply.question.id } };
  }
  return null;
}

/** Кнопки під уточненням (clarify): фраза варіанта → POST /api/clarify {clarify_id, option}. */
export function clarifyButtons(reply) {
  if (!reply.question || reply.question.kind !== "clarify" || !Array.isArray(reply.choices)) return [];
  return reply.choices.map((label, i) => ({
    label,
    url: "/api/clarify",
    body: { clarify_id: reply.question.id, option: i + 1 },
  }));
}

/** `reply_to` наступного повідомлення — питання останньої відповіді; відповідь без питання його скидає. */
export function nextReplyTo(reply) {
  if (!reply || !reply.question) return null;
  const { kind, id, fingerprint } = reply.question;
  return { kind, id, fingerprint };
}

/** Надсилає повідомлення з новим `message_id`; обрив мережі — ще одна спроба з тим самим тілом (і id). */
export async function sendMessage(fetchFn, newId, text, replyTo) {
  const body = JSON.stringify({ text, reply_to: replyTo, message_id: newId() });
  const request = () =>
    fetchFn("/api/message", { method: "POST", headers: { "Content-Type": "application/json" }, body });
  try {
    return await request();
  } catch {
    return await request();
  }
}
