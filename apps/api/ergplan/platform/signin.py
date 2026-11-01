"""Issue a one-time sign-in link from the server (for a server without a mail account, or to let
someone in at once). Run by the operator, who hands the link over:

    docker compose -f docker/compose.yaml -f docker/compose.mini.yaml exec api \
        python -m ergplan.platform.signin someone@company.in

The link works once, for 15 minutes; analysts are emails at ERGPLAN_ANALYST_DOMAIN or listed in
ERGPLAN_ANALYST_EMAILS, exactly as with a mailed link."""

from __future__ import annotations

import argparse

from pydantic import ValidationError

from .routers.auth import RequestIn, issue_link


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="ergplan.platform.signin")
    ap.add_argument("email")
    ap.add_argument("--next", default="/plan/intake")
    a = ap.parse_args(argv)
    try:
        body = RequestIn(email=a.email, next=a.next)  # the same checks as the web form
    except ValidationError:
        ap.error(f"not an email address and path: {a.email} {a.next}")
    print(issue_link(body.email, body.next, actor="operator"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
