"""Disputed catch-up test of the slice access-shell: the smoke script and `Cache-Control` on `/`.

Depends on question Q1 of the hand-in: the smoke runs without signing in, so the only `/` it can see is
the 302 to `/auth/login`. This test takes the reading that «Cache-Control: no-cache на / і статиці»
makes the smoke check the header on that 302. Not sealed until the slice planner answers.
"""

from tests.test_smoke_script import (
    Deployment,
    Headers,
    deployment,
    on,
    replace_header,
    run_smoke,
)

__all__ = ["deployment"]


def test_smoke_fails_when_root_redirect_lacks_no_cache(deployment: Deployment) -> None:
    def no_header(
        request: dict[str, str], status: int, headers: Headers, body: bytes
    ) -> tuple[int, Headers, bytes]:
        return status, replace_header(headers, "cache-control", lambda _: None), body

    assert run_smoke(deployment, on(lambda p: p == "/", no_header)) != 0
