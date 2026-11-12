"""Contract tests of the slice photo-and-file below HTTP: `cases.add_file`, `Files`,
`AI.generate_json_with_file` and `Config`.

Seam 1 (break and repeat), Seam 3 (reading), Seam 4 (separate accounts), I1, I3. Written by the slice tester
from the sealed contract `.engine/slices/photo-and-file.md`, without the code. A failure at the level of
`cases` may be raised or answered with «Не вдалося…» (`failed`), as in the tests of note-to-case; the
contract fixes what `http` answers. `data=None` is the repeat with the header only.
"""

import json
from typing import Any

import pytest
from google.genai import types

from mamamemory.config import Config, load_config
from mamamemory.integrations.ai import AI
from mamamemory.integrations.store import Decide, InMemoryStore
from tests.note_to_case_world import NOT_UNDERSTOOD, ask, failed, placed
from tests.photo_and_file_world import (
    BUCKET,
    NO_TEXT,
    PDF,
    PNG,
    READ_TEXT,
    FakeStorage,
    Uploads,
    make_files,
)
from tests.test_config import _environ
from tests.test_one_task_planning import NOW, make_config

SCHMIDT = "пані Шмідт"
KOCH = "пан Кох"
ACC = "acc-1"


def two_cases(world: Uploads | None = None) -> tuple[Uploads, str]:
    """A world with «пан Кох» and «пані Шмідт» made by notes and «так»; the Розкладач names «пані Шмідт»."""
    world = world or Uploads()
    world.seed(KOCH, "k0")
    world.seed(SCHMIDT, "m0")
    world.ai.file_to(SCHMIDT)
    return world, SCHMIDT


def file_materials(world: Uploads) -> list[Any]:
    return [m for m in world.materials() if m.kind in ("photo", "file")]


class FailingStore(InMemoryStore):
    """The fake store; `fail_materials = n` makes the next n writes under `materials/` raise."""

    def __init__(self) -> None:
        super().__init__()
        self.fail_materials = 0

    def _maybe_fail(self, path: str) -> None:
        if path.startswith("materials/") and self.fail_materials > 0:
            self.fail_materials -= 1
            raise OSError("store write failed")

    def set(self, account_id: str, path: str, data: dict[str, Any]) -> None:
        self._maybe_fail(path)
        super().set(account_id, path, data)

    def transact(self, account_id: str, path: str, decide: Decide) -> dict[str, Any] | None:
        self._maybe_fail(path)
        return super().transact(account_id, path, decide)


# ------------------------------------------------------------------ recording (Seam 1)


def test_original_is_put_before_the_material_is_written() -> None:
    world, _ = two_cases()
    seen: list[object] = []
    world.files.on_put = lambda account_id, material_id: seen.append(
        world.store.get(account_id, f"materials/{material_id}")
    )
    world.add("f1", PNG, "image/png")
    assert world.files.puts == [(ACC, "f1")]
    assert seen == [None], "the material was written before the original was put"
    material = world.material("f1")
    assert material.gs_uri == f"gs://{BUCKET}/{ACC}/f1"
    assert world.files.objects[(ACC, "f1")] == (PNG, "image/png")


def test_material_is_written_new_with_empty_text_before_it_is_read() -> None:
    world, _ = two_cases()
    world.ai.fail["read_file"] = 1
    assert failed(world.try_add("f1", PNG, "image/png"))
    material = world.material("f1")
    assert material.kind == "photo"
    assert material.state == "new"
    assert material.text == ""
    assert material.gs_uri == f"gs://{BUCKET}/{ACC}/f1"
    assert material.mime == "image/png"


def test_kind_is_photo_for_every_image_type_and_file_otherwise() -> None:
    world, _ = two_cases()
    kinds = {
        "image/png": "photo",
        "image/jpeg": "photo",
        "image/webp": "photo",
        "image/heic": "photo",
        "image/heif": "photo",
        "application/pdf": "file",
        "text/plain": "file",
    }
    for number, (mime, kind) in enumerate(kinds.items()):
        world.add(f"f{number}", b"HbA1c 7,2", mime)
        assert world.material(f"f{number}").kind == kind, mime
        assert world.material(f"f{number}").mime == mime


