"""Contract tests of the route of the slice photo-and-file: `POST /api/upload`.

Seam 1 (break and repeat), Seam 2 (types and size), Seam 4 (separate accounts), I2, the log line (C1).
Written by the slice tester from the sealed contract `.engine/slices/photo-and-file.md`, without the code.
The body is the file itself; the repeat after «Не вдалося…» is an empty body with no `Content-Type` and the
same `X-Material-Id` (`UploadApp.header_only`). The app's clock is the clock the route passes on; the fake
`Files` and the model fake move it, to stand on either side of the deadline.
"""

import dataclasses
import uuid
from datetime import timedelta

import pytest

from mamamemory import cases
from tests.note_to_case_world import FAILED, ask, placed
from tests.photo_and_file_world import (
    ALLOWED,
    BUCKET,
    EMPTY,
    NOT_READ,
    PDF,
    PNG,
    READ_TEXT,
    SUB_2,
    TOO_BIG_20,
    UploadApp,
)
from tests.test_one_task_http import SUB
from tests.test_one_task_planning import NOW, make_config

SCHMIDT = "пані Шмідт"
KOCH = "пан Кох"
DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


def with_cases() -> UploadApp:
    """An app whose account has «пан Кох» and «пані Шмідт»; the Розкладач names «пані Шмідт»."""
    app = UploadApp()
    app.seed(KOCH, "k0")
    app.seed(SCHMIDT, "m0")
    app.ai.file_to(SCHMIDT)
    return app


def file_materials(app: UploadApp, sub: str = SUB) -> list[cases.Material]:
    return [m for m in app.materials(sub) if m.kind in ("photo", "file")]


def nothing_happened(app: UploadApp) -> None:
    assert file_materials(app) == []
    assert app.files.puts == []
    assert app.files.objects == {}
    assert app.ai.calls == []
    assert app.ai.file_calls == []


# ------------------------------------------------------------------ the route and its reply


def test_upload_valid_id_names_the_material_and_the_reply_asks_like_any_other() -> None:
    app = UploadApp()
    app.seed(KOCH, "k0")
    app.ai.new_case(SCHMIDT)
    reply = app.upload(PNG, "image/png", "up-1")
    assert reply["text"] == ask(SCHMIDT)
    assert reply["question"] == {"kind": "case", "id": "up-1", "fingerprint": None}
    material = [m for m in app.materials() if m.material_id == "up-1"]
    assert len(material) == 1 and material[0].kind == "photo"
    assert material[0].gs_uri == f"gs://{BUCKET}/{SUB}/up-1"
    assert app.files.objects[(SUB, "up-1")] == (PNG, "image/png")
    assert app.confirm("up-1")["text"] == placed(SCHMIDT)


def test_upload_placed_into_a_known_case_answers_placed() -> None:
    app = with_cases()
    reply = app.upload(PDF, "application/pdf", "up-1")
    assert reply["text"] == placed(SCHMIDT)
    assert app.ai.file_calls == [("read_file", f"gs://{BUCKET}/{SUB}/up-1", "application/pdf")]


def test_upload_id_outside_the_pattern_or_missing_gets_a_new_uuid() -> None:
    app = with_cases()
    good = "a" * 59
    app.upload(PNG, "image/png", good)
    assert [m.material_id for m in file_materials(app)] == [good]
    for number, bad in enumerate([None, "", "a" * 60, "../x", "a/b", "a.b", "a b"], start=1):
        app.upload(PNG, "image/png", bad)
        ids = [m.material_id for m in file_materials(app)]
        assert len(ids) == number + 1, (bad, ids)
        fresh = [i for i in ids if i != good]
        assert bad not in fresh
        for material_id in fresh:
            uuid.UUID(material_id)
    assert len({m.material_id for m in file_materials(app)}) == 8


# ------------------------------------------------------------------ types and size (Seam 2)


def test_every_allowed_type_is_accepted_also_with_parameters_and_in_upper_case() -> None:
    app = with_cases()
    number = 0
    for mime in ALLOWED:
        for given in (mime, mime.upper(), f"{mime}; charset=utf-8", f"{mime.upper()};name=x"):
            number += 1
            reply = app.upload(b"HbA1c 7,2", given, f"t{number}")
            assert reply["text"] == placed(SCHMIDT), (given, reply)
            assert len(file_materials(app)) == number, given


