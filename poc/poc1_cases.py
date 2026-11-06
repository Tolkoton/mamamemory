# /// script
# requires-python = ">=3.11"
# dependencies = ["google-genai>=1.0", "pillow>=10.1"]
# ///
"""PoC 1 (M2): does Gemini read a photo of a document, file a new material into the right case,
and answer a question from the case's materials — with all of a case in one request?

Premises: P-OCR, P-CTX (.engine/premises/premise-log.md). Invented data only: German lab reports
rendered as slightly rotated photos, Ukrainian notes, one "large" patient followed for months.

    GOOGLE_CLOUD_PROJECT=pocket-lawyer-431614 uv run poc/poc1_cases.py
    uv run poc/poc1_cases.py --dry-run      # build the data and images only, no API calls

Writes poc/out/poc1-report.md (and the images to poc/out/poc1-images/).
"""

from __future__ import annotations

import argparse
import io
import random
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any

from common import MODELS, OUT_DIR, Usage, client, generate, normalize, parse_json, vertex_location
from google import genai
from google.genai import types
from PIL import Image, ImageDraw, ImageFont

SERIES = [3, 6, 12, 24]  # growing number of cases: where does filing start to err?
BIG_CASE_MATERIALS = 30  # the patient "followed for months" (journal 17:41Z)

# Similar names on purpose: filing gets harder with look-alike patients, not only with case size.
SURNAMES = [
    ("Müller", "Мюллер"),
    ("Möller", "Меллер"),
    ("Schmidt", "Шмідт"),
    ("Schmitt", "Шмітт"),
    ("Meyer", "Маєр"),
    ("Meier", "Майєр"),
    ("Maier", "Маєр-Майєр"),
    ("Becker", "Беккер"),
    ("Bäcker", "Бекер"),
    ("Fischer", "Фішер"),
    ("Weber", "Вебер"),
    ("Wagner", "Вагнер"),
    ("Schneider", "Шнайдер"),
    ("Schulz", "Шульц"),
    ("Schulze", "Шульце"),
    ("Hoffmann", "Гофманн"),
    ("Koch", "Кох"),
    ("Richter", "Ріхтер"),
    ("Klein", "Кляйн"),
    ("Wolf", "Вольф"),
    ("Neumann", "Нойманн"),
    ("Schwarz", "Шварц"),
    ("Zimmermann", "Ціммерманн"),
    ("Braun", "Браун"),
]
FIRST = ["Anna", "Maria", "Ursula", "Helga", "Monika", "Peter", "Klaus", "Jürgen", "Sabine", "Renate"]
LABS = {
    "TSH": ("mU/l", 0.4, 6.5),
    "HbA1c": ("%", 5.2, 8.9),
    "Ferritin": ("µg/l", 8, 180),
    "Vitamin D (25-OH)": ("ng/ml", 9, 48),
    "Kreatinin": ("mg/dl", 0.6, 1.6),
    "CRP": ("mg/l", 0.5, 24),
}
TOPICS = ["Hypothyreose", "Diabetes mellitus Typ 2", "Eisenmangel", "Vitamin-D-Mangel", "Hypertonie"]
NOTES = [
    "Говорила з пані {ua}: скаржиться на втому, домовились повторити {lab} через 6 тижнів.",
    "Пані {ua} принесла виписку з лікарні, треба переглянути дозування.",
    "Подзвонити пані {ua} щодо результату {lab}, вона хвилюється.",
    "У пані {ua} знову болить голова, тиск вранці 150/95.",
]


@dataclass
class Material:
    kind: str  # "lab" (a photo) or "note" (Ukrainian text)
    when: date
    text: str  # the ground truth: what is written on the photo, or the note itself
    image: bytes = b""


@dataclass
class Case:
    case_id: str
    name: str
    name_ua: str
    born: date
    topic: str
    materials: list[Material] = field(default_factory=list)
    held_out: Material | None = None


def fmt(value: float) -> str:
    return f"{value:.1f}".replace(".", ",")


def lab_report(rng: random.Random, case: Case, when: date, labs: list[str]) -> str:
    lines = [
        "Labor Dr. Hartmann & Kollegen, Frankfurt am Main",
        "Befundbericht",
        f"Patient: {case.name}, geb. {case.born:%d.%m.%Y}",
        f"Eingang: {when:%d.%m.%Y}",
        "",
        "Untersuchung            Ergebnis   Einheit",
    ]
    for lab in labs:
        unit, low, high = LABS[lab]
        lines.append(f"{lab:<23} {fmt(rng.uniform(low, high)):>8}   {unit}")
    lines += ["", f"Klinische Angabe: {case.topic}"]
    return "\n".join(lines)


