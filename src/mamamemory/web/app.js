// app.js — S3: розмова в застосунку. Показує відповіді й план, кнопку «так» під планом з `reply_to`
// свого повідомлення. Поля для набору немає (C8): `send(text)` кличе голос (S2) або tracer з DevTools.
import { confirmBody, replyToOf } from "/reply_to.js";

const conversation = document.getElementById("conversation");
let lastReply = null;

async function post(url, body) {
  const response = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!response.ok) return { text: "Не вдалося, спробуйте ще раз.", question: null, plan: null };
  return response.json();
}

function show(reply) {
  const item = document.createElement("p");
  item.textContent = reply.text;
  conversation.append(item);
  if (reply.plan) {
    const yes = document.createElement("button");
    yes.textContent = "так";
    yes.addEventListener("click", async () => show(await post("/api/plan/confirm", confirmBody(reply))));
    conversation.append(yes);
  }
  if (reply.question) lastReply = reply;
}

/** Надсилає текст мами з `reply_to` останньої відповіді на екрані. */
export async function send(text) {
  const reply_to = lastReply ? replyToOf(lastReply) : null;
  show(await post("/api/message", { text, reply_to }));
}

window.mamamemory = { send };
