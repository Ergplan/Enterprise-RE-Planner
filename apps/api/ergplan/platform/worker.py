"""The run worker (compose service `worker`): takes queued runs one at a time and solves them.
`python -m ergplan.platform.worker` runs forever; `--once` drains the queue and exits."""

from __future__ import annotations

import argparse
import logging
import time

from .runs import claim_next, execute

log = logging.getLogger("ergplan.worker")


def drain() -> int:
    n = 0
    while (run_id := claim_next()) is not None:
        status = execute(run_id)
        log.info("run %s: %s", run_id, status)
        n += 1
    return n


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--poll", type=float, default=2.0)
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    if args.once:
        drain()
        return
    while True:
        if drain() == 0:
            time.sleep(args.poll)


if __name__ == "__main__":
    main()