# ------------------------------------------------------------------ reading (Seam 3)


def test_photo_is_read_by_read_file_with_its_gs_uri_and_mime() -> None:
    world, _ = two_cases()
    world.add("f1", PNG, "image/png")
    assert world.ai.file_calls == [("read_file", f"gs://{BUCKET}/{ACC}/f1", "image/png")]
    assert world.material("f1").text == READ_TEXT


def test_pdf_is_a_file_read_by_read_file_with_its_gs_uri_and_mime() -> None:
    world, _ = two_cases()
    world.add("f1", PDF, "application/pdf")
    assert world.ai.file_calls == [("read_file", f"gs://{BUCKET}/{ACC}/f1", "application/pdf")]
    material = world.material("f1")
    assert material.kind == "file"
    assert material.text == READ_TEXT


def test_text_plain_is_its_own_utf8_text_with_bad_bytes_replaced_and_no_model() -> None:
    world, _ = two_cases()
    world.add("f1", "HbA1c 7,2 — пані Шмідт ".encode() + b"\xff", "text/plain")
    assert world.ai.file_calls == []
    material = world.material("f1")
    assert material.kind == "file"
    assert material.text == "HbA1c 7,2 — пані Шмідт �"
    assert world.files.objects[(ACC, "f1")][0].startswith(b"HbA1c")
    assert any("HbA1c 7,2 — пані Шмідт" in p for p in world.ai.prompts.get("classify_case", []))


def test_the_classifier_gets_the_read_text_and_the_file_goes_into_the_case_with_description() -> None:
    world, name = two_cases()
    reply = world.add("f1", PNG, "image/png")
    assert reply.text == placed(name)
    assert [call[0] for call in world.ai.file_calls] == ["read_file"], "only read_file is given the file"
    assert any(READ_TEXT in p for p in world.ai.prompts["classify_case"])
    material = world.material("f1")
    assert material.state == "placed"
    assert material.case_id == [c.case_id for c in world.cases() if c.name == name][0]
    assert world.ai.count("describe_case") == 1


def test_empty_read_text_is_no_text_and_the_classifier_gets_it() -> None:
    world, name = two_cases()
    world.ai.read_text = ""
    reply = world.add("f1", PNG, "image/png")
    assert world.material("f1").text == NO_TEXT
    assert any(NO_TEXT in p for p in world.ai.prompts["classify_case"])
    cases_now = [c.name for c in world.cases()]
    assert reply.text in {placed(n) for n in cases_now} | {NOT_UNDERSTOOD} or reply.text.startswith(
        "Створити справу «"
    ), reply.text
    assert len(file_materials(world)) == 1


def test_empty_read_text_on_an_empty_catalogue_without_a_name_is_not_understood() -> None:
    world = Uploads()
    world.ai.read_text = ""
    world.ai.nameless = True
    reply = world.add("f1", PNG, "image/png")
    assert any(NO_TEXT in p for p in world.ai.prompts["name_case"])
    assert reply.text == NOT_UNDERSTOOD
    material = world.material("f1")
    assert material.text == NO_TEXT
    assert material.state == "unplaced"


# ------------------------------------------------------------------ break and repeat (Seam 1)


def test_put_failure_writes_nothing_and_the_header_only_repeat_fails_without_writing() -> None:
    world, _ = two_cases()
    world.files.fail = 1
    assert failed(world.try_add("f1", PNG, "image/png"))
    assert file_materials(world) == []
    assert world.ai.file_calls == []
    puts = len(world.files.puts)
    assert failed(world.try_add("f1", None, None))
    assert file_materials(world) == []
    assert world.ai.calls == []
    assert len(world.files.puts) == puts
    assert world.files.objects == {}


def test_header_only_for_an_id_with_no_material_fails_writes_nothing_and_calls_no_model() -> None:
    world, _ = two_cases()
    assert failed(world.try_add("nope", None, None))
    assert world.with_id("nope") == []
    assert world.ai.calls == []
    assert world.files.puts == []