@pytest.mark.parametrize("content_type", [DOCX, "image/gif", "application/octet-stream", None])
def test_a_type_outside_the_list_is_refused_in_words_without_writing(content_type: str | None) -> None:
    app = with_cases()
    reply = app.upload(PNG, content_type, "up-1")
    assert reply["text"] == NOT_READ
    nothing_happened(app)


def test_an_empty_body_with_a_type_is_refused_as_empty_without_writing() -> None:
    app = with_cases()
    reply = app.upload(b"", "image/png", "up-1")
    assert reply["text"] == EMPTY
    nothing_happened(app)


def test_exactly_max_upload_bytes_is_accepted_and_one_byte_more_is_too_big() -> None:
    app = with_cases()
    limit = 20 * 1024 * 1024
    assert app.config.max_upload_bytes == limit
    over = app.upload(b"x" * (limit + 1), "image/png", "big")
    assert over["text"] == TOO_BIG_20
    nothing_happened(app)
    exact = app.upload(b"x" * limit, "image/png", "fits")
    assert exact["text"] == placed(SCHMIDT)
    assert app.files.puts == [(SUB, "fits")]


def test_the_too_big_text_takes_its_number_from_max_upload_bytes() -> None:
    app = UploadApp(dataclasses.replace(make_config(), max_upload_bytes=5 * 1024 * 1024))
    reply = app.upload(b"x" * (5 * 1024 * 1024 + 1), "application/pdf", "big")
    assert reply["text"] == "Файл завеликий — до 5 MB."
    nothing_happened(app)


# ------------------------------------------------------------------ break and repeat (Seam 1)


def test_header_only_repeat_without_a_type_finishes_an_existing_material() -> None:
    app = with_cases()
    app.ai.fail["read_file"] = 1
    assert app.upload(PNG, "image/png", "up-1")["text"] == FAILED
    app.later()
    assert app.header_only("up-1")["text"] == placed(SCHMIDT)
    assert app.files.puts == [(SUB, "up-1")]
    assert [c[0] for c in app.ai.file_calls] == ["read_file", "read_file"]
    assert [m.state for m in file_materials(app)] == ["placed"]


def test_header_only_repeat_for_an_unknown_id_fails_and_writes_nothing() -> None:
    app = with_cases()
    assert app.header_only("up-9")["text"] == FAILED
    nothing_happened(app)


def test_files_failure_answers_failed_and_the_header_only_repeat_writes_and_reads_nothing() -> None:
    app = with_cases()
    app.files.fail = 1
    assert app.upload(PNG, "image/png", "up-1")["text"] == FAILED
    assert file_materials(app) == []
    assert app.ai.file_calls == []
    app.later()
    assert app.header_only("up-1")["text"] == FAILED
    assert file_materials(app) == []
    assert app.ai.file_calls == []
    assert app.files.objects == {}


@pytest.mark.parametrize(("moved_s", "finished"), [(9, True), (11, False)])
def test_upload_deadline_is_request_timeout_less_two_call_timeouts(moved_s: int, finished: bool) -> None:
    # request_timeout_s = 30, call_timeout_s = 10: the deadline is 10 s after the request began.
    app = with_cases()

    def move() -> None:
        app.clock.at = NOW + timedelta(seconds=moved_s)

    app.files.after_put = move
    reply = app.upload(PNG, "image/png", "up-1")
    if finished:
        assert reply["text"] == placed(SCHMIDT)
        assert len(app.ai.file_calls) == 1
    else:
        assert reply["text"] == FAILED
        assert app.ai.file_calls == []


def test_slow_body_leaves_a_new_unread_material_and_the_header_repeat_reads_without_a_new_put() -> None:
    app = with_cases()

    def slow() -> None:
        app.clock.at = NOW + timedelta(seconds=11)

    app.files.after_put = slow
    assert app.upload(PNG, "image/png", "up-1")["text"] == FAILED
    [material] = file_materials(app)
    assert (material.material_id, material.state, material.text) == ("up-1", "new", "")
    app.later()
    assert app.header_only("up-1")["text"] == placed(SCHMIDT)
    assert app.files.puts == [(SUB, "up-1")]
    assert [m.text for m in file_materials(app)] == [READ_TEXT]


