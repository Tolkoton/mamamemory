"""Contract tests of the slice guide: `assistant.guide_text`, the guide on the first open
(`assistant.open_questions` and `settings/guide_shown`), the intent `help`, the new `CANNOT_TEXT`;
Seam 1-3, I1.

Written by the slice tester from the sealed contract `.engine/slices/guide.md`, without the code.
`NOW` is Monday 9 November 2026, 10:07 Berlin (09:07Z). Every text is written by hand from the contract.
"""

from datetime import timedelta

import requests

from mamamemory import assistant
from mamamemory.errors import LoginExpired
from mamamemory.replies import Question, Reply
from tests.case_questions_world import case_q
from tests.clarify_world import clarified
from tests.guide_world import (
    GUIDE,
    GUIDE_PATH,
    NEW_CANNOT,
    SHOWN_BEFORE,
    Guide,
    flag_writes,
    guide_reply,
    guides,
    is_guide,
    plain,
)
from tests.note_to_case_world import ask
from tests.test_one_task_planning import NOW, shown

SCHMIDT = "пані Шмідт"
FISCHER = "пан Фішер"
MINUTE = timedelta(minutes=1)
HOUR = timedelta(hours=1)
WEEK = timedelta(days=7)


def with_sign_in_and_case() -> Guide:
    """A pending note «a1» an hour before NOW and a shown plan. Since calm-open the open shows nothing of the
    plan: even with LoginExpired it gives only the case question (no «увійди знову», `login_needed` False)."""
    g = Guide()
    g.pending_note("a1", SCHMIDT, NOW - HOUR)
    shown(g.plan.start())
    return g


# ------------------------------------------------------------------ guide_text


def test_guide_text_is_the_contract_text_for_uk_and_the_same_for_another_language() -> None:
    assert plain(assistant.guide_text("uk")) == GUIDE
    for language in ("en", "de", "xx"):
        assert assistant.guide_text(language) == assistant.guide_text("uk"), language


# ------------------------------------------------------------------ Seam 1: the first open


def test_seam1_first_open_without_the_flag_is_the_guide_alone_and_writes_the_flag() -> None:
    g = Guide()
    result = g.open(NOW)
    assert len(result.replies) == 1, result.replies
    guide_reply(result.replies[0])
    assert "guide" not in result.failed
    assert result.login_needed is False
    flag = g.flag()
    assert flag is not None and "shown" in flag, flag


def test_seam1_guide_stands_before_every_item_and_the_question_stays_last() -> None:
    g = with_sign_in_and_case()
    result = g.open(NOW + MINUTE, LoginExpired())
    assert len(result.replies) == 2, result.replies
    guide_reply(result.replies[0])
    assert result.replies[1:] == [Reply(ask(SCHMIDT), case_q("a1"))]
    assert result.login_needed is False
    # A shown plan alone (calm-open): the open is the guide alone, no plan and no plan question.
    p = Guide()
    shown(p.plan.start())
    opened = p.open(NOW + MINUTE)
    assert len(opened.replies) == 1, opened.replies
    guide_reply(opened.replies[0])
    assert opened.login_needed is False


def test_seam1_second_open_has_no_guide_and_the_items_as_before() -> None:
    g = with_sign_in_and_case()
    first = g.open(NOW + MINUTE, LoginExpired())
    assert guides(first.replies) == 1, first.replies
    second = g.open(NOW + HOUR, LoginExpired())
    assert second.replies == [Reply(ask(SCHMIDT), case_q("a1"))]
    assert second.login_needed is False
    assert "guide" not in second.failed
    empty = Guide()
    assert guides(empty.open(NOW).replies) == 1
    assert empty.open(NOW + MINUTE).replies == []


def test_seam1_with_the_accounts_flag_there_is_no_guide_and_the_flag_is_kept() -> None:
    g = with_sign_in_and_case()
    g.mark_shown()
    result = g.open(NOW + MINUTE, LoginExpired())
    assert result.replies == [Reply(ask(SCHMIDT), case_q("a1"))]
    assert "guide" not in result.failed
    assert g.flag() == SHOWN_BEFORE
    # The flag is the account's: another account over the same store has none and gets its guide.
    assert guides(g.other_account().open(NOW + MINUTE).replies) == 1


