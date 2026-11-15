# Moving mamamemory from one routing call to model tool calling: research notes

Date: 2026-11-15. The repo was only read, not changed. The SDK facts below were checked in `.venv/lib/python3.13/site-packages/google/genai/types.py`, version 2.34.0.

---

## 1. Gemini function calling on Vertex AI with google-genai

Sources:
- https://docs.cloud.google.com/vertex-ai/generative-ai/docs/multimodal/function-calling
- https://docs.cloud.google.com/vertex-ai/generative-ai/docs/model-reference/function-calling
- https://googleapis.github.io/python-genai/
- https://docs.cloud.google.com/vertex-ai/generative-ai/docs/thought-signatures
- https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/guides/gemini-3-5-flash

### Declaring tools
Three ways:
- **Manual declaration:** `types.FunctionDeclaration(name, description, parameters_json_schema={...})` inside `types.Tool(function_declarations=[...])`.
  - `parameters_json_schema` takes plain JSON Schema. The older `parameters=` takes the OpenAPI-subset `Schema`.
  - In 2.34.0, `FunctionDeclaration` also has a `response_json_schema` field.
- **Python callables:** pass them as `tools=[fn]`. This turns on automatic function calling (AFC): the SDK runs the function and loops by itself.
  - The default limit is `maximum_remote_calls=10`.
  - To turn it off: `automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True)`.
  - **Recommendation:** do not use AFC here. We must stop before destructive actions, enforce deadlines (`call_timeout_s`) and inject the account and session, and AFC hides that loop.
- **Schema features Vertex supports:**
  - Supported: `type`, `nullable`, `required`, `format`, `description`, `properties`, `items`, `enum`, `anyOf`, `$ref`, `$defs`. Other keywords are ignored.
  - Nesting depth is at most 32. Self-reference in defs goes at most 2 deep.
  - `enum` supports only non-empty strings.

### Limits
- At most **128 function declarations** per request (Vertex reference).
- Function names must start with a letter or `_`, use only `[a-zA-Z0-9_.-]`, and be at most 64 characters.
- Google's best-practices section says to keep the **active set at about 10–20 tools**. Beyond that, the model is more likely to pick the wrong tool, so use dynamic tool selection.

### tool_config modes
Set them with `types.ToolConfig(function_calling_config=types.FunctionCallingConfig(mode=..., allowed_function_names=[...]))`.

| Mode | What it does |
|---|---|
| `AUTO` (default) | The model chooses between text and a function call. |
| `ANY` | The model always returns one or more function calls. `allowed_function_names` limits which ones. |
| `NONE` | No function calls; same as sending no declarations. |
| `VALIDATED` | Function call or text, with schema adherence enforced. From Gemini 3 it also enforces required parameters. `allowed_function_names` works here too (SDK enum docstring). |

- The REST reference still says `allowed_function_names` is "only set when mode is ANY". The SDK and the guide also allow it with `VALIDATED`.
- `ANY` plus a `reply_to_user(text)` tool is a known way to force every turn through a tool, which makes it measurable.
- `stream_function_call_arguments=True` is in preview. The guide says it is not supported on 3.1 Flash-Lite.

### Parallel calls
- The model can return several `functionCall` parts in one turn, read from `response.function_calls`.
- Send back **all** `functionResponse` parts together in one `Content`, in the same order, with no interleaving. Interleaving gives a 400 error.
- Gemini 3+ matches responses by `id` first, then by name and order.
- The Gemini 3.5 Flash guide is stricter:
  - every `FunctionResponse` must carry the `id` and `name` of its `FunctionCall`;
  - send exactly one response per call;
  - a mismatch usually gives an **empty response with finish_reason STOP** (a silent failure).

### Multi-turn loop
1. Start with `contents = [user]`.
2. `r = generate_content(contents, config with tools)`.
3. If `r.function_calls` is empty, stop: the turn ends with text.
4. Otherwise append `r.candidates[0].content` **unchanged**. That object carries the thought signatures.
5. Run every call, then append one `Content` with all the function responses.
6. Repeat, with a cap on steps.

How to build the response part:
- **SDK gotcha:** in 2.34.0, `types.Part.from_function_response(name=, response=, parts=)` has **no `id` parameter**. Build it directly:
  `types.Part(function_response=types.FunctionResponse(id=call.id, name=call.name, response={...}))`.
- The SDK docs use `{'result': ...}` or `{'error': str(e)}` as the response dict.
- The docs use `role='tool'` for this content (other pages use `user`).
- Multimodal function responses (images, PDF, text) are in preview on Gemini 3+.
  - Put them in `FunctionResponse.parts`, never as separate user parts. The 3.5 guide says media outside the function response causes thought leakage and lower quality.
  - Instructions inside a function response go at the end of the response text, after two newlines.

