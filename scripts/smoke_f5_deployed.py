"""Smoke F5 S4 against the deployed address (no sign-in): the revision carries `/api/speak` and the S4 player.

`POST /api/speak` without a cookie → 401 (an unknown route would be 404); `GET /speak.js` and `GET /player.js`
without a cookie → 302 to `/auth/login`: the routes exist (an unknown one is 404);
`/player.js` is S4 code.
Scripts are served only with a session (S1 I1), so their bodies cannot be read here. All 3 must pass.

    uv run python scripts/smoke_f5_deployed.py https://mamamemory-2mfebgg56q-ey.a.run.app
"""

import sys
from urllib.parse import urlparse

import requests


def check(name: str, ok: bool, detail: str) -> bool:
    print(f"{'PASS' if ok else 'FAIL'}  {name}" + ("" if ok else f" — {detail}"))
    return ok


def main(base: str) -> int:
    base = base.rstrip("/")
    speak = requests.post(f"{base}/api/speak", json={"text": "Так.", "part": 0}, timeout=60)
    results = [check("POST /api/speak без cookie → 401", speak.status_code == 401, str(speak.status_code))]
    for script in ("/speak.js", "/player.js"):
        resp = requests.get(f"{base}{script}", allow_redirects=False, timeout=60)
        location = urlparse(resp.headers.get("location", "")).path
        results.append(
            check(
                f"GET {script} без cookie → 302 на /auth/login (маршрут є; невідомий — 404)",
                resp.status_code == 302 and location == "/auth/login",
                f"{resp.status_code} {resp.headers.get('location')}",
            )
        )
    failed = results.count(False)
    print("SMOKE PASSED" if failed == 0 else f"SMOKE FAILED: {failed} of {len(results)}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
