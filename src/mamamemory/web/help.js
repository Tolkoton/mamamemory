// help.js — кнопка «Що я вмію» (calm-open): гайд з `GET /api/guide`. Повертає лише текст — показ гайду не чіпає
// очікуваного питання (`reply_to`).

/** `{text}` — гайд; `"login"` — сесії немає (401); `null` — інша відповідь чи мережа впала. */
export async function loadGuide(fetchFn) {
  try {
    const response = await fetchFn("/api/guide");
    if (response.status === 401) return "login";
    if (!response.ok) return null;
    const body = await response.json();
    return { text: body.reply.text };
  } catch {
    return null;
  }
}

/** Кнопка «Що я вмію» перемикає один блок гайду (add-simply): прихований — відкрити, показаний — сховати. */
export function nextGuide(shown) {
  return shown ? "close" : "open";
}