### Thought signatures (Gemini 3 thinking models)
- **Required** when the response has `functionCall` parts. A missing signature in the current turn gives a 400 error, **even at `MINIMAL` thinking**.
- For parallel calls, only the first `functionCall` part carries a signature. For sequential steps, each step's first call does.
- A "turn" starts at the latest user message that is not a function response.
- The SDK handles signatures if you append `response.candidates[0].content` as is. Never rebuild, merge or trim those parts.
- When we store the conversation in Firestore between HTTP requests, we must keep the model `Content` exactly as returned. Serialize it with `model_dump(mode="json")` or the base64 signature bytes.
- `skip_thought_signature_validator` is a last resort only, and it hurts quality.
- The 3.5 guide: keep the whole history (thoughts, calls, responses) or drop all of it. Partial history degrades results.

### Thinking level and sampling (Gemini 3.x)
- Use `thinking_level` (`MINIMAL`, `LOW`, `MEDIUM`, `HIGH`) instead of `thinking_budget`. Sending both is a 400 error.
- A higher level means more tool exploration. Lowering it cuts unnecessary calls.
- `temperature`, `top_p` and `top_k` are deprecated or ignored on Gemini 3. Control behaviour with system instructions instead.
- The older Vertex best-practice text says to use temperature 0. That advice predates Gemini 3.

### Function calling together with response_json_schema
- The Vertex function-calling guide says function calling "can be combined with structured output so the model always produces either a function call or output that follows a specific schema."
- In practice there are community bug reports (Gemini 3 Pro ignoring the schema with a retrieval tool).
- The 3.5 guide warns that requiring structured JSON or XML text right before a tool call can cause `MALFORMED_FUNCTION_CALL`.
- **Recommendation:** do not mix them in the loop. Final text stays plain Ukrainian text. Structured buttons or cards come from tool results (server-side), not from a response schema.

---

## 2. Best practices for tool design

Sources:
- https://www.anthropic.com/engineering/writing-tools-for-agents
- The Vertex guide's "Best practices" and "Limitations" sections (above)

**Granularity**
- "Make sure each tool you build has a clear, distinct purpose." Consolidate multi-step work: one `schedule_event` instead of `list_users` + `list_events` + `create_event`.
- Do **not** wrap every API endpoint; overlapping tools distract the model.
- Google adds that generic tools get used often but inaccurately, while specific high-level tools are used precisely.

**Naming**
- Use namespacing prefixes such as `tasks_*`, `calendar_*`, `case_*`.
- Parameter names should be unambiguous: `task_id`, not `task`.

**Descriptions are prompts**
- Write each description "as if to a new hire". Say when to use the tool, when not to, and what it returns.
- Use `enum` for finite sets and `integer` rather than `number` for whole numbers.
- Put the current date, time and time zone into the system instruction when tools take dates.
- Tell the model to ask a clarifying question when the request is ambiguous.

**Results**
- Return high-signal, human-meaningful fields: titles, dates in words, case names, not raw IDs or whole API payloads.
- Keep IDs only where the next call needs them.
- Paginate, filter and truncate with sensible defaults. A `response_format` concise/detailed switch is optional.

**Errors**
- Errors must be actionable, not codes or tracebacks. Example: "Задачу не знайдено. Спершу виклич tasks_list і візьми task_id звідти."

**Destructive actions**
- Google: "For actions with significant consequences … confirm the call with the user before executing it."
- **Recommendation for this project:** the model should never perform a delete itself. The tool returns a proposal, the server renders a confirmation card, and the delete runs only on the user's tap or "так" on that card. This reuses the existing `reply_to` / fingerprint pattern in `assistant.py`. The model's "the user said yes" is not trusted on its own.

**How many tools**
- Google's guideline is about 10–20 active tools, out of a hard limit of 128.
- Fewer is better for Flash-Lite. Use `allowed_function_names` to narrow the set by context, for example only case tools when replying to a case card.

**Evaluation**
- Build realistic tasks grounded in real data, often needing several calls.
- Avoid brittle verifiers that reject valid alternatives.
- Keep a held-out set.
- Track tool-call counts, tokens, runtime and tool errors, not only accuracy.
- Here: replay the existing routing phrase corpus (the Ukrainian phrases already used for `ROUTE_SCHEMA` tests) as an eval of tool selection and arguments, run per model.

---

