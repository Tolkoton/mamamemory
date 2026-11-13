# Supersede package — add-or-plan, changed by the sealed contract show-schedule (owner's word 2026-11-12: «спитав, які в нас сьогодні плани на поточний тиждень. І він видав мені якісь дві рандомні таски… ця логіка взагалі не працює»)

show-schedule Seam: «підказка маршрутизації: «schedule — мама питає, що в неї вже заплановано («які плани на
сьогодні?», «що в мене на тиждень?», «що в мене завтра?»); plan_week — лише коли просить спланувати («сплануй
тиждень», «давай планувати»)»; зі старого опису `plan_week` прибрати «що в мене на тиждень».»

- `tests/test_add_or_plan_disputed.py::test_Q2_route_prompt_carries_the_contract_hints_in_their_words` — тримає старий
  опис «plan_week — мама просить спланувати тиждень чи дні …» з «що в мене на тиждень». Переписати на новий опис
  `plan_week` (show-schedule Seam); решта підказок add-or-plan — як були.

Requested: rewrite each listed test to the new contract; `uv run pytest -q` green, except the clarify `allowed()` test,
which waits for its own package.
