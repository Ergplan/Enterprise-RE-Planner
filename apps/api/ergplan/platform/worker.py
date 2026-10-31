"""The run worker (compose service `worker`): takes queued runs one at a time and solves them.
`python -m ergplan.platform.worker` runs forever; `--once` drains the queue and exits."""

from __future__ import annotations

import argparse
import logging
import multiprocessing as mp
import time

from ..core.settings import get_settings
from .runs import claim_next, execute

log = logging.getLogger("ergplan.worker")


def drain() -> int:
    n = 0
    while (run_id := claim_next()) is not None:
        status = execute(run_id)
        log.info("run %s: %s", run_id, status)
        n += 1
    return n


def loop(poll: float) -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    while True:
        if drain() == 0:
            time.sleep(poll)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--poll", type=float, default=2.0)
    ap.add_argument(
        "--concurrency",
        type=int,
        default=get_settings().ergplan_worker_concurrency,
        help="runs solved at once (one process each; HiGHS uses one thread per run)",
    )
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    if args.once:
        drain()
        return
    if args.concurrency <= 1:
        loop(args.poll)
        return
    procs = [mp.Process(target=loop, args=(args.poll,), daemon=True) for _ in range(args.concurrency)]
    for p in procs:
        p.start()
    for p in procs:
        p.join()


if __name__ == "__main__":
    main()
