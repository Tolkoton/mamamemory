// reply_to.js — S3: яке `reply_to` несе кнопка «так» під планом. Чистий модуль, без DOM.
// Не робить: надсилання (це робить застосунок), голосу (S2).

/** `reply_to` кнопки «так» під відповіддю `reply` — питання саме цього повідомлення. */
export function replyToOf(reply) {
  const { kind, id, fingerprint } = reply.question;
  return { kind, id, fingerprint };
}

/** Тіло POST /api/plan/confirm для кнопки під відповіддю `reply`. */
export function confirmBody(reply) {
  return { plan_id: reply.plan.plan_id, fingerprint: reply.plan.fingerprint };
}
