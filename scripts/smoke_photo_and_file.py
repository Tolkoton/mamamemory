"""Smoke of slice photo-and-file (F3 S2) with the real bucket and models: P-GCS and the reading of files.

(a) A PDF built here with the text «Frau Schmidt HbA1c 7,2» → `Files.put` into the real bucket → `read_file`
(Flash-Lite) by `gs://` → the text holds «7,2». (b) The photo `poc/out/poc1-images/c02-0.png` → the same path
→ the text is not empty. (c) The PDF's text through the Розкладач (3.8 Flash) on a catalogue of six made-up
cases → «пані Шмідт». (d) Both objects lie under the test account and are deleted at the end. All 4 must pass.

    GCP_PROJECT=pocket-lawyer-431614 VERTEX_LOCATION=eu uv run python scripts/smoke_photo_and_file.py
"""

import os
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path

from google import genai
from google.cloud.storage import Client as StorageClient

from mamamemory import cases
from mamamemory.config import Config
from mamamemory.integrations.ai import AI
from mamamemory.integrations.files import Files

NOW = datetime(2026, 11, 9, 9, 7, tzinfo=UTC)
PHOTO = Path(__file__).resolve().parents[1] / "poc" / "out" / "poc1-images" / "c02-0.png"
SIX = [
    ("пан Кох", "Пацієнт 71 рік, цукровий діабет 2 типу, метформін; алергія на пеніцилін."),
    ("пані Шмідт", "Пацієнтка 64 роки, гіпертонія, раміприл; контроль HbA1c."),
    ("пан Шмітт", "Пацієнт 58 років, після інфаркту 2024, аспірин і статин."),
    ("пані Майєр", "Пацієнтка 80 років, остеопороз, щорічна денситометрія."),
    ("город", "Купівля ділянки біля Кельна: договір, нотаріус, межі ділянки."),
    ("пані Фішер", "Пацієнтка 45 років, гіпотиреоз, L-тироксин 75 мкг."),
]  # fmt: skip


def pdf(text: str) -> bytes:
    """A one-page PDF with `text` in Helvetica (Latin only), offsets computed."""
    stream = f"BT /F1 24 Tf 72 720 Td ({text}) Tj ET".encode()
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R "
        b"/Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out, offsets = bytearray(b"%PDF-1.4\n"), []
    for n, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{n} 0 obj\n".encode() + body + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode()
    out += b"".join(f"{o:010d} 00000 n \n".encode() for o in offsets)
    out += f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    return bytes(out)


def main() -> int:
    project = os.environ["GCP_PROJECT"]
    client = genai.Client(vertexai=True, project=project, location=os.environ.get("VERTEX_LOCATION", "eu"))
    config = Config(
        gcp_project=project, firestore_database="mamamemory", vertex_location="eu",
        tts_endpoint="eu-texttospeech.googleapis.com", region="europe-west3", oauth_client_id="-",
        oauth_client_secret="-", session_key="-", session_max_age_s=1, login_max_age_s=1, base_url="-",
        request_timeout_s=60, call_timeout_s=15, files_bucket=f"{project}-mamamemory-files",
    )  # fmt: skip
    ai = AI(lambda: client, config)
    storage = StorageClient(project=project)
    files = Files(lambda: storage, config.files_bucket, call_timeout_s=config.call_timeout_s)
    account = f"smoke-{uuid.uuid4().hex[:8]}"
    failed = 0

    def read(material_id: str, data: bytes, mime: str) -> str:
        gs_uri = files.put(account, material_id, data, mime)
        answer = ai.generate_json_with_file("read_file", cases.READ_PROMPT, cases.READ_SCHEMA, gs_uri, mime)
        return str(answer.get("text") or "")

    try:
        pdf_text = read("pdf-1", pdf("Frau Schmidt HbA1c 7,2"), "application/pdf")
        ok = "7,2" in pdf_text
        failed += not ok
        print(f"{'PASS' if ok else 'FAIL'}  PDF by gs:// -> {pdf_text!r}")
        photo_text = read("png-1", PHOTO.read_bytes(), "image/png")
        ok = bool(photo_text.strip())
        failed += not ok
        print(f"{'PASS' if ok else 'FAIL'}  photo by gs:// -> {photo_text[:120]!r}")
        known = [cases.Case(f"c{n}", name, description, NOW) for n, (name, description) in enumerate(SIX)]
        answer = ai.generate_json(
            "classify_case", cases._classify_prompt(known, pdf_text), cases.CLASSIFY_SCHEMA
        )
        ok = answer.get("number") == 2
        failed += not ok
        print(f"{'PASS' if ok else 'FAIL'}  PDF text through the Розкладач -> {answer}")
    finally:
        names = sorted(blob.name for blob in storage.list_blobs(config.files_bucket, prefix=f"{account}/"))
        ok = names == [f"{account}/pdf-1", f"{account}/png-1"]
        failed += not ok
        print(f"{'PASS' if ok else 'FAIL'}  objects under the test account -> {names}")
        for name in names:
            storage.bucket(config.files_bucket).blob(name).delete()
    print("SMOKE PASSED" if failed == 0 else f"SMOKE FAILED: {failed} of 4")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