def test_seam1_the_flag_is_read_before_the_other_sources() -> None:
    g = with_sign_in_and_case()
    g.store.log.clear()
    g.open(NOW + MINUTE, LoginExpired())
    paths = [path for _, _, path in g.store.log]
    assert GUIDE_PATH in paths, g.store.log
    others = [i for i, path in enumerate(paths) if path not in (GUIDE_PATH, "settings/profile")]
    assert others, g.store.log
    assert paths.index(GUIDE_PATH) < others[0], g.store.log


def test_seam1_flag_read_failure_shows_no_guide_keeps_the_items_and_names_guide_in_failed() -> None:
    g = with_sign_in_and_case()
    g.store.fail_read = True
    result = g.open(NOW + MINUTE, LoginExpired())
    assert result.replies == [Reply(ask(SCHMIDT), case_q("a1"))]
    assert "guide" in result.failed
    assert result.login_needed is False
    empty = Guide()
    empty.store.fail_read = True
    alone = empty.open(NOW)
    assert alone.replies == []
    assert "guide" in alone.failed


def test_seam1_flag_write_failure_shows_the_guide_and_the_next_open_shows_it_again() -> None:
    g = with_sign_in_and_case()
    g.store.fail_write = True
    first = g.open(NOW + MINUTE, LoginExpired())
    assert len(first.replies) == 2, first.replies
    guide_reply(first.replies[0])
    assert first.replies[1:] == [Reply(ask(SCHMIDT), case_q("a1"))]
    assert "guide" in first.failed
    assert g.flag() is None
    g.store.fail_write = False
    second = g.open(NOW + HOUR, LoginExpired())
    assert len(second.replies) == 2, second.replies
    guide_reply(second.replies[0])
    assert second.replies[1:] == [Reply(ask(SCHMIDT), case_q("a1"))]
    assert "guide" not in second.failed
    third = g.open(NOW + 2 * HOUR, LoginExpired())
    assert third.replies == [Reply(ask(SCHMIDT), case_q("a1"))]


def test_seam1_each_account_has_its_own_guide() -> None:
    a = Guide()
    b = a.other_account()
    assert guides(a.open(NOW).replies) == 1
    assert b.flag() is None
    assert guides(b.open(NOW + MINUTE).replies) == 1
    assert a.open(NOW + HOUR).replies == []
    assert b.open(NOW + HOUR).replies == []


# ------------------------------------------------------------------ Seam 2: «що ти вмієш?»


def test_seam2_help_answers_the_guide_writes_no_flag_and_changes_nothing() -> None:
    g = Guide()
    g.pending_note("a1", SCHMIDT, NOW - HOUR)
    shown(g.plan.start())
    before = g.everything_else()
    inserts = list(g.calendar.insert_calls)
    g.store.log.clear()
    reply = g.help("що ти вмієш?", "h1")
    guide_reply(reply)
    assert flag_writes(g.store, g.session.account_id) == [], g.store.log
    assert g.flag() is None
    assert g.everything_else() == before
    assert g.calendar.insert_calls == inserts
    # The flag was not written: the next open still shows the guide.
    assert guides(g.open(NOW + MINUTE).replies) == 1


def test_seam2_help_under_a_case_question_or_a_plan_question_is_the_guide_too() -> None:
    g = Guide()
    g.pending_note("a1", SCHMIDT, NOW - HOUR)
    plan_id, fingerprint = shown(g.plan.start())
    before = g.everything_else()
    inserts = list(g.calendar.insert_calls)
    guide_reply(g.help("як з тобою працювати?", "h1", case_q("a1")))
    guide_reply(g.help("допоможи", "h2", Question("plan", plan_id, fingerprint)))
    assert g.everything_else() == before
    assert g.calendar.insert_calls == inserts
    assert g.flag() is None


