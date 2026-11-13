"""Contract tests of the slice f4-measure: the report `docs/f4-measure.md`, the premise log, PROGRESS and the
«ви» / «ти» card on the board.

Written by the slice tester from the sealed contract `.engine/slices/f4-measure.md` («Seam (contract)»,
«Hardest seams», «Exit criterion»), without the code. Expected values are written by hand from the contract;
Sonko's reports are read only as the source the contract names.
"""

import re

from tests.f4_measure_sources import (
    PREMISES,
    PROGRESS,
    REVISION,
    S3_DEPLOY,
    count,
    log_status,
    mentions,
    premise_row,
    report_text,
    section,
    task_files,
)

# The answers of Sonko's smoke reports (S2, S3) that show the form of address: «ви», «ти», the third person.
ADDRESS_ANSWERS = [
    "У середу, 11 листопада 2026, 12:00 ви працювали над договором купівлі городу.",
    "У середу, 11 листопада 2026, о 12:00 ти працювала над договором купівлі городу.",
    "Вчора, у середу, 11 листопада 2026, о 12:00, ти працювала над договором купівлі городу.",
    "У середу, 11 листопада 2026, 12:00 мама працювала над договором купівлі городу.",
    "Вчора, у середу, 11 листопада 2026 року, о 12:00, ви працювали над договором купівлі городу "
    "(запис: середа, 11 листопада 2026, 12:00: працюю над договором купівлі городу).",
    "У справі «пані Шмідт» пацієнтка має проблеми зі щитоподібною залозою. За матеріалами (нотатка, "
    "2026-11-12): ТТГ становить 4,9, рекомендовано повторити через шість тижнів. У записах журналу роботи "
    "мами немає записів щодо цієї справи.",
    "У середу, 11 листопада 2026, 12:00 мама працювала над договором купівлі городу. Також у матеріалах "
    "справи є нотатка від 2026-11-12 про те, що договір купівлі потрібно підписати до п'ятниці.",
]


def test_report_names_the_deployed_revision() -> None:
    assert REVISION in report_text()


def test_report_gives_the_smoke_of_each_f4_slice_with_sonkos_numbers() -> None:
    lines = report_text().splitlines()
    for script, n in (("smoke_working_on", 5), ("smoke_work_recall", 9), ("smoke_case_recall", 8)):
        rows = [line for line in lines if script in line]
        assert rows, f"the report does not name {script}.py"
        assert any(count(n).search(row) for row in rows), f"the smoke {script} does not say {n} з {n}"
    case_rows = " ".join(line for line in lines if "smoke_case_recall" in line)
    three = (
        re.search(r"(?:3|три)\s*[×xх]\s*8\s*(?:/|з|із|of)\s*8", case_rows)
        or "тричі" in case_rows
        or len(count(8).findall(case_rows)) >= 3
    )
    assert three, "the report does not say smoke_case_recall passed 8 з 8 three times"


def test_report_quotes_the_first_failure_of_case_recall_verbatim() -> None:
    text = report_text()
    assert "що ми знаємо про пані Шмідт?" in text
    assert "Про «пані Шмідт» поки нічого не записано." in text


def test_report_quotes_the_first_failure_of_s1_verbatim() -> None:
    assert "FAIL  route «лікар о десятій у середу» -> yes (expected edit)" in report_text()


def test_report_names_what_is_deferred() -> None:
    text = report_text()
    assert "WorkLogOver100" in text, "the report does not name the trigger WorkLogOver100"
    assert "100" in text.replace("WorkLogOver100", ""), "the report does not name the 100 newest entries"
    assert re.search(r"(?<!\w)[«\"`]?ви[»\"`]?\s*(?:/|чи|або)\s*[«\"`]?ти(?!\w)", text), (
        "the report does not name the mixed «ви» / «ти»"
    )