## 3. Google Tasks API v1 and Calendar API v3

Sources:
- https://developers.google.com/workspace/tasks/reference/rest/v1/tasks
- https://developers.google.com/workspace/tasks/reference/rest/v1/tasks/list
- https://developers.google.com/workspace/tasks/reference/rest/v1/tasks/delete
- https://developers.google.com/workspace/calendar/api/v3/reference/events/list
- https://developers.google.com/workspace/calendar/api/v3/reference/events/patch
- https://developers.google.com/workspace/calendar/api/v3/reference/events/delete

### Tasks
Endpoints use `/tasks/v1/lists/{tasklist}/tasks[/{task}]`. Our code uses `@default`.

**tasks.list parameters**
- `showCompleted`: default **true**. Completed tasks from Google's own clients also need `showHidden=true`.
- `showHidden`: default false.
- `showDeleted`: default false.
- `showAssigned`: default false.
- `dueMin`, `dueMax`, `completedMin`, `completedMax`, `updatedMin`: RFC 3339.
- `maxResults`: default **20**, max 100.
- `pageToken`: for paging.
- Scope: `tasks` or `tasks.readonly`.

**Task resource fields**
- `title`: up to 1024 characters.
- `notes`: up to 8192 characters.
- `due`: **date only; the time part is discarded**, so Tasks cannot hold a time. It is the day the task is scheduled, not a deadline.
- `status`: `needsAction` or `completed`. Setting `completed` is what `complete_task` does today.
- Read-only: `parent`, `position` (use `move` to change them), `webViewLink`, `links`.

**Other methods**
- `tasks.patch` and `tasks.update` change a task.
- `tasks.delete` returns an empty body and needs scope `tasks`. Deleting an assigned task (from Docs or Chat) also deletes the source item.

### Calendar
**events.list**
- `timeMin` is an exclusive bound on the event's end; `timeMax` is an exclusive bound on its start.
- `singleEvents=true` expands recurring events and is needed for `orderBy=startTime`.
- `q` does free-text search over summary, description, location and attendees.
- `maxResults`: default 250, max 2500.
- `showDeleted`, `timeZone`.

**events.patch**
- Omitted fields are kept; **arrays you include replace the whole array**.
- `sendUpdates`: `all`, `externalOnly` or `none`.
- Each patch costs 3 quota units. Google suggests `get` + `update` instead.
- Scopes: `calendar`, `calendar.events`, `calendar.app.created`, `calendar.events.owned`.

**events.delete**
- Empty response, takes `sendUpdates`, same scopes as patch.

### Scopes we already request (`src/mamamemory/config.py:9`)
`openid`, `userinfo.email`, `calendar.events`, `calendar.readonly`, `tasks`.

- `tasks` covers list, insert, patch, update and delete. **Nothing new is needed.**
- `calendar.events` covers events.list, patch and delete on all of the user's calendars. **Nothing new is needed.**
- `calendar.readonly` is already there for the time-zone setting.
- Narrower option (not required): `calendar.events.owned` or `calendar.app.created` would limit what the agent can touch. Only events the app created would be editable, which is a safety rail for an elderly user. The cost is that the model then cannot edit events she created herself. This is a product decision for the owner.

### Code gap
`src/mamamemory/integrations/google_work.py` today has these methods: `list_events`, `list_agenda`, `get_event`, `insert_event`, `list_open_tasks`, `insert_task`, `complete_task`.

Still missing: `patch_task`, `delete_task`, `patch_event`, `delete_event`, and a search or list of events by text (`q`).

---

## 4. Showing a stored file from a private GCS bucket in the PWA

Sources:
- https://docs.cloud.google.com/storage/docs/access-control/signed-urls
- https://docs.cloud.google.com/storage/docs/access-control/signing-urls-with-helpers
- https://docs.cloud.google.com/python/docs/reference/storage/latest/google.cloud.storage.blob.Blob

Objects are stored as `gs://{bucket}/{account_id}/{material_id}` with a mime (`integrations/files.py`). That module has only `put` today.

### Option A: V4 signed URL
- Call `blob.generate_signed_url(version="v4", expiration=timedelta(minutes=5), method="GET", service_account_email=<run SA>, access_token=<creds.token>, response_type=mime, response_disposition="inline")`.
- Without a key file, the library signs through IAM `signBlob`. This needs:
  - `roles/iam.serviceAccountTokenCreator` granted **on the runtime service account itself**;
  - the IAM Service Account Credentials API enabled;
  - `storage.objects.get` on the bucket.
