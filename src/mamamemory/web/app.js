// app.js — S3: розмова в застосунку. Показує відповіді й план, кнопку «так» під планом (і під «Створити справу?», F3) з `reply_to`
// свого повідомлення. Поля для набору немає (C8): `send(text)` кличе голос (S2) або tracer з DevTools.
import { clarifyButtons, nextReplyTo, sendMessage, yesButton } from "/message.js";
import { uploadFile } from "/upload.js";
import { speak } from "/speak.js";
import { makePlay } from "/player.js";
import { initialButton, onButton } from "/speak_button.js";
import { restore } from "/open_questions.js";
import { loadGuide, nextGuide } from "/help.js";
import { bindButtons } from "/buttons.js";
import { mineText } from "/dialog.js";
import { buildCard } from "/card.js";
import { createRecorder } from "/recorder.js";
import { initial, on, statusOf } from "/voice_state.js";

const conversation = document.getElementById("conversation");
let lastReplyTo = null;
let voice = initial(null);

const NOT_SENT = { text: "Не вдалося, спробуйте ще раз.", question: null, plan: null, failed: true };

async function answerOf(response) {
  if (!response.ok) return NOT_SENT;
  return response.json();
}

async function post(url, body) {
  try {
    const response = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    return await answerOf(response);
  } catch {
    return NOT_SENT;
  }
}

/** Повідомлення з новим `message_id` (повтор після обриву мережі — з тим самим). */
async function message(text, replyTo) {
  try {
    return await answerOf(await sendMessage(fetch, () => crypto.randomUUID(), text, replyTo));
  } catch {
    return NOT_SENT;
  }
}

/** Мамине повідомлення в розмові (dialog): абзац праворуч, без 🔊; очікуване питання й голос не змінює. */
function renderMine(text) {
  if (!text) return;
  const item = document.createElement("p");
  item.className = "mine";
  item.textContent = text;
  conversation.append(item);
}

/** Лише абзац і 🔊 — без змін очікуваного питання (гайд кнопкою, calm-open). */
function renderText(text) {
  const item = document.createElement("p");
  item.textContent = text;
  conversation.append(item);
  if (text) conversation.append(speakButton(text));
}

/** Елемент для `buildCard`: тег, клас, текст лише через `textContent`. */
function make(tag, className, text) {
  const element = document.createElement(tag);
  if (className) element.className = className;
  if (text !== null && text !== undefined) element.textContent = text;
  return element;
}

function show(reply) {
  if (reply.card) {
    conversation.append(buildCard(reply.card, make));
    conversation.append(speakButton(reply.text));
  } else {
    renderText(reply.text);
  }
  const targets = [];
  const button = yesButton(reply);
  if (button) targets.push({ label: "так", url: button.url, body: button.body });
  for (const choice of clarifyButtons(reply)) targets.push(choice);
  const elements = targets.map((target) => {
    const element = document.createElement("button");
    element.textContent = target.label;
    conversation.append(element);
    return element;
  });
  // Одна сторожа на всі кнопки повідомлення (one-message): один натиск — одна відповідь.
  const press = bindButtons(elements, post);
  elements.forEach((element, n) => {
    element.addEventListener("click", () => pressed(press, targets[n]));
  });
  lastReplyTo = nextReplyTo(reply);
  voice = on(voice, { type: "assistant_reply", reply }).state;
}

/** Відповідь на натиск: збій — лише текст (кнопки знову ввімкнені, очікуване питання те саме); інакше — `show`. */
async function pressed(press, target) {
  const answer = await press(target.url, target.body);
  if (answer === null) return;
  renderMine(mineText("button", target.label));
  if (answer.failed) renderText(answer.text);
  else show(answer);
}

const play = makePlay(Audio, URL);

/** «🔊» біля відповіді: озвучує її на натиск; під час озвучення — «⏹», натиск зупиняє (C4: лише на прохання). */
function speakButton(text) {
  const element = document.createElement("button");
  element.setAttribute("aria-label", "прочитай");
  let button = initialButton();
  let controller = null;
  const paint = () => {
    element.textContent = button.label;
    element.disabled = button.disabled;
  };
  const dispatch = (event) => {
    const next = onButton(button, event);
    button = next.button;
    paint();
    return next.action;
  };
  element.addEventListener("click", async () => {
    const action = dispatch("press");
    if (action === "abort") controller?.abort();
    if (action !== "start") return;
    controller = new AbortController();
    const failed = await speak(fetch, play, text, controller.signal);
    if (failed) status.textContent = failed;
    dispatch("finished");
  });
  paint();
  return element;
}