@pytest.mark.parametrize("repeat_with_body", [True, False])
def test_repeat_after_a_read_failure_reads_and_places_without_a_new_put(repeat_with_body: bool) -> None:
    world, name = two_cases()
    world.ai.fail["read_file"] = 1
    assert failed(world.try_add("f1", PNG, "image/png"))
    reply = world.add("f1", PNG, "image/png") if repeat_with_body else world.add("f1", None, None)
    assert reply.text == placed(name)
    assert world.files.puts == [(ACC, "f1")]
    assert [call[0] for call in world.ai.file_calls] == ["read_file", "read_file"]
    assert world.material("f1").text == READ_TEXT
    assert world.material("f1").state == "placed"


def test_repeat_after_a_classifier_failure_places_without_reading_again() -> None:
    world, name = two_cases()
    world.ai.fail["classify_case"] = 1
    assert failed(world.try_add("f1", PNG, "image/png"))
    assert world.material("f1").state == "new"
    assert world.material("f1").text == READ_TEXT
    reply = world.add("f1", None, None)
    assert reply.text == placed(name)
    assert len(world.ai.file_calls) == 1
    assert world.files.puts == [(ACC, "f1")]


def test_deadline_passed_after_put_leaves_a_new_unread_material_and_the_header_repeat_finishes() -> None:
    world, name = two_cases()
    world.files.after_put = world.clock.expire
    assert failed(world.try_add("f1", PNG, "image/png"))
    assert world.ai.file_calls == [], "a model was called after the deadline"
    material = world.material("f1")
    assert (material.state, material.text) == ("new", "")
    world.clock.at = NOW
    assert world.add("f1", None, None).text == placed(name)
    assert world.files.puts == [(ACC, "f1")]
    assert len(world.ai.file_calls) == 1


def test_deadline_passed_after_reading_calls_no_classifier() -> None:
    world, _ = two_cases()
    world.ai.after["read_file"] = world.clock.expire
    assert failed(world.try_add("f1", PNG, "image/png"))
    assert world.ai.count("classify_case") == 0
    assert world.material("f1").state == "new"


def test_repeat_of_a_placed_file_answers_by_its_state_without_a_new_put_or_read() -> None:
    world, name = two_cases()
    first = world.add("f1", PNG, "image/png")
    again = world.add("f1", PNG, "image/png")
    header = world.add("f1", None, None)
    assert first.text == again.text == header.text == placed(name)
    assert world.files.puts == [(ACC, "f1")]
    assert len(world.ai.file_calls) == 1
    assert len(file_materials(world)) == 1


def test_repeat_of_a_file_waiting_for_yes_asks_the_same_question() -> None:
    world, _ = two_cases()
    world.ai.new_case("пан Мюллер")
    first = world.add("f1", PNG, "image/png")
    assert first.text == ask("пан Мюллер")
    assert first.question is not None and (first.question.kind, first.question.id) == ("case", "f1")
    again = world.add("f1", None, None)
    assert again.text == first.text
    assert world.material("f1").state == "pending"
    assert len(world.ai.file_calls) == 1


def note_view(material: Any) -> tuple[Any, ...]:
    """What a note is: the fields the file must not change (the description flag is the case's business)."""
    return (material.kind, material.text, material.state, material.case_id, material.gs_uri, material.mime)


def test_note_id_takes_the_file_under_the_derived_id_and_leaves_the_note() -> None:
    world, name = two_cases()
    world.notes.add("запиши до пані Шмідт: тиск 130/80", "n1")
    note = note_view(world.material("n1"))
    world.ai.calls.clear()
    reply = world.add("n1", PNG, "image/png")
    assert reply.text == placed(name)
    assert note_view(world.material("n1")) == note
    derived = world.material("n1-file")
    assert derived.kind == "photo"
    assert derived.gs_uri == f"gs://{BUCKET}/{ACC}/n1-file"
    world.add("n1", PNG, "image/png")
    world.add("n1", None, None)
    assert set(world.files.puts) == {(ACC, "n1-file")}
    assert len(world.with_id("n1-file")) == 1
    assert note_view(world.material("n1")) == note


def test_note_id_repeat_with_header_only_finishes_the_derived_material() -> None:
    world, name = two_cases()
    world.notes.add("запиши до пані Шмідт: тиск 130/80", "n1")
    world.ai.fail["read_file"] = 1
    assert failed(world.try_add("n1", PNG, "image/png"))
    assert world.add("n1", None, None).text == placed(name)
    assert world.material("n1-file").state == "placed"
    assert world.files.puts == [(ACC, "n1-file")]
    assert world.material("n1").kind == "note"