- The Python reference still warns that you "can't generate a signed URL using GCE service account". That is about the default key-less signer; the `service_account_email` + `access_token` path is the workaround.
- Max lifetime 7 days, and **anyone holding the URL can read the object** until it expires.
- Pros: the bytes do not go through Cloud Run.
- Cons: an extra IAM grant (a provisioning step for the owner or Sonko, and an infra or ADR change); the URL is a bearer link that can leak through history, sharing or screenshots; needs bucket CORS only if fetched by JS (an `<img src>` or opening a tab does not need CORS).

### Option B: stream through an app endpoint
- `GET /files/{material_id}` checks the session cookie and that the material belongs to `session.account_id`, then streams the blob with the correct `Content-Type`, `Content-Disposition: inline` and `Cache-Control: private`.
- No new IAM: the service account already writes to the bucket and needs only read added if it lacks it.
- No bearer URLs, and the same auth as the rest of the app. Access stays tied to the signed-in account, which fits ADR-0001 ("data under signed-in account").
- Cost: the bytes go through Cloud Run. Uploads are capped at 20 MB (`max_upload_bytes`), under Cloud Run's 32 MiB non-streamed response limit. Use `StreamingResponse` anyway. Latency and egress are negligible at one user.

### Recommendation
Use **Option B**.
- The tool `case_show_material` returns a reply card with an app-relative link `/files/{material_id}`, plus the mime so the PWA can pick between `<img>`, a PDF viewer tab or text.
- The model never sees URLs; the server builds the link from `material_id`.
- Revisit signed URLs only if files get large or many.

---

## 5. Flash-Lite tool-calling quality and Ukrainian

Sources:
- https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/guides/gemini-3-5-flash
- The Vertex function-calling guide
- Third-party listings (OpenRouter, Vercel AI Gateway) that show `gemini-3.5-flash-lite` accepting tools and `tool_choice`. I found no Google page for this model.

**Model names are not confirmed by official docs**
- I found no official Google page for `gemini-3.5-flash-lite` or `gemini-3.8-flash`. The 3.5 guide names Gemini 3.5 Flash, 3.1 Flash-Lite (GA) and 3.1 Pro, and its migration section mentions 3.6 Flash.
- The project presumably runs on these models today, but their tool-calling quality is **not documented**. It must be measured with an eval.

**What Google says about Flash-Lite**
- Google positions it for "intent routing, data extraction, tagging and classification". That is today's single routing call, not multi-step agentic work.
- 3.1 Flash-Lite thinking defaults to `MINIMAL`.
- Streaming of function-call arguments is not supported on 3.1 Flash-Lite.

**Documented gotchas**
- Silent empty `STOP` when `id`, `name` or the count of function responses do not match.
- 400 when thought signatures are missing, even at `MINIMAL` thinking.
- `MALFORMED_FUNCTION_CALL` when structured text is forced right before a call.
- "Premature exits in multi-turn loops" and tool overuse: lower the thinking level or set a call budget in the system instruction.
- Do not end history with an empty user turn or a model turn.
- Accuracy falls as the tool count grows (about 10–20 active tools).
- A community report says Gemini 3 Flash preview gave inconsistent signatures on parallel calls (400). Treat it as unconfirmed.

**Ukrainian (no official data found)**
- Practical choices:
  - tool and parameter names in English snake_case;
  - descriptions in English, plus short Ukrainian example phrases ("видали задачу …", "перенеси зустріч …");
  - the system instruction requires replies to the user in Ukrainian, in short plain sentences.
- Pass dates as ISO strings and let the server parse them. Do not ask the model to output Ukrainian dates.
- Keep the existing `parse_when` and `parse_duration` helpers as server-side validators, or pass the model's ISO output through them.
- Measure on the existing Ukrainian phrase corpus before switching.
- Escalation options:
  - use Flash (`gemini-3.8-flash` here) for the agent loop and keep Flash-Lite for transcription-adjacent and simple calls;
  - or keep Flash-Lite as a fast first router and fall back to Flash when it returns no call or a malformed call.

---

## 6. RECOMMENDED DESIGN SKETCH (recommendation, not a decision)

### Tools
About 14, below Google's 10–20 guideline, and narrowed further by context. Names are English and namespaced. `id`s come only from earlier tool results. Every result is a short Ukrainian-ready summary plus the ids the next call needs.

