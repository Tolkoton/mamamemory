"""A text/plain file and a header-only retry (overseer test gap, F3 S2): its text is written with the
material, so a retry without the body never answers «Не вдалося» for want of a text."""

from tests.note_to_case_world import FAILED
from tests.photo_and_file_world import Uploads


def test_text_plain_header_only_retry_after_a_classifier_failure_places_it() -> None:
    world = Uploads()
    world.seed("пані Шмідт", "s0")
    world.ai.file_to("пані Шмідт")
    world.ai.fail["classify_case"] = 1
    assert world.try_add("t-1", "пані Шмідт: HbA1c 7,2".encode(), "text/plain") is None
    assert world.material("t-1").text == "пані Шмідт: HbA1c 7,2"
    reply = world.add("t-1", None, None)
    assert reply.text != FAILED
    assert reply.text == "Поклала в «пані Шмідт»."
    assert world.ai.count("read_file") == 0
    assert world.files.puts.count((world.session.account_id, "t-1")) == 1
