# 708 — Брак тесту (overseer): voice_state_contract: after {type:'assistant_reply', reply:{question:{kind:'duration',id:'q1',fingerprint:null}}} then MIC, SEND, transcribed 200, SEND, the send_message action carries reply_to {kind:

Залежить від: —
Аудит потрібен: ні
Відкритий пункт: test-gap-voice-state-contract-after-type-assistant-reply-reply-questi-700f3284

## Що сталося
Overseer прийняв юніт `-|-|unit 1` (PASS, запит `20261106T075957Z-a62406`) і знайшов брак тесту: a voice_state that ignores assistant_reply, or keeps the first replyTo forever, sends mama's spoken answer to the duration question with the wrong reply_to. All 8 node tests still pass because every sequence starts from initial(replyTo) (tester's Q5, left untested) Де: `src/mamamemory/web/voice_state_contract.test.js`. Вердикт — у ledger: `python3 .claude/hooks/journal.py show ledger`.

- Записано: 2026-11-06T08:01:49Z, overseer (overseer_verdict.py)
- Це пропозиція, а не задача в черзі: runner із `tasks/proposed/` нічого не бере. У роботу її ставить власник — файлом із цим номером в inbox.

## Що зробити
Дописати перевірку «voice_state_contract: after {type:'assistant_reply', reply:{question:{kind:'duration',id:'q1',fingerprint:null}}} then MIC, SEND, transcribed 200, SEND, the send_message action carries reply_to {kind:'duration',id:'q1',fingerprint:null}; after a reply whose question is null it carries null»: тест червоніє на тому, що описано вище (a voice_state that ignores assistant_reply, or keeps the first replyTo forever, sends mama's spoken answer to the duration question with the wrong reply_to. All 8 node tests still pass because every sequence starts from initial(replyTo) (tester's Q5, left untested)), і зелений на коді, як він є (покажи обидва прогони); код не міняти, якщо тест не знайде справжньої вади; швидкий набір тестів зелений.

## Готово, коли
Описане вище зроблено і перевірено, або на нього є відповідь власника.

## Питання до власника