| Tool | One-line description |
|---|---|
| `tasks_list(query?, include_done=false)` | Her open Google Tasks (title, day, task_id), optionally filtered by words; at most 20. |
| `tasks_add(title, day?)` | Add one task; `day` is ISO, date only (Tasks cannot hold a time). Replaces the `new_task` intent. |
| `tasks_edit(task_id, title?, notes?, day?, done?)` | Change or complete one task (`tasks.patch`). |
| `tasks_delete(task_id)` | **Proposes** deletion. Returns a confirmation card; nothing is deleted until she taps "Так". |
| `calendar_list(from, to, query?)` | Events in a range (`singleEvents=true`, `orderBy=startTime`, `q`), with title, start in her zone and event_id. |
| `calendar_edit(event_id, title?, start?, end?)` | **Proposes** a move or rename. Confirmation card, then `events.patch` with `sendUpdates=none`. |
| `calendar_delete(event_id)` | **Proposes** deletion. Confirmation card, then `events.delete`. |
| `plan_week()` / `plan_day()` | Existing planner (`plan_week` intent); the plan card already has its own "yes" flow. |
| `case_note(text, case_hint?)` | Existing note-to-case flow, including its "which case?" questions. |
| `case_recall(question, case_hint?)` | Existing `recall` / `answer_case`; returns an answer from the materials, with material ids. |
| `case_show_material(material_id)` | Shows a stored photo, PDF or note. Returns a card with an `/files/{material_id}` link and the mime. |
| `journal_working_on(text)` / `journal_ask(question)` | Existing `working_on` and `work_question` (work journal). |
| `help()` | Existing help text. |

No `reply` tool is needed if we use `AUTO`. With `ANY`, add `reply_to_user(text)` so every turn is a call.

### Loop shape
In `assistant.handle_message`, the tool loop replaces `_route_prompt`, `ROUTE_SCHEMA` and `_dispatch`.

1. **Keep the existing short-circuits before the loop:** a reply to a card (`reply_to`: yes, no, case_name, plan "yes", confirmation-card "Так") is handled deterministically with no model call, as today.
2. **Set up the call:**
   - `contents` = the system instruction (date, time, her time zone, rules: Ukrainian, short replies, ask when unclear, never claim a delete is done) plus her text.
   - `tools` = the subset for this context, via `allowed_function_names` when replying to a case card.
   - `tool_config` = `AUTO`, or `VALIDATED` if available, so required parameters are enforced.
   - `thinking_level` low or minimal.
   - Automatic function calling disabled.
   - No `response_json_schema`.
3. **Run the loop:**
   - Repeat up to **4 steps** and stop at the `call_timeout_s` / `request_timeout_s` deadline.
   - Each step calls `generate_content`.
   - If it returns no function calls, the text is the reply. Stop.
   - Otherwise append `candidates[0].content` unchanged.
   - Run each call through a registry `{name: handler(session, args, deps)}`. The account and session are injected and never come from the model.
   - Validate args (ISO dates go through the existing parsers; ids must belong to this account).
   - Append one `Content` of `Part(function_response=FunctionResponse(id=call.id, name=call.name, response={"result": …} | {"error": "…actionable…"}))`.
4. **Destructive or editing tools return a pending action**, stored in Firestore with a fingerprint: what exactly will change, the before and after shown in words.
   - The turn ends with a confirmation card (`Reply` with a `kind="confirm"` `reply_to`).
   - The real `tasks.delete`, `events.patch` or `events.delete` runs only in step 1 on her explicit tap or "так" reply to that card, and re-checks that the target has not changed.
   - The model never has an "execute delete" tool.
5. **Failure fallbacks:** if the loop hits the step cap, an empty `STOP`, `MALFORMED_FUNCTION_CALL` or a deadline, fall back to today's "Не зрозуміла — перепитаю" path. Log the turn for the eval.
6. **History:** one HTTP message is one model turn. Prior turns go in as plain text, user and assistant, and the stored history keeps no function-call parts. That keeps thought signatures within one request, so there is no signature persistence to get wrong.

### Rollout
1. Add the missing REST methods to `google_work.py` (`patch_task`, `delete_task`, `patch_event`, `delete_event`, a text search) and `Files.open` with the `/files/{id}` endpoint.
2. Build an eval of the Ukrainian phrase corpus mapped to the expected tool and args, and compare Flash-Lite with Flash.
3. Run the tool loop behind a flag, the same way as `use_tasks`, with the routing call as fallback.
4. Remove `ROUTE_SCHEMA` once the eval matches or beats it.

### Owner decisions to raise
- Allow editing and deleting calendar events she did not create through the app (scope `calendar.events`), or limit it to app-created events (`calendar.app.created`, or check `extendedProperties` / the event-id prefix in code).
- Which model runs the loop: Flash-Lite or Flash. This is a cost and quality trade-off, measured by the eval.
