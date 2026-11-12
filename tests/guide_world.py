"""Test helpers of the slice guide: a store that logs every access and can fail the read or the write of
`settings/guide_shown`, a model fake that records the route's schema, and a world around
`assistant.open_questions` and `assistant.handle_message` over plan and case questions.

Written by the slice tester from the sealed contract `.engine/slices/guide.md`, without the code.
`NOW` is Monday 9 November 2026, 10:07 Berlin (09:07Z). Every text is written by hand from the contract.
The contract does not fix the apostrophe's typography nor whitespace around the guide (question Q1 of this
slice): `is_guide` reads the text with its apostrophes made one character and its ends stripped.
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from mamamemory import assistant
from mamamemory.access import Session
from mamamemory.config import Config
from mamamemory.integrations.google_work import GoogleWork
from mamamemory.integrations.store import Decide
from mamamemory.replies import Reply
from tests.case_questions_world import BrokenStore, Lazy
from tests.clarify_world import Clarify, ClarifyCaseAI
from tests.note_to_case_world import Clock
from tests.test_one_task_planning import FakeCalendar, make_config, make_session

GUIDE_PATH = "settings/guide_shown"
GUIDE = (
    "Я допомагаю планувати й пам'ятати справи. Що можна сказати:\n"
    "• «Додай задачу подзвонити нотаріусу в понеділок» — поставлю в календар.\n"
    "• «Сплануй тиждень» — складу план з усіх задач.\n"
    "• «Запиши до пані Шмідт: …», або 📷 чи ＋ — покладу у справу.\n"
    "• «Переклади … до …» — перенесу в іншу справу.\n"
    "• 🔊 біля відповіді — прочитаю вголос.\n"
    "Не зрозумію — перепитаю."
)
NEW_CANNOT = "Не зрозуміла. Скажіть «що ти вмієш?» — розкажу."
SIGN_IN_AGAIN = "Щоб показати план, увійди знову."
SHOWN_BEFORE = {"shown": "2026-11-01T09:00:00+00:00"}


def plain(text: str) -> str:
    """Apostrophes made one character, the ends stripped: the contract does not fix the typography."""
    return text.replace("ʼ", "'").replace("’", "'").strip()


def is_guide(reply: Reply) -> bool:
    return plain(reply.text) == GUIDE


def guide_reply(reply: Reply) -> None:
    """`Reply(guide_text(…))`: the guide's text, no question, no plan, no choices."""
    assert is_guide(reply), reply
    assert reply.question is None, reply
    assert reply.plan is None, reply
    assert reply.choices is None, reply


class FlagBroken(Exception):
    """What `GuideStore` raises on the flag while it is told to fail."""


class GuideStore(BrokenStore):
    """`BrokenStore` that logs every access as (operation, path) and fails the flag's read or write.

    `fail_read`: `get` of the flag raises (and `transact` on it, which reads first). `fail_write`: `set` and
    `transact` of the flag raise; nothing is stored."""

    def __init__(self) -> None:
        super().__init__()
        self.log: list[tuple[str, str, str]] = []  # (account, operation, path)
        self.fail_read = False
        self.fail_write = False

    def get(self, account_id: str, path: str) -> dict[str, Any] | None:
        self.log.append((account_id, "get", path))
        if path == GUIDE_PATH and self.fail_read:
            raise FlagBroken("read")
        return super().get(account_id, path)

    def set(self, account_id: str, path: str, data: dict[str, Any]) -> None:
        self.log.append((account_id, "set", path))
        if path == GUIDE_PATH and self.fail_write:
            raise FlagBroken("write")
        super().set(account_id, path, data)

    def transact(self, account_id: str, path: str, decide: Decide) -> dict[str, Any] | None:
        self.log.append((account_id, "transact", path))
        if path == GUIDE_PATH and (self.fail_read or self.fail_write):
            raise FlagBroken("transact")
        return super().transact(account_id, path, decide)

    def delete(self, account_id: str, path: str) -> None:
        self.log.append((account_id, "delete", path))
        super().delete(account_id, path)

    def list(self, account_id: str, collection: str) -> list[tuple[str, dict[str, Any]]]:
        self.log.append((account_id, "list", collection))
        return super().list(account_id, collection)


def flag_writes(store: GuideStore, account_id: str) -> list[str]:
    """Every write of the flag (`set`, `transact`, `delete`) the store saw for the account."""
    return [op for acc, op, path in store.log if acc == account_id and path == GUIDE_PATH and op != "get"]


class GuideAI(ClarifyCaseAI):
    """The clarify fake that also records the schema of every route call."""

    def __init__(self) -> None:
        super().__init__()
        self.route_schemas: list[dict[str, Any]] = []

    def _answer(self, task_type: str, prompt: str, schema: dict[str, Any]) -> dict[str, Any]:
        if task_type == "route":
            self.route_schemas.append(schema)
        return super()._answer(task_type, prompt, schema)


@dataclass
class Guide(Clarify):
    ai: GuideAI = field(default_factory=GuideAI)
    store: GuideStore = field(default_factory=GuideStore)
    config: Config = field(default_factory=make_config)
    session: Session = field(default_factory=make_session)
    clock: Clock = field(default_factory=Clock)
    calendar: FakeCalendar = field(default_factory=FakeCalendar)

    def other_account(self, account_id: str = "acc-2") -> "Guide":
        """A second account over the same store, model and calendar."""
        return Guide(
            ai=self.ai,
            store=self.store,
            config=self.config,
            session=make_session(account_id),
            clock=self.clock,
            calendar=self.calendar,
        )

    def open(
        self,
        now: datetime,
        raises: BaseException | None = None,
        *,
        calendar: Callable[[], GoogleWork] | None = None,
    ) -> assistant.OpenQuestions:
        lazy = calendar if calendar is not None else Lazy(self.calendar, raises)
        return assistant.open_questions(
            self.session, calendar=lazy, store=self.store, now=now, config=self.config
        )

    def flag(self) -> dict[str, Any] | None:
        return BrokenStore.get(self.store, self.session.account_id, GUIDE_PATH)

    def mark_shown(self) -> None:
        BrokenStore.set(self.store, self.session.account_id, GUIDE_PATH, dict(SHOWN_BEFORE))

    def help(self, text: str, message_id: str, reply_to: Any = None, now: datetime | None = None) -> Reply:
        self.ai.plain_intent("help")
        if now is None:
            return self.say(text, message_id, reply_to)
        return self.say(text, message_id, reply_to, now)


def guides(replies: list[Reply]) -> int:
    return sum(1 for r in replies if is_guide(r))
