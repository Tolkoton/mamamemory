// open_questions.js — S4: що показати після перевідкриття застосунку. Чистий модуль, без DOM і мережі.
// Не робить: запиту до /api/open (це робить app.js), надсилання.

/** `body` — відповідь `GET /api/open`. Повертає {shown, replyTo, loginNeeded}. */
export function restore(body) {
  const shown = body.replies ?? [];
  const question = shown.length > 0 ? shown[shown.length - 1].question : null;
  const replyTo = question ? { kind: question.kind, id: question.id, fingerprint: question.fingerprint } : null;
  return { shown, replyTo, loginNeeded: Boolean(body.login_needed) };
}
