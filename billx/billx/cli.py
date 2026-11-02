"""The `billx` command. Each subcommand lives with the code it drives; this file only parses
arguments. Everything that reads a bill goes through billx.reader.pipeline.read_file."""

import argparse
import json
import sys
from decimal import Decimal
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="billx")
    sub = parser.add_subparsers(dest="command", required=True)

    synth = sub.add_parser("synth", help="write synthetic bills with known values")
    synth.add_argument("--out", default="out/synth")
    synth.add_argument("--seed", type=int, default=1)
    synth.add_argument(
        "--planted",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="also write the planted-misread variants and misread fixtures (default on)",
    )

    studio = sub.add_parser("studio", help="run the confirmation studio on 127.0.0.1")
    studio.add_argument("--workspace", default=None)
    studio.add_argument("--port", type=int, default=8750)

    extract = sub.add_parser("extract", help="read bills: one JSON result per file")
    extract.add_argument("paths", nargs="+")
    extract.add_argument("--allow-cloud-model", action="store_true")
    extract.add_argument("--max-cost-usd", default="0")
    extract.add_argument("--contract", choices=["1.0", "1.1"], default="1.1")
    extract.add_argument("--out", default=None, help="write <stem>.billx.json files here")

    validate = sub.add_parser("validate", help="re-run the checks on saved results")
    validate.add_argument("paths", nargs="+")

    ev = sub.add_parser("eval", help="run the engine over a set with truth and report")
    ev.add_argument("--synthetic", default=None, help="a folder written by `billx synth`")
    ev.add_argument("--golden", action="store_true", help="the confirmed golden manifest")
    ev.add_argument(
        "--unconfirmed", default=None, help="survey a folder of real bills: statuses only"
    )
    ev.add_argument("--allow-cloud-model", action="store_true")
    ev.add_argument("--max-cost-usd", default="0")
    ev.add_argument("--report", default=None, help="write the markdown report here")

    ex = sub.add_parser("examples", help="write contract/examples from a synthetic set")
    ex.add_argument("--synthetic", required=True, help="a folder written by `billx synth --seed 1`")

    oa = sub.add_parser("openapi", help="write contract/openapi.json from the app")
    oa.add_argument("--out", default="contract/openapi.json")
    oa.add_argument("--check", action="store_true", help="exit 1 when the file is stale")

    serve = sub.add_parser("serve", help="run the HTTP API (contract 1.0 / 1.1)")
    serve.add_argument("--host", default="0.0.0.0")
    serve.add_argument("--port", type=int, default=8080)

    args = parser.parse_args(argv)
    if args.command == "serve":
        return _serve(args)
    if args.command == "openapi":
        from billx.platform.api.openapi import write_openapi

        changed = write_openapi(Path(args.out), check=args.check)
        if args.check:
            print("contract/openapi.json is " + ("stale" if changed else "current"))
            return 1 if changed else 0
        print(f"billx openapi: wrote {args.out}")
        return 0
    if args.command == "examples":
        from billx.platform.api.examples import write_examples

        written = write_examples(Path(args.synthetic))
        print(f"billx examples: {len(written)} examples written under contract/examples/")
        return 0
    if args.command == "synth":
        from billx.platform.synth.cli import run

        return run(args)
    if args.command == "studio":
        from billx.platform.studio.cli import run

        return run(args)
    if args.command == "extract":
        return _extract(args)
    if args.command == "validate":
        return _validate(args)
    if args.command == "eval":
        return _eval(args)
    return 2


def _serve(args) -> int:
    import uvicorn

    from billx.platform.api.app import ApiSettings, create_app

    logging_config = {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {"json": {"()": "billx.platform.api.logging.JsonFormatter"}},
        "handlers": {"stdout": {"class": "logging.StreamHandler", "formatter": "json"}},
        "root": {"level": "INFO", "handlers": ["stdout"]},
    }
    settings = ApiSettings.from_env()
    app = create_app(settings)
    print(f"billx serve: mode {settings.mode} on {args.host}:{args.port}")
    uvicorn.run(app, host=args.host, port=args.port, log_config=logging_config)
    return 0


def _providers():
    from billx.reader.providers.base import make_model_a, make_model_b

    return make_model_a(), make_model_b()


def _third():
    from billx.reader.providers.base import make_model_c

    return make_model_c()


def _extract(args) -> int:
    from billx.reader.pipeline import ReadError, read_file

    model_a, model_b = _providers() if args.allow_cloud_model else (None, None)
    model_c = _third() if args.allow_cloud_model else None
    out_dir = Path(args.out) if args.out else None
    if out_dir:
        out_dir.mkdir(parents=True, exist_ok=True)
    failures = 0
    for p in args.paths:
        path = Path(p)
        try:
            env = read_file(
                path,
                allow_cloud_model=args.allow_cloud_model,
                max_cost_usd=Decimal(args.max_cost_usd),
                model_a=model_a,
                model_b=model_b,
                model_c=model_c,
                contract=args.contract,
            )
        except ReadError as exc:
            print(f"{path.name}: {exc.code}", file=sys.stderr)
            failures += 1
            continue
        text = env.model_dump_json(indent=1)
        if out_dir:
            (out_dir / f"{path.stem}.billx.json").write_text(text, encoding="utf-8")
            bill = env.bills[0]
            print(f"{path.name}: {bill.status} route={bill.route} checks={len(bill.checks)}")
        else:
            print(text)
    return 1 if failures else 0


def _validate(args) -> int:
    from billx.core.schema import Envelope
    from billx.reader.validate.formula import run_checks
    from billx.reader.validate.registry import CheckContext

    for p in args.paths:
        env = Envelope.model_validate_json(Path(p).read_text(encoding="utf-8"))
        for bill in env.bills:
            if bill.data is None:
                print(f"{p}: bill {bill.index} has no data")
                continue
            results = run_checks(bill.data, CheckContext(version=None))
            counts = {}
            for r in results:
                counts[r.status] = counts.get(r.status, 0) + 1
            print(
                f"{p}: bill {bill.index} " + " ".join(f"{k}={v}" for k, v in sorted(counts.items()))
            )
            for r in results:
                if r.status in ("fail", "warn"):
                    print(f"  {r.status} {r.id}: {r.description}")
    return 0


def _eval(args) -> int:
    from billx.platform.evals.runner import evaluate_golden, evaluate_synthetic, write_report
    from billx.reader.pipeline import read_file

    model_a, model_b = _providers() if args.allow_cloud_model else (None, None)
    model_c = _third() if args.allow_cloud_model else None

    def reader(path, **kw):
        return read_file(path, model_a=model_a, model_b=model_b, model_c=model_c, **kw)

    kw = dict(allow_cloud_model=args.allow_cloud_model, max_cost_usd=Decimal(args.max_cost_usd))
    if args.unconfirmed:
        from billx.platform.evals.survey import render, survey

        groups = survey(Path(args.unconfirmed), reader, **kw)
        text = render(groups)
        if args.report:
            Path(args.report).write_text(text, encoding="utf-8")
            print(f"report: {args.report}")
        else:
            print(text)
        return 0
    if args.synthetic:
        result = evaluate_synthetic(Path(args.synthetic), reader, **kw)
    elif args.golden:
        result = evaluate_golden(reader, **kw)
    else:
        print("give --synthetic DIR or --golden", file=sys.stderr)
        return 2
    print(json.dumps(result.summary(), indent=1, default=str))
    if args.report:
        write_report(result, Path(args.report))
        print(f"report: {args.report}")
    return 0 if result.ok() else 1


if __name__ == "__main__":
    sys.exit(main())