def photo(text: str, rng: random.Random) -> bytes:
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf", 26)
    except OSError:
        font = ImageFont.load_default(size=26)
    page = Image.new("RGB", (1100, 700), (246, 244, 236))
    ImageDraw.Draw(page).multiline_text((50, 50), text, fill=(30, 30, 30), font=font, spacing=10)
    page = page.rotate(rng.uniform(-2.5, 2.5), expand=True, fillcolor=(190, 186, 176))
    buffer = io.BytesIO()
    page.save(buffer, format="PNG")
    return buffer.getvalue()


def build_cases(rng: random.Random) -> list[Case]:
    cases = []
    start = date(2026, 3, 1)
    for index, (name, name_ua) in enumerate(SURNAMES):
        case = Case(
            case_id=f"c{index + 1:02d}",
            name=f"{rng.choice(FIRST)} {name}",
            name_ua=name_ua,
            born=date(1940, 1, 1) + timedelta(days=rng.randrange(365 * 45)),
            topic=rng.choice(TOPICS),
        )
        count = BIG_CASE_MATERIALS if index == 0 else rng.randint(3, 5)
        for step in range(count + 1):
            when = start + timedelta(days=step * (240 // count) + rng.randrange(5))
            if rng.random() < 0.6:
                labs = rng.sample(list(LABS), 2)
                text = lab_report(rng, case, when, labs)
                material = Material("lab", when, text, photo(text, rng))
            else:
                text = rng.choice(NOTES).format(ua=case.name_ua, lab=rng.choice(list(LABS)))
                material = Material("note", when, text)
            if step == count:
                case.held_out = material
            else:
                case.materials.append(material)
        cases.append(case)
    return cases


def new_patients(rng: random.Random) -> list[Material]:
    stranger = Case("new", "Erika Lindemann", "Ліндеманн", date(1951, 4, 2), "Hypothyreose")
    text = lab_report(rng, stranger, date(2026, 10, 20), ["TSH", "Ferritin"])
    return [
        Material("lab", date(2026, 10, 20), text, photo(text, rng)),
        Material("note", date(2026, 10, 21), "Нова пацієнтка, пані Ліндеманн, перший прийом у вівторок."),
    ]


def as_parts(material: Material) -> list[Any]:
    if material.kind == "lab":
        return [types.Part.from_bytes(data=material.image, mime_type="image/png")]
    return [material.text]


def read_photo(gc: genai.Client, model: str, material: Material, usage: Usage) -> str:
    prompt = "Перепиши дослівно весь текст із цього фото документа. Лише текст, без коментарів."
    return generate(gc, model, [*as_parts(material), prompt], usage)


def describe(gc: genai.Client, model: str, texts: list[str], usage: Usage) -> str:
    """The case description, built the way production builds it: updated as each material arrives."""
    description = ""
    for text in texts:
        prompt = (
            "Ти ведеш короткий опис справи пацієнта для лікарки. Поточний опис:\n"
            f"{description or '(порожньо)'}\n\nНовий матеріал:\n{text}\n\n"
            "Онови опис: ім'я пацієнта (як у документах і як українською), дата народження, якщо є, "
            "основна тема, останні події. Не більше трьох речень. Відповідай лише описом."
        )
        description = generate(gc, model, [prompt], usage) or description
    return description


def file_material(
    gc: genai.Client, model: str, catalog: list[tuple[str, str]], material: Material, usage: Usage
) -> str:
    listing = "\n".join(f"- {case_id}: {description}" for case_id, description in catalog)
    prompt = (
        "Лікарка додає новий матеріал. Ось її справи (ідентифікатор: опис):\n"
        f"{listing}\n\nДо якої справи належить матеріал вище? Якщо жодна не підходить — це нова справа. "
        'Відповідай JSON: {"case_id": "<ідентифікатор або new>"}'
    )
    return str(
        parse_json(generate(gc, model, [*as_parts(material), prompt], usage, as_json=True)).get("case_id", "")
    )


def answer(gc: genai.Client, model: str, case: Case, texts: list[str], question: str, usage: Usage) -> str:
    joined = "\n\n---\n\n".join(
        f"[{m.when:%d.%m.%Y}]\n{t}" for m, t in zip(case.materials, texts, strict=True)
    )
    prompt = (
        f"Матеріали справи «{case.name}» у порядку часу:\n\n{joined}\n\n"
        f"Питання лікарки: {question}\nВідповідай коротко українською, лише з цих матеріалів."
    )
    return generate(gc, model, [prompt], usage)


def last_lab(case: Case) -> tuple[str, str, date] | None:
    for material in reversed(case.materials):
        if material.kind == "lab":
            line = material.text.splitlines()[6]
            lab = next(name for name in LABS if line.startswith(name))
            return lab, line[len(lab) :].split()[0], material.when
    return None


def run(dry_run: bool) -> str:
    rng = random.Random(20261024)
    cases = build_cases(rng)
    strangers = new_patients(rng)
    report = ["# PoC 1 — справи, фото й відповіді (вигадані дані)", ""]
    report.append(
        f"Справ: {len(cases)}; матеріалів у великій справі: {len(cases[0].materials)}; серії: {SERIES}."
    )
    images = OUT_DIR / "poc1-images"
    images.mkdir(parents=True, exist_ok=True)
    for case in cases[:3]:
        for number, material in enumerate(case.materials[:2]):
            if material.kind == "lab":
                (images / f"{case.case_id}-{number}.png").write_bytes(material.image)
    if dry_run:
        report.append("\n--dry-run: дані й фото побудовано, до API не зверталися.")
        return "\n".join(report)

    report.append(f"Vertex AI location: `{vertex_location()}`.")
    gc = client()
    for model in MODELS:
        usage = Usage()
        report += ["", f"## {model}", ""]

        # 1. Photos → text; a key value on the photo must survive.
        texts: dict[str, list[str]] = {}
        read_ok = read_total = 0
        for case in cases:
            texts[case.case_id] = []
            for material in case.materials:
                if material.kind == "lab":
                    got = read_photo(gc, model, material, usage)
                    value_line = material.text.splitlines()[6]
                    read_total += 1
                    read_ok += normalize(value_line.split()[-2]) in normalize(got)
                    texts[case.case_id].append(got)
                else:
                    texts[case.case_id].append(material.text)
        report.append(f"- Читання фото: значення з бланка збережене в {read_ok} з {read_total}.")

        # 2. Case descriptions, updated per material, as in production.
        catalog = [(case.case_id, describe(gc, model, texts[case.case_id], usage)) for case in cases]

        # 3. Filing a new material, for a growing number of cases.
        report.append(
            "- Розкладання нового матеріалу (правильно / усього; "
            "«нова справа» — 2 матеріали нових пацієнток):"
        )
        for size in SERIES:
            subset = catalog[:size]
            right = 0
            wrong: list[str] = []
            for case in cases[:size]:
                assert case.held_out is not None
                got = file_material(gc, model, subset, case.held_out, usage)
                right += got == case.case_id
                if got != case.case_id:
                    wrong.append(f"{case.case_id}→{got or '?'}")
            for material in strangers:
                got = file_material(gc, model, subset, material, usage)
                right += got == "new"
                if got != "new":
                    wrong.append(f"new→{got or '?'}")
            report.append(
                f"  - {size} справ: {right} / {size + len(strangers)}"
                + (f"; помилки: {', '.join(wrong)}" if wrong else "")
            )

        # 4. Answering from all of a case in one request, small cases and the large one.
        report.append(
            "- Відповідь із матеріалів справи (останній аналіз; очікуване значення має бути у відповіді):"
        )
        for case in [cases[0], *cases[1:4]]:
            truth = last_lab(case)
            if truth is None:
                continue
            lab, value, when = truth
            before = usage.tokens_in
            got = answer(gc, model, case, texts[case.case_id], f"Яке останнє значення {lab} і коли?", usage)
            ok = normalize(value) in normalize(got)
            report.append(
                f"  - {case.case_id} ({len(case.materials)} матеріалів, "
                f"~{usage.tokens_in - before} токенів запиту): "
                f"{'так' if ok else 'НІ'} — очікувано {lab} {value} від {when:%d.%m.%Y}; "
                f"відповідь: {got.strip()[:160]!r}"
            )

        report.append(
            f"- Викликів: {usage.calls}; токенів: {usage.tokens_in} вхід / {usage.tokens_out} вихід / "
            f"{usage.tokens_thinking} роздуми; "
            f"≈ ${usage.cost(model):.3f}; час: {usage.seconds:.0f} с; помилок: {len(usage.errors)}"
        )
        report += [f"  - помилка: {error}" for error in usage.errors[:5]]
    return "\n".join(report)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dry-run", action="store_true")
    report = run(parser.parse_args().dry_run)
    OUT_DIR.mkdir(exist_ok=True)
    (OUT_DIR / "poc1-report.md").write_text(report + "\n", encoding="utf-8")
    print(report)


if __name__ == "__main__":
    main()