/** Надсилає текст мами з `reply_to` останньої відповіді на екрані. */
export async function send(text) {
  const reply_to = lastReplyTo;
  renderMine(mineText("said", text));
  show(await message(text, reply_to));
}

// ------------------------------------------------------------------ голос (S2)

const FAILED = "Не вдалося, спробуйте ще раз.";

function pickType() {
  return ["audio/webm;codecs=opus", "audio/ogg;codecs=opus"].find((t) => MediaRecorder.isTypeSupported(t));
}

async function transcribe(blob) {
  try {
    const response = await fetch("/api/transcribe", {
      method: "POST",
      headers: { "Content-Type": blob.type },
      body: blob,
    });
    const body = await response.json().catch(() => ({ error: FAILED }));
    dispatch({ type: "transcribed", status: response.status, body });
  } catch {
    dispatch({ type: "transcribed", status: 0, body: { error: FAILED } });
  }
}

const recorder = createRecorder({
  getUserMedia: () => navigator.mediaDevices.getUserMedia({ audio: true }),
  MediaRecorder,
  Blob,
  mimeType: pickType(),
  onAudio: transcribe,
  onNoAudio: () => dispatch({ type: "transcribed", status: 0, body: { error: FAILED } }),
  onFailed: () => dispatch({ type: "recording_failed", error: FAILED }),
});

const draft = document.getElementById("draft");

const status = document.getElementById("status");
const mic = document.getElementById("mic");
const sendButton = document.getElementById("send");

function render() {
  const view = statusOf(voice);
  status.textContent = view.label;
  mic.classList.toggle("recording", view.recording);
  sendButton.disabled = !view.canSend;
}

function dispatch(event) {
  const out = on(voice, event);
  voice = out.state;
  render();
  for (const action of out.actions) {
    if (action.do === "start_recording") recorder.start();
    if (action.do === "stop_and_transcribe") recorder.stop();
    if (action.do === "show_draft") draft.textContent = action.text;
    if (action.do === "show_error") draft.textContent = action.error;
    if (action.do === "send_message") {
      draft.textContent = "";
      renderMine(mineText("said", action.text));
      message(action.text, action.reply_to).then(show);
    }
  }
}

// ------------------------------------------------------------------ відкриття (S4)

async function openQuestions() {
  const response = await fetch("/api/open");
  if (response.status === 401) {
    window.location.href = "/auth/login";
    return;
  }
  if (!response.ok) return;
  const restored = restore(await response.json());
  restored.shown.forEach(show);
  if (restored.loginNeeded) {
    const link = document.createElement("a");
    link.href = "/auth/login";
    link.textContent = "Увійти";
    conversation.append(link);
  }
}

// ------------------------------------------------------------------ фото й файли (F3 S2)

async function upload(input) {
  const file = input.files && input.files[0];
  input.value = "";
  if (!file) return;
  status.textContent = "Надсилаю…";
  renderMine(mineText("file", file.name));
  try {
    show(await uploadFile(fetch, () => crypto.randomUUID().replaceAll("-", ""), file));
  } catch {
    show(NOT_SENT);
  }
  render();
}

for (const [button, input] of [["add", "add-input"]]) {
  const field = document.getElementById(input);
  document.getElementById(button).addEventListener("click", () => field.click());
  field.addEventListener("change", () => upload(field));
}

mic.addEventListener("click", () => dispatch({ type: "mic" }));
sendButton.addEventListener("click", () => dispatch({ type: "send" }));
render();
openQuestions();

window.mamamemory = { send };

// ------------------------------------------------------------------ «Що я вмію» (calm-open)

// Один блок `#guide`: перший клік відкриває, другий згортає (add-simply). Розмови й `reply_to` не чіпає.
const guideBlock = document.getElementById("guide");
document.getElementById("help").addEventListener("click", async () => {
  if (nextGuide(!guideBlock.hidden) === "close") {
    guideBlock.hidden = true;
    return;
  }
  const guide = await loadGuide(fetch);
  if (guide === "login") window.location.href = "/auth/login";
  else if (guide) {
    guideBlock.textContent = guide.text;
    guideBlock.hidden = false;
  }
});