# ------------------------------------------------------------------ Files (Cloud Storage)


def test_files_put_writes_account_slash_material_with_type_and_call_timeout_and_returns_gs_uri() -> None:
    storage = FakeStorage()
    files = make_files(storage, "bkt-1", call_timeout_s=7)
    assert files.put("acc-1", "m-1", PNG, "image/png") == "gs://bkt-1/acc-1/m-1"
    assert storage.objects == {("bkt-1", "acc-1/m-1"): PNG}
    upload = storage.uploads[0]
    assert upload.get("content_type") == "image/png"
    assert upload.get("timeout") == 7


def test_files_put_of_the_same_id_overwrites_the_same_object() -> None:
    storage = FakeStorage()
    files = make_files(storage)
    first = files.put("acc-1", "m-1", PNG, "image/png")
    second = files.put("acc-1", "m-1", PDF, "application/pdf")
    assert first == second == f"gs://{BUCKET}/acc-1/m-1"
    assert storage.objects == {(BUCKET, "acc-1/m-1"): PDF}


def test_files_put_refuses_the_ids_document_path_refuses() -> None:
    storage = FakeStorage()
    files = make_files(storage)
    for account_id, material_id in [
        ("", "m-1"),
        (".", "m-1"),
        ("..", "m-1"),
        ("a/b", "m-1"),
        ("acc-1", ""),
        ("acc-1", "."),
        ("acc-1", ".."),
        ("acc-1", "m/1"),
        ("acc-1", "../m"),
    ]:
        with pytest.raises(ValueError):
            files.put(account_id, material_id, PNG, "image/png")
    assert storage.objects == {}


# ------------------------------------------------------------------ AI with a file


class FakeModels:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def generate_content(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        return types.GenerateContentResponse(
            candidates=[
                types.Candidate(
                    content=types.Content(role="model", parts=[types.Part(text=json.dumps({"text": "7,2"}))])
                )
            ]
        )


class FakeGenai:
    def __init__(self) -> None:
        self.models = FakeModels()


def flat_parts(contents: Any) -> list[tuple[str, str, str | None]]:
    """The parts of `contents` in order: ("file", uri, mime) or ("text", text, None)."""
    items = contents if isinstance(contents, list) else [contents]
    parts: list[tuple[str, str, str | None]] = []
    for item in items:
        if isinstance(item, str):
            parts.append(("text", item, None))
        elif isinstance(item, types.Content):
            parts.extend(flat_parts(list(item.parts or [])))
        elif isinstance(item, types.Part):
            if item.file_data is not None:
                parts.append(("file", str(item.file_data.file_uri), item.file_data.mime_type))
            elif item.text is not None:
                parts.append(("text", item.text, None))
    return parts


def test_generate_json_with_file_sends_the_gs_file_part_before_the_prompt() -> None:
    client = FakeGenai()
    config = make_config()
    ai = AI(lambda: client, config)
    schema = {"type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"]}
    answer = ai.generate_json_with_file(
        "read_file", "Перепиши текст.", schema, "gs://b/acc-1/f1", "image/png"
    )
    assert answer == {"text": "7,2"}
    call = client.models.calls[0]
    assert call["model"] == config.models["read_file"].model == "gemini-3.5-flash-lite"
    parts = flat_parts(call["contents"])
    assert parts[0] == ("file", "gs://b/acc-1/f1", "image/png")
    assert ("text", "Перепиши текст.", None) in parts[1:]
    assert call["config"].response_mime_type == "application/json"


# ------------------------------------------------------------------ Config


def test_files_bucket_is_read_from_files_bucket() -> None:
    config: Config = load_config(_environ(FILES_BUCKET="my-files"))
    assert config.files_bucket == "my-files"


def test_files_bucket_without_files_bucket_is_the_project_bucket() -> None:
    config: Config = load_config(_environ())
    assert config.files_bucket == "pocket-lawyer-431614-mamamemory-files"


# ------------------------------------------------------------------ invariants


