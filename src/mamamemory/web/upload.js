// upload.js — F3 S2: фото чи файл → POST /api/upload. Чистий модуль, без DOM: `fetch` і генератор id —
// параметрами. Тіло — сам файл, `X-Material-Id` — новий на кожен файл, той самий на повторах.

const FAILED = "Не вдалося, спробуйте ще раз.";

function request(fetchFn, id, file) {
  const headers = { "X-Material-Id": id };
  if (file) headers["Content-Type"] = file.type || "application/octet-stream";
  return fetchFn("/api/upload", { method: "POST", headers, body: file || undefined });
}

/** Надсилає файл; обрив мережі — ще раз з тим самим тілом; відповідь «Не вдалося…» — один повтор лише заголовком. */
export async function uploadFile(fetchFn, newId, file) {
  const id = newId().slice(0, 59);
  let response;
  try {
    response = await request(fetchFn, id, file);
  } catch {
    response = await request(fetchFn, id, file);
  }
  const reply = response.ok ? await response.json() : { text: FAILED, question: null, plan: null };
  if (reply.text !== FAILED) return reply;
  const again = await request(fetchFn, id, null);
  return again.ok ? again.json() : reply;
}
