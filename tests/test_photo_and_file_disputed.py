"""Disputed contract tests of the slice photo-and-file: each fixes one reading of a question to the contract.

Written by the slice tester from the sealed contract `.engine/slices/photo-and-file.md`, without the code.
This file is sealed only after the slice planner answers the questions Q1-Q3 of the hand-in.
"""

from typing import Any

from mamamemory.integrations.store import Decide, InMemoryStore
from tests.note_to_case_world import FAILED, failed, placed
from tests.photo_and_file_world import EMPTY, PNG, UploadApp, Uploads
from tests.test_one_task_http import SUB

SCHMIDT = "пані Шмідт"
KOCH = "пан Кох"


def test_q1_empty_body_with_an_allowed_type_for_an_existing_material_is_empty_not_a_finish() -> None:
    # Q1: the order of checks puts «Файл порожній.» (3) before the finish without a body; the finish (1) is
    # an empty body WITHOUT `Content-Type`. Reading taken: with a type, the empty body is refused as empty,
    # even when the material exists, and the material is left as it was.
    app = UploadApp()
    app.seed(KOCH, "k0")
    app.ai.file_to(KOCH)
    app.ai.fail["read_file"] = 1
    assert app.upload(PNG, "image/png", "up-1")["text"] == FAILED
    app.later()
    assert app.upload(b"", "image/png", "up-1")["text"] == EMPTY
    [material] = [m for m in app.materials() if m.material_id == "up-1"]
    assert (material.state, material.text) == ("new", "")
    assert len(app.ai.file_calls) == 1


def test_q2_the_type_goes_on_without_parameters_and_in_lower_case() -> None:
    # Q2: the type is checked without parameters and in lower case; reading taken: that same normalised type
    # is what `add_file` gets, so the object, the material and `read_file` carry «image/jpeg».
    app = UploadApp()
    app.seed(KOCH, "k0")
    app.ai.file_to(KOCH)
    assert app.upload(PNG, "Image/JPEG; foo=bar", "up-1")["text"] == placed(KOCH)
    [material] = [m for m in app.materials() if m.material_id == "up-1"]
    assert material.mime == "image/jpeg"
    assert app.files.objects[(SUB, "up-1")][1] == "image/jpeg"
    assert [call[2] for call in app.ai.file_calls] == ["image/jpeg"]


class SecondWriteFails(InMemoryStore):
    """The fake store; the second write under `materials/` after `arm()` raises (the text, after the
    record)."""

    def __init__(self) -> None:
        super().__init__()
        self.countdown: int | None = None

    def arm(self) -> None:
        self.countdown = 2

    def _maybe_fail(self, path: str) -> None:
        if path.startswith("materials/") and self.countdown is not None:
            self.countdown -= 1
            if self.countdown == 0:
                self.countdown = None
                raise OSError("store write failed")

    def set(self, account_id: str, path: str, data: dict[str, Any]) -> None:
        self._maybe_fail(path)
        super().set(account_id, path, data)

    def transact(self, account_id: str, path: str, decide: Decide) -> dict[str, Any] | None:
        self._maybe_fail(path)
        return super().transact(account_id, path, decide)


def test_q3_text_plain_left_unread_is_read_from_the_body_of_the_repeat() -> None:
    # Q3: a `text/plain` material can stay `new` with `text: ""` (the write of its text failed); `Files` has
    # no read and the contract reads `text/plain` without a model. Reading taken: a repeat WITH the body takes
    # the text from that body — no model, no new put. The header-only repeat of such a material is not fixed.
    store = SecondWriteFails()
    world = Uploads(store=store)
    world.seed(KOCH, "k0")
    world.ai.file_to(KOCH)
    store.arm()
    content = "HbA1c 7,2 — пані Шмідт".encode()
    assert failed(world.try_add("t1", content, "text/plain"))
    reply = world.add("t1", content, "text/plain")
    assert reply.text == placed(KOCH)
    assert world.material("t1").text == "HbA1c 7,2 — пані Шмідт"
    assert world.ai.file_calls == []
    assert world.files.puts == [("acc-1", "t1")]
