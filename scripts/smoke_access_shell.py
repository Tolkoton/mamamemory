"""Smoke S1 access-shell проти розгорнутої адреси (без входу; вхід мамою — S5).

uv run python scripts/smoke_access_shell.py https://mamamemory-2mfebgg56q-ey.a.run.app
"""

import json
import sys
from urllib.parse import parse_qs, urlparse

import requests

SCOPES = {
    "openid",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/calendar.events",
    "https://www.googleapis.com/auth/calendar.readonly",
    "https://www.googleapis.com/auth/tasks",
}


def check(name: str, ok: bool, detail: str = "") -> bool:
    print(f"{'PASS' if ok else 'FAIL'}  {name}" + (f" — {detail}" if detail and not ok else ""))
    return ok


def no_cache(resp: requests.Response) -> bool:
    return "no-cache" in [d.strip().lower() for d in resp.headers.get("cache-control", "").split(",")]


def main(base: str) -> int:
    base = base.rstrip("/")
    results = []
    root = requests.get(f"{base}/", allow_redirects=False, timeout=60)
    results.append(
        check(
            "GET / без cookie → 302 на /auth/login",
            root.status_code == 302 and urlparse(root.headers.get("location", "")).path == "/auth/login",
            f"{root.status_code} {root.headers.get('location')}",
        )
    )
    forged = requests.get(
        f"{base}/", cookies={"mm_session": "forged.value"}, allow_redirects=False, timeout=60
    )
    results.append(
        check("GET / з підробленим cookie → 302", forged.status_code == 302, str(forged.status_code))
    )

    login = requests.get(f"{base}/auth/login", allow_redirects=False, timeout=60)
    target = urlparse(login.headers.get("location", ""))
    query = {k: v[0] for k, v in parse_qs(target.query).items()}
    results.append(
        check(
            "GET /auth/login → 302 на accounts.google.com",
            login.status_code == 302 and target.hostname == "accounts.google.com",
            f"{login.status_code} {target.hostname}",
        )
    )
    results.append(
        check("scope — усі SCOPES", set(query.get("scope", "").split()) == SCOPES, query.get("scope", ""))
    )
    for key, value in [
        ("access_type", "offline"),
        ("prompt", "consent"),
        ("code_challenge_method", "S256"),
        ("redirect_uri", f"{base}/auth/callback"),
    ]:
        results.append(check(f"{key}={value}", query.get(key) == value, str(query.get(key))))
    cookie = next((h for h in login.raw.headers.get_all("Set-Cookie") or [] if h.startswith("mm_login=")), "")
    flags = {p.strip().lower() for p in cookie.split(";")[1:]}
    results.append(
        check(
            "mm_login: Secure; HttpOnly; SameSite=Lax",
            {"secure", "httponly", "samesite=lax"} <= flags,
            cookie.split(";", 1)[-1],
        )
    )

    manifest = requests.get(f"{base}/manifest.webmanifest", timeout=60)
    body = json.loads(manifest.text) if manifest.ok else {}
    sizes = {s for icon in body.get("icons", []) for s in str(icon.get("sizes", "")).split()}
    results.append(
        check(
            "маніфест: name, start_url, display standalone, значки 192 і 512",
            manifest.ok
            and bool(body.get("name"))
            and bool(body.get("start_url"))
            and body.get("display") == "standalone"
            and {"192x192", "512x512"} <= sizes,
        )
    )
    results.append(check("Cache-Control: no-cache на маніфесті", no_cache(manifest)))
    icon = requests.get(f"{base}/static/icon-192.png", timeout=60)
    results.append(check("значок 192 без сесії, no-cache", icon.ok and no_cache(icon), str(icon.status_code)))
    results.append(check("Cache-Control: no-cache на /", no_cache(root)))

    passed = all(results)
    print("\nSMOKE", "PASSED" if passed else "FAILED")
    print(
        "Далі вручну (S5): відкрийте адресу на маминому телефоні, увійдіть її акаунтом —"
        " має відкритися оболонка;"
        " інший акаунт — «Цей акаунт не має доступу.»."
    )
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