def test_I1_an_accepted_file_is_neither_lost_nor_doubled_whatever_breaks_and_repeats() -> None:
    places = ["put", "store", "read_file", "classify_case", "describe_case", "deadline", "nothing"]
    sequences = [
        ["body"],
        ["header", "body"],
        ["body", "header", "body", "header"],
        ["header", "header", "body"],
    ]
    kinds = [("image/png", PNG), ("application/pdf", PDF), ("text/plain", b"x"), ("image/heif", b"h" * 4096)]
    for place in places:
        for sequence in sequences:
            for on_note in (False, True):
                for mime, data in kinds:
                    label = (place, sequence, on_note, mime)
                    world, _ = two_cases(Uploads(store=FailingStore()))
                    store = world.store
                    assert isinstance(store, FailingStore)
                    if on_note:
                        world.notes.add("запиши до пані Шмідт: тиск 130/80", "m1")
                    key = "m1-file" if on_note else "m1"
                    if place == "put":
                        world.files.fail = 1
                    elif place == "store":
                        store.fail_materials = 1
                    elif place == "deadline":
                        world.files.after_put = world.clock.expire
                    elif place != "nothing":
                        world.ai.fail[place] = 1
                    world.try_add("m1", data, mime)
                    for step in sequence:
                        check_one(world, key, label, at_most=True)
                        world.clock.at = NOW
                        if step == "body":
                            world.try_add("m1", data, mime)
                        else:
                            world.try_add("m1", None, None)
                    check_one(world, key, label, at_most=False)


def check_one(world: Uploads, key: str, label: object, *, at_most: bool) -> None:
    materials = file_materials(world)
    objects = [k for k in world.files.objects if k[0] == ACC]
    assert {k[1] for k in world.files.puts} <= {key}, (label, world.files.puts)
    assert all(m.material_id == key for m in materials), (label, materials)
    if at_most:
        assert len(materials) <= 1 and len(objects) <= 1, (label, materials, objects)
    else:
        assert len(materials) == 1 and objects == [(ACC, key)], (label, materials, objects)
    for material in materials:
        assert material.gs_uri == world.files.uri(ACC, key), (label, material)
        assert (ACC, key) in world.files.objects, (label, "gs_uri points to no object")


def test_I3_original_and_material_of_an_account_lie_only_under_its_account_id() -> None:
    # Two accounts, the same ids, one of them a note's id in the first account only; a failure in one.
    first, _ = two_cases()
    second = first.other("acc-2")
    first.notes.add("запиши до пані Шмідт: тиск 130/80", "n1")
    first.add("m1", PNG, "image/png")
    second.ai.fail["read_file"] = 1
    second.try_add("m1", PDF, "application/pdf")
    second.add("m1", None, None)
    first.add("n1", PNG, "image/png")
    second.add("n1", b"HbA1c 7,2", "text/plain")
    assert first.files.objects == {
        ("acc-1", "m1"): (PNG, "image/png"),
        ("acc-1", "n1-file"): (PNG, "image/png"),
        ("acc-2", "m1"): (PDF, "application/pdf"),
        ("acc-2", "n1"): (b"HbA1c 7,2", "text/plain"),
    }
    assert first.material("m1").gs_uri == f"gs://{BUCKET}/acc-1/m1"
    assert first.material("m1").mime == "image/png"
    assert first.material("n1-file").gs_uri == f"gs://{BUCKET}/acc-1/n1-file"
    assert second.material("m1").gs_uri == f"gs://{BUCKET}/acc-2/m1"
    assert second.material("m1").mime == "application/pdf"
    assert second.material("n1").kind == "file"
    assert second.with_id("n1-file") == []
    assert first.material("n1").kind == "note"
    assert first.store.get("acc-2", "materials/n1-file") is None
    storage = FakeStorage()
    files = make_files(storage)
    assert files.put("acc-1", "m1", PNG, "image/png") == f"gs://{BUCKET}/acc-1/m1"
    assert files.put("acc-2", "m1", PDF, "application/pdf") == f"gs://{BUCKET}/acc-2/m1"
    assert storage.objects == {(BUCKET, "acc-1/m1"): PNG, (BUCKET, "acc-2/m1"): PDF}