def test_report_premise_status_matches_the_premise_log() -> None:
    lines = report_text().splitlines()
    for premise in PREMISES:
        status = log_status(premise)
        where = [i for i, line in enumerate(lines) if mentions(line, premise)]
        assert where, f"the report does not name {premise}"
        near = [" ".join(lines[i : i + 2]) for i in where]
        assert any(
            f"`{status}`" in chunk or re.search(rf"(?<![\w-]){status}(?![\w-])", chunk) for chunk in near
        ), f"the report does not give {premise} the status `{status}` of its premise log row"


def test_report_says_what_is_left_for_the_owner() -> None:
    text = report_text()
    assert "744" in text, "the report does not name card 744"
    assert "746" in text, "the report does not name card 746"


def test_report_names_the_deployed_tree_by_digest_and_file_times() -> None:
    text = report_text()
    assert "40104a4a" in text, "the report does not give the image digest from Sonko's report"
    assert "assistant.py" in text
    assert "12:34:20" in text, "the report does not give the time of assistant.py"
    assert "12:59:18" in text, "the report does not give the time of Sonko's report"


def test_report_maps_every_f4_criterion_to_its_evidence() -> None:
    body = section(report_text(), "Критерії F4")
    lines = body.splitlines()
    for ac in ("AC1", "AC2", "AC3", "AC4"):
        assert re.search(rf"{ac}(?!\d)", body), f"the section «Критерії F4 → докази» does not name {ac}"
    ac1 = [" ".join(lines[i : i + 3]) for i, line in enumerate(lines) if re.search(r"AC1(?!\d)", line)]
    assert any("test_working_on.py" in chunk for chunk in ac1), (
        "AC1 is not backed by tests/test_working_on.py"
    )
    ac4 = [" ".join(lines[i : i + 3]) for i, line in enumerate(lines) if re.search(r"AC4(?!\d)", line)]
    assert any(
        "test_AC4_after_two_working_on_the_prompt_about_x_carries_the_x_entry" in chunk for chunk in ac4
    ), "AC4 is not backed by its test in tests/test_work_recall.py"


def test_premise_log_route_f4_is_verified() -> None:
    assert log_status("P-ROUTE-F4") == "verified"


def test_premise_log_recall_is_verified() -> None:
    assert log_status("P-RECALL") == "verified"


def test_premise_log_ctx_keeps_its_status_and_points_to_recall() -> None:
    assert log_status("P-CTX") == "verified"
    evidence = premise_row("P-CTX")[5]
    assert "P-RECALL" in evidence and "F4 S3" in evidence, (
        "the evidence of P-CTX has no note «зведення — P-RECALL"
    )


def test_seam1_report_and_premise_log_agree_with_sonkos_reports() -> None:
    deployed = re.findall(
        r"revision \[(mamamemory-\d{5}-[a-z0-9]{3})\]", S3_DEPLOY.read_text(encoding="utf-8")
    )
    assert deployed, f"{S3_DEPLOY} names no deployed revision"
    assert deployed[-1] in report_text(), "the report does not give the revision of Sonko's S3 deploy report"
    recall = " ".join(premise_row("P-RECALL")[4:6])
    assert count(8).search(recall), "the premise log row of P-RECALL does not carry Sonko's 8 з 8"


def test_progress_says_f4_waits_for_the_owners_pass() -> None:
    lines = PROGRESS.read_text(encoding="utf-8").splitlines()
    chunks = [" ".join(lines[i : i + 4]) for i, line in enumerate(lines) if re.search(r"F4(?!\d)", line)]
    assert any(
        "код готовий і викладений" in chunk
        and "проходу власника" in chunk
        and "744" in chunk
        and "746" in chunk
        for chunk in chunks
    ), "PROGRESS does not say F4 «код готовий і викладений, чекає проходу власника (744, 746)»"


def test_the_address_question_is_a_card_with_verbatim_answers() -> None:
    cards = [
        path
        for path in task_files()
        if sum(answer in (body := path.read_text(encoding="utf-8")) for answer in ADDRESS_ANSWERS) >= 2
        and "ви" in body
        and "ти" in body
    ]
    assert cards, (
        "no card under tasks/ asks the owner «ви» or «ти» with two or three of Sonko's answers verbatim"
    )
