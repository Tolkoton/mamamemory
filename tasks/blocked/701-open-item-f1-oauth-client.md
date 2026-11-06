# 701 — Клієнт входу Google і мамина адреса для каркаса

Залежить від: —
Аудит потрібен: ні
Відкритий пункт: f1-oauth-client

## Що сталося
Код першого кроку F1 (вхід, оболонка) готовий: 41 тест зелений. Розгортання й smoke чекають на дві речі, які можна зробити лише вручну: (1) клієнт OAuth у Google Cloud Console — Google не дає створити його з командного рядка для проєкту без організації (звіт Сонька ~/sonko/done/2026-11-05-mamamemory-f1-provisioning.md, п. 6); (2) мамина Gmail-адреса — для списку дозволених і для Test users екрана входу. Кроки в консолі: APIs & Services → Credentials → Create Credentials → OAuth client ID, проєкт pocket-lawyer-431614, тип Web application, назва mamamemory; Authorized JavaScript origin https://mamamemory-2mfebgg56q-ey.a.run.app; Authorized redirect URI https://mamamemory-2mfebgg56q-ey.a.run.app/auth/callback; OAuth consent screen → Test users → додати мамину адресу. Client ID і Client Secret передати Сонькові (секрет — у mamamemory-oauth-client-secret).

- Записано: 2026-11-05T22:04:56Z, агент

## Що зробити
Це питання до власника, не робота для агента. Коли власник відповість, задача повернеться в чергу: виконай відповідь, запиши її у звіт і закрий задачу.

## Готово, коли
Власник відповів, і відповідь виконано.

## Питання до власника
1. Створіть, будь ласка, клієнт OAuth (кроки вище) і напишіть мамину Gmail-адресу — тоді Сонько розгорне каркас і прожене smoke.
   Відповідь:
