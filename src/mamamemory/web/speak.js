// speak.js — F5 S3: «🔊» → озвучення відповіді частинами через POST /api/speak {text, part}. Чистий модуль, без
// DOM: `fetch` і програвач — параметрами. Частина 0 → грає; поки грає i — запит i+1 (кількість — з `X-Parts`).

export const FAILED = "Не вдалося озвучити.";

const speaking = new Set();

/** `X-Parts` — лише десяткові цифри й ≥ 1; інакше NaN. */
function partsCount(header) {
  return /^[0-9]+$/.test(header ?? "") && Number(header) >= 1 ? Number(header) : NaN;
}

/** Аудіо частини `part` і кількість частин; помилка мережі чи сервера — null. */
async function fetchPart(fetchFn, text, part, signal) {
  try {
    const response = await fetchFn("/api/speak", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text, part }),
      signal,
    });
    if (!response.ok) return null;
    return { audio: await response.blob(), count: partsCount(response.headers.get("X-Parts")) };
  } catch {
    return null;
  }
}

/** Грає частини по черзі; помилка мережі, сервера, `X-Parts` чи програвання будь-якої — зупинка з FAILED;
 * перерваний `signal` — жодного нового запиту й нової частини, null. */
async function playAll(fetchFn, play, text, signal) {
  const stopped = () => signal?.aborted === true;
  if (stopped()) return null;
  let current = await fetchPart(fetchFn, text, 0, signal);
  if (stopped()) return null;
  if (current === null || Number.isNaN(current.count)) return FAILED;
  for (let part = 0; part < current.count; part += 1) {
    const next = part + 1 < current.count ? fetchPart(fetchFn, text, part + 1, signal) : null;
    try {
      await play(current.audio, signal);
    } catch {
      return stopped() ? null : FAILED;
    }
    if (stopped()) return null;
    if (next === null) break;
    const fetched = await next;
    if (stopped()) return null;
    if (fetched === null) return FAILED;
    current = { audio: fetched.audio, count: current.count };
  }
  return null;
}

/** Озвучує текст частинами по черзі; повертає null на успіх або FAILED. Поки текст звучить, повтор нічого не робить. */
export async function speak(fetchFn, play, text, signal) {
  if (speaking.has(text)) return null;
  speaking.add(text);
  try {
    return await playAll(fetchFn, play, text, signal);
  } finally {
    speaking.delete(text);
  }
}