def test_a_note_id_as_material_id_puts_the_file_under_the_derived_id() -> None:
    app = with_cases()
    app.world.notes.add("запиши до пані Шмідт: тиск 130/80", "n1")
    note = [m for m in app.materials() if m.material_id == "n1"][0]
    app.ai.fail["read_file"] = 1
    assert app.upload(PNG, "image/png", "n1")["text"] == FAILED
    app.later()
    assert app.header_only("n1")["text"] == placed(SCHMIDT)
    app.later(200)
    assert app.upload(PNG, "image/png", "n1")["text"] == placed(SCHMIDT)
    assert [m.material_id for m in file_materials(app)] == ["n1-file"]
    assert set(app.files.puts) == {(SUB, "n1-file")}
    assert list(app.files.objects) == [(SUB, "n1-file")]
    after = [m for m in app.materials() if m.material_id == "n1"][0]
    assert (after.kind, after.text, after.state, after.case_id) == (
        note.kind,
        note.text,
        note.state,
        note.case_id,
    )


# ------------------------------------------------------------------ separate accounts (Seam 4)


def test_the_same_material_id_of_two_accounts_is_two_objects_and_two_materials() -> None:
    app = with_cases()
    app.upload(PNG, "image/png", "up-1")
    app.sign_in(SUB_2)
    app.ai.new_case(SCHMIDT)
    app.upload(PDF, "application/pdf", "up-1")
    assert app.files.objects == {(SUB, "up-1"): (PNG, "image/png"), (SUB_2, "up-1"): (PDF, "application/pdf")}
    [first] = file_materials(app, SUB)
    [second] = file_materials(app, SUB_2)
    assert (first.gs_uri, first.mime) == (f"gs://{BUCKET}/{SUB}/up-1", "image/png")
    assert (second.gs_uri, second.mime) == (f"gs://{BUCKET}/{SUB_2}/up-1", "application/pdf")


# ------------------------------------------------------------------ the log (C1)


def test_log_lines_carry_no_file_content_no_text_from_it_and_no_case_name(
    capfd: pytest.CaptureFixture[str],
) -> None:
    app = with_cases()
    capfd.readouterr()
    app.ai.read_text = "Секретний аналіз: HbA1c 7,2"
    app.ai.fail["read_file"] = 1
    app.upload(b"vmist-faylu-photo", "image/png", "up-1")
    app.later()
    app.ai.fail["classify_case"] = 1
    app.header_only("up-1")
    app.later(200)
    app.ai.fail["describe_case"] = 1
    app.header_only("up-1")
    app.later(300)
    app.files.fail = 1
    app.upload("Таємний вміст тексту".encode(), "text/plain", "up-2")
    out = capfd.readouterr()
    for line in (out.out + out.err).splitlines():
        for secret in ("vmist-faylu", "Секретний", "HbA1c", "Таємний", "Шмідт"):
            assert secret not in line, f"the log line carries {secret!r}: {line}"


# ------------------------------------------------------------------ invariant


def test_I2_a_file_of_a_refused_type_or_size_reaches_neither_storage_nor_store_nor_model() -> None:
    app = UploadApp(dataclasses.replace(make_config(), max_upload_bytes=1024))
    app.seed(KOCH, "k0")
    app.ai.file_to(KOCH)
    accepted = app.upload(PNG, "image/png", "ok-1")
    assert accepted["text"] == placed(KOCH)
    before = (list(app.materials()), list(app.files.puts), dict(app.files.objects))
    calls, file_calls = list(app.ai.calls), list(app.ai.file_calls)
    refused_types = [
        "image/gif",
        "IMAGE/GIF",
        "image/svg+xml",
        "image/pngx",
        "image/png-x",
        "text/html",
        "text/plainx",
        "application/x-pdf",
        "application/octet-stream",
        DOCX,
        "multipart/form-data; boundary=x",
        None,
    ]
    number = 0
    for content_type in refused_types:
        for material_id in ("ok-1", "new-1"):
            number += 1
            reply = app.upload(PNG, content_type, material_id if material_id == "ok-1" else f"r{number}")
            assert reply["text"] == NOT_READ, (content_type, reply)
    for mime in ALLOWED:
        for size in (1025, 4096):
            for material_id in ("ok-1", "r-big"):
                reply = app.upload(b"x" * size, mime, material_id)
                assert reply["text"].startswith("Файл завеликий"), (mime, size, reply)
        reply = app.upload(b"", mime, "r-empty")
        assert reply["text"] == EMPTY, (mime, reply)
    assert (list(app.materials()), list(app.files.puts), dict(app.files.objects)) == before
    assert (app.ai.calls, app.ai.file_calls) == (calls, file_calls)
    assert app.upload(b"x" * 1024, "image/jpeg", "ok-2")["text"] == placed(KOCH)
    assert app.files.puts[-1] == (SUB, "ok-2")