def test_seam2_route_offers_help_under_every_reply_to() -> None:
    reply_tos: list[Question | None] = [
        None,
        Question("duration", "p1", None),
        Question("plan", "p1", "fp"),
        Question("limits", "p1", None),
        Question("priorities", "p1", None),
        case_q("a1"),
        Question("clarify", "c1", None),
    ]
    for reply_to in reply_tos:
        enum = assistant.route_schema(reply_to)["properties"]["intent"]["enum"]
        assert "help" in enum, (reply_to, enum)
    g = Guide()
    g.pending_note("a1", SCHMIDT, NOW - HOUR)
    for n, reply_to in enumerate([None, case_q("a1")]):
        g.ai.plain_intent("other")
        g.say("щось", f"o{n}", reply_to)
        assert g.ai.route_schemas, "the route model was not asked"
        assert "help" in g.ai.route_schemas[-1]["properties"]["intent"]["enum"], reply_to
        assert "help" in g.ai.prompts["route"][-1], reply_to


def test_seam2_help_is_no_option_of_a_clarification() -> None:
    g = Guide()
    g.ai.unsure("help", "note")
    reply = g.say("що ти вмієш, запиши", "u1")
    assert reply.question is None or reply.question.kind != "clarify", reply
    assert g.current() is None
    assert reply == Reply(NEW_CANNOT)
    # Two lawful options are still a clarification: the refusal above was for `help`.
    g.ai.unsure("note", "new_task")
    clarified(g.say("що ти вмієш, запиши", "u2"))


# ------------------------------------------------------------------ Seam 3: not understood


def test_seam3_other_answers_the_new_text() -> None:
    assert assistant.CANNOT_TEXT == NEW_CANNOT
    g = Guide()
    before = g.everything_else()
    g.ai.plain_intent("other")
    reply = g.say("бла-бла", "o1")
    assert reply == Reply(NEW_CANNOT)
    assert not is_guide(reply)
    assert g.everything_else() == before


# ------------------------------------------------------------------ I1


def test_I1_guide_once_without_the_flag_never_with_it_and_never_in_the_question_place() -> None:
    """Every open sequence of three opens over plan states, case questions and failures of their sources."""
    plan_kinds = ("none", "asking", "shown", "no_free_time", "sign_in")
    # The failure of the plan or the case source on each of the three opens; a lawful open after a failed one.
    failure_runs: list[tuple[str | None, ...]] = [
        (None, None, None),
        ("plan", None, None),
        ("cases", "plan", None),
        ("plan", "cases", "plan"),
    ]
    for kind in plan_kinds:
        for count in (0, 1, 2):
            for failures in failure_runs:
                for flagged in (False, True):
                    g = Guide()
                    for i in range(count):
                        g.pending_note(f"n{i}", f"справа {i}", NOW - HOUR + i * MINUTE)
                    if kind == "asking":
                        g.ai.task["duration_min"] = None
                    if kind != "none":
                        g.plan.start()
                    if kind == "no_free_time":
                        g.calendar.busy(NOW - HOUR, NOW + WEEK + HOUR)
                    if flagged:
                        g.mark_shown()
                    seen = 0
                    for step, failure in enumerate(failures):
                        raises: BaseException | None = LoginExpired() if kind == "sign_in" else None
                        if failure == "plan":
                            raises = requests.HTTPError("fake: 500 Backend Error")
                        g.store.broken = failure == "cases"
                        label = (kind, count, failures, flagged, step)
                        result = g.open(NOW + (step + 1) * HOUR, raises)
                        here = guides(result.replies)
                        assert here <= 1, (label, result.replies)
                        if here:
                            assert is_guide(result.replies[0]), (label, result.replies)
                        seen += here
                        asked = [r for r in result.replies if r.question is not None]
                        if asked:
                            last = result.replies[-1]
                            assert last.question is not None, (label, result.replies)
                            assert not is_guide(last), (label, result.replies)
                        g.store.broken = False
                    expected = 0 if flagged else 1
                    assert seen == expected, (kind, count, failures, flagged, seen)
                    if flagged:
                        assert g.flag() == SHOWN_BEFORE, (kind, count, failures)
    # The same with «що ти вмієш?» between the opens: help adds no automatic guide and takes none away.
    g = Guide()
    g.pending_note("a1", SCHMIDT, NOW - HOUR)
    seen = 0
    for step in range(3):
        g.help("що ти вмієш?", f"h{step}")
        result = g.open(NOW + (step + 1) * HOUR)
        seen += guides(result.replies)
        assert result.replies[-1].question == case_q("a1"), result.replies
    assert seen == 1
    assert g.flag() is not None
