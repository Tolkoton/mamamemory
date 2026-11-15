// buttons.js — кнопки одного повідомлення («так», уточнення) спрацьовують один раз (one-message): одна сторожа на всі,
// поки запит іде — вимкнені; успіх — зникають; збій — вмикаються, і можна натиснути ще раз.

const FAILED = { text: "Не вдалося, спробуйте ще раз.", question: null, plan: null, failed: true };

/** `press(url, body)` для всіх `elements` одного повідомлення; `null` — натиск не пішов на сервер. */
export function bindButtons(elements, postFn) {
  let state = "open";
  return async function press(url, body) {
    if (state !== "open") return null;
    state = "pending";
    for (const element of elements) element.disabled = true;
    let reply;
    try {
      reply = await postFn(url, body);
    } catch {
      reply = FAILED;
    }
    if (reply && reply.failed) {
      for (const element of elements) element.disabled = false;
      state = "open";
      return reply;
    }
    for (const element of elements) element.remove();
    state = "closed";
    return reply;
  };
}
