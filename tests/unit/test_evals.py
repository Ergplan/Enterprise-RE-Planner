"""`billx eval`: silent errors, refusals, planted misreads, the rule of three, and a report
with no value in it, proven on hand-built Envelopes and a fake read_file."""

import json
from decimal import Decimal
from pathlib import Path

import pytest

from billx.core.normalize import normalise
from billx.core.schema import (
    BillResult,
    CheckResult,
    Element,
    Envelope,
    FileInfo,
    FormulaRecheck,
    Reading,
    UsageRecord,
    make_value,
)
from billx.platform.evals import (
    evaluate_golden,
    evaluate_synthetic,
    load_golden,
    load_synthetic,
    render_markdown,
    rule_of_three,
    run,
    summary,
    write_report,
)
from billx.platform.evals.manifest import EvalCase
from billx.platform.synth.cli import build

TRUTH = {
    "utility.name": "AVVNL",
    "consumer.account_number": "991234567890",
    "meter.number": None,
    "period.from": "2025-04-01",
    "period.to": "2025-04-30",
    "period.bill_month": "2025-04",
    "energy.kwh": "2477850.00",
    "totals.net_payable": "25230114.71",
}
PRINTED = {
    "utility.name": "AVVNL",
    "consumer.account_number": "991234567890",
    "period.from": "01-04-2025",
    "period.to": "30-04-2025",
    "period.bill_month": "APR-2025",
    "energy.kwh": "24,77,850.00",
    "totals.net_payable": "2,52,30,114.71",
}
TYPES = {
    "utility.name": "text",
    "consumer.account_number": "identifier",
    "meter.number": "identifier",
    "period.from": "date",
    "period.to": "date",
    "period.bill_month": "month",
    "energy.kwh": "number",
    "totals.net_payable": "number",
}


# builders ------------------------------------------------------------------------------------


def reading(reader: str, raw: str, field_type: str) -> Reading:
    method = {"text_layer": "text_layer", "local_ocr": "ocr", "model_a": "vision"}[reader]
    fam = "openai" if reader == "model_a" else None
    return Reading(
        reader=reader, method=method, family=fam, raw=raw, normalised=normalise(raw, field_type)
    )


def value(path: str, raw: str, *, verified: bool = True, checks=()):
    """Two independent readers agreeing make it verified; one reading leaves it unverified."""
    readers = ("text_layer", "model_a") if verified else ("text_layer",)
    return make_value(
        path, TYPES[path], tuple(reading(r, raw, TYPES[path]) for r in readers), checks=checks
    )


def fields(wrong: dict | None = None, unverified: set | None = None):
    out = []
    for path, printed in PRINTED.items():
        raw = (wrong or {}).get(path, printed)
        out.append(value(path, raw, verified=path not in (unverified or set())))
    return tuple(out)


def check(id: str, status: str) -> CheckResult:
    return CheckResult(
        id=id, description=id, status=status, detects="one digit", equality=True, paths=()
    )


def element(status: str) -> Element:
    return Element(
        index=0,
        label="Energy Charges",
        kind="item",
        stage="current",
        code="energy_charge",
        amount=value("totals.net_payable", "1"),
        formula_recheck=FormulaRecheck(
            status=status, reason=None if status != "not_computable" else "x"
        ),
    )


def bill(
    document_type="electricity_bill",
    status="passed",
    *,
    fields=(),
    checks=(),
    elements=(),
    route="template",
    unread_reason=None,
) -> BillResult:
    passed = status == "passed"
    return BillResult(
        index=0,
        pages=(1,),
        bill_type="electricity" if document_type == "electricity_bill" else None,
        document_type=document_type,
        route=route,
        fields=fields,
        checks=checks,
        elements=elements,
        passed=passed,
        status=status,
        accepted=passed,
        accepted_by="engine" if passed else None,
        unread_reason=unread_reason,
    )


def envelope(*bills: BillResult, cost: Decimal = Decimal(0)) -> Envelope:
    usage = ()
    if cost:
        usage = (
            UsageRecord(
                provider="openai",
                model="m",
                purpose="read",
                input_tokens=1,
                output_tokens=1,
                cost_usd=cost,
            ),
        )
    return Envelope(
        contract_version="esgos-1.1",
        file=FileInfo(sha256="0" * 64, pages=1, media_type="application/pdf"),
        bills=bills,
        usage=usage,
        seconds=Decimal("0.1"),
    )


def case(id, document_type="electricity_bill", *, planted=None, input_kind="digital_pdf"):
    from billx.platform.evals.manifest import Planted

    return EvalCase(
        id=id,
        path=Path("/nowhere") / id,
        document_type=document_type,
        layout="avvnl-ht-synth-v1" if document_type == "electricity_bill" else "letter-synth-v1",
        input_kind=input_kind,
        truth=dict(TRUTH) if document_type == "electricity_bill" else {},
        planted=Planted(check=planted, path="totals.net_payable", kind="printed_inconsistency")
        if planted
        else None,
    )


def fake(envelopes: dict[str, Envelope]):
    """A read_file with the integrator's signature, answering by file name."""

    def read_file(
        path: Path, *, allow_cloud_model: bool, max_cost_usd: Decimal, model_a=None, model_b=None
    ):
        result = envelopes[path.name]
        if isinstance(result, Exception):
            raise result
        return result

    return read_file


def evaluate(pairs):
    """`pairs`: (EvalCase, Envelope or Exception) in run order."""
    pairs = list(pairs)
    return run(
        [c for c, _ in pairs],
        fake({c.id: e for c, e in pairs}),
        allow_cloud_model=False,
        max_cost_usd=Decimal(0),
        set_name="hand-built",
        date="2026-10-12",
    )


# the metrics ----------------------------------------------------------------------------------


def test_a_correct_passed_bill_has_no_silent_error():
    r = evaluate([(case("ok.pdf"), envelope(bill(fields=fields())))])
    t = r.metrics.total
    assert (t.n, t.bills, t.passed, t.silent_errors, t.false_refusals) == (1, 1, 1, 0, 0)
    assert t.coverage == Decimal("1.0000")
    assert t.silent_error_bound == Decimal(3)  # 3/n with n = 1
    acc = t.field_accuracy()
    assert set(acc) == set(PRINTED) and all(c == n == 1 for c, n, _ in acc.values())
    assert list(r.metrics.groups) == [("avvnl-ht-synth-v1", "digital_pdf", "template")]


def test_a_wrong_verified_field_on_a_passed_bill_is_a_silent_error():
    wrong = fields(wrong={"totals.net_payable": "2,52,30,174.71"})
    r = evaluate([(case("bad.pdf"), envelope(bill(fields=wrong)))])
    t = r.metrics.total
    assert t.silent_errors == 1
    assert t.silent_error_paths == [("bad.pdf", "totals.net_payable")]
    assert t.silent_error_bound is None  # no bound once an error was seen
    assert t.field_accuracy()["totals.net_payable"] == (0, 1, Decimal("0.0000"))
    assert t.field_accuracy()["energy.kwh"] == (1, 1, Decimal("1.0000"))


def test_an_unverified_wrong_field_on_a_needs_review_bill_is_not_a_silent_error():
    wrong = fields(
        wrong={"totals.net_payable": "2,52,30,174.71"}, unverified={"totals.net_payable"}
    )
    assert wrong[-1].verification == "unverified"
    r = evaluate([(case("review.pdf"), envelope(bill(status="needs_review", fields=wrong)))])
    t = r.metrics.total
    assert (t.silent_errors, t.passed, t.needs_review, t.false_refusals) == (0, 0, 1, 0)
    assert t.coverage == Decimal("0.0000")
    assert t.field_accuracy() == {}  # accuracy is over passed bills only


def test_a_non_bill_refused_is_a_correct_refusal():
    letter = bill("not_a_bill", "not_a_bill", unread_reason="not_a_bill")
    r = evaluate([(case("letter.pdf", "not_a_bill"), envelope(letter))])
    t = r.metrics.total
    assert (t.non_bills, t.correct_refusals, t.false_refusals, t.bills) == (1, 1, 0, 0)
    assert t.non_bills_read_as_bills == 0


def test_a_non_bill_read_as_a_bill_is_counted():
    r = evaluate([(case("letter.pdf", "not_a_bill"), envelope(bill(fields=fields())))])
    t = r.metrics.total
    assert (t.correct_refusals, t.non_bills_read_as_bills) == (0, 1)
    assert t.non_bills_read_as_bills_ids == ["letter.pdf"]


def test_a_bill_refused_or_classed_as_another_type_is_a_false_refusal():
    refused = bill("electricity_bill", "not_a_bill", unread_reason="not_a_bill")
    as_gas = bill("gas_bill", "passed", fields=())
    empty = envelope()
    r = evaluate(
        [
            (case("refused.pdf"), envelope(refused)),
            (case("gas.pdf"), envelope(as_gas)),
            (case("empty.pdf"), empty),
        ]
    )
    t = r.metrics.total
    assert t.false_refusals == 3
    assert t.false_refusal_ids == ["refused.pdf", "gas.pdf", "empty.pdf"]
    assert t.passed == 0 and t.silent_errors == 0


def test_a_declined_bill_is_neither_a_refusal_nor_passed():
    declined = bill("electricity_bill", "model_not_allowed", unread_reason="model_not_allowed")
    r = evaluate([(case("scan.pdf", input_kind="scan_pdf"), envelope(declined))])
    t = r.metrics.total
    assert (t.declined, t.false_refusals, t.passed, t.bills) == (1, 0, 0, 1)


def test_a_planted_case_is_caught_only_when_the_declared_check_fails():
    caught = envelope(bill(status="passed", fields=fields(), checks=(check("G09", "fail"),)))
    missed = envelope(bill(status="passed", fields=fields(), checks=(check("G09", "pass"),)))
    other = envelope(bill(status="needs_review", fields=fields(), checks=(check("G07", "fail"),)))
    r = evaluate(
        [
            (case("a.planted-G09.pdf", planted="G09"), caught),
            (case("b.planted-G09.pdf", planted="G09"), missed),
            (case("c.planted-G09.pdf", planted="G09"), other),
        ]
    )
    t = r.metrics.total
    assert (t.planted, t.planted_caught, t.planted_missed) == (3, 1, 2)
    assert t.planted_missed_ids == [("b.planted-G09.pdf", "G09"), ("c.planted-G09.pdf", "G09")]
    assert r.metrics.all_planted_caught is False
    # planted cases take part in no other metric
    assert (t.bills, t.passed, t.silent_errors, t.false_refusals) == (0, 0, 0, 0)


def test_formula_coverage_cost_and_time():
    e = envelope(
        bill(
            fields=fields(),
            elements=(element("match"), element("differs"), element("not_computable")),
        ),
        cost=Decimal("0.0123"),
    )
    r = evaluate([(case("x.pdf"), e), (case("y.pdf"), envelope(bill(fields=fields())))])
    t = r.metrics.total
    assert (t.elements, t.elements_computable) == (3, 2)
    assert t.formula_coverage == Decimal("0.6667")
    assert t.cost_p95 == Decimal("0.0123") and t.cost_median == Decimal("0.0062")
    assert t.seconds_median is not None and t.seconds_p95 >= t.seconds_median
    assert all(isinstance(x, Decimal) for x in (t.cost_median, t.cost_p95, t.seconds_p95))


def test_an_engine_exception_is_recorded_by_class_only():
    r = evaluate([(case("boom.pdf"), RuntimeError("secret value 2,52,30,114.71"))])
    t = r.metrics.total
    assert (t.errors, t.bills, t.passed, t.false_refusals) == (1, 1, 0, 0)
    assert t.error_ids == [("boom.pdf", "RuntimeError")]
    assert r.results[0].envelope is None and r.results[0].error == "RuntimeError"
    text = render_markdown(r)
    assert "RuntimeError" in text and "secret" not in text and "2,52,30,114.71" not in text


def test_rule_of_three():
    assert rule_of_three(0) is None
    assert rule_of_three(1) == Decimal(3)
    assert rule_of_three(30) == Decimal("0.1")
    assert rule_of_three(7) == Decimal("0.4286")  # rounded up: an upper bound
    r = evaluate([(case(f"b{i}.pdf"), envelope(bill(fields=fields()))) for i in range(12)])
    assert r.metrics.total.passed == 12
    assert r.metrics.total.silent_error_bound == Decimal("0.25")
    assert "0.25" in render_markdown(r) and "in 12 passed bills" in render_markdown(r)


# the report -----------------------------------------------------------------------------------


def _no_float(s):
    raise AssertionError(f"float in the JSON summary: {s}")


def test_report_has_counts_and_paths_but_no_values(tmp_path):
    wrong = fields(wrong={"totals.net_payable": "2,52,30,174.71"})
    r = evaluate(
        [
            (case("bad.pdf"), envelope(bill(fields=wrong), cost=Decimal("0.5"))),
            (case("letter.pdf", "not_a_bill"), envelope(bill("not_a_bill", "not_a_bill"))),
        ]
    )
    md, js = write_report(r, tmp_path / "2026-10-12-hand-built.md")
    text = md.read_text()
    assert text.startswith("# billx eval: hand-built\n")
    assert "- Date: 2026-10-12" in text and "- Engine version:" in text
    assert "unmeasured" not in text  # a synthetic set
    assert "bad.pdf: totals.net_payable" in text
    for s in list(PRINTED.values()) + [v for v in TRUTH.values() if v] + ["2,52,30,174.71"]:
        assert s not in text, s
        assert s not in js.read_text(), s
    assert "25230114.71" not in text and "2477850" not in text
    data = json.loads(js.read_text(), parse_float=_no_float)
    assert data["total"]["silent_errors"] == 1
    assert data["total"]["silent_error_paths"] == [
        {"case": "bad.pdf", "path": "totals.net_payable"}
    ]
    assert data["total"]["correct_refusals"] == 1
    assert data["total"]["cost_usd"]["p95"] == "0.5000"
    assert data["unmeasured"] is False and data["set_kind"] == "synthetic"
    assert len(data["groups"]) == 2
    assert summary(r) == data == r.summary()
    assert r.markdown() == text
    assert r.ok() is False  # one silent error


def test_golden_report_is_unmeasured_and_names_no_file(tmp_path):
    manifest = tmp_path / "manifest.jsonl"
    sha = "ab" * 32
    entries = [
        {
            "sha256": sha,
            "source_path": "unconfirmed/avvnl/Real Consumer Name bill.pdf",
            "layout_id": "avvnl-2025",
            "input_kind": "scan",
            "bill_kind": "electricity",
            "fields": {"totals.net_payable": "1", "meter.number": "not_printed"},
        },
        {
            "sha256": sha,
            "source_path": "unconfirmed/avvnl/Real Consumer Name bill.pdf",
            "layout_id": "avvnl-2025",
            "input_kind": "scan",
            "bill_kind": "electricity",
            "fields": {"totals.net_payable": "2,52,30,114.71", "meter.number": "not_printed"},
        },
    ]
    manifest.write_text("\n".join(json.dumps(e) for e in entries) + "\n")
    cases = load_golden(manifest, root=tmp_path)
    assert len(cases) == 1  # the latest entry per sha256 wins
    c = cases[0]
    assert c.id == sha[:12] and c.set_kind == "golden" and c.input_kind == "scan_pdf"
    assert c.truth == {"totals.net_payable": "2,52,30,114.71", "meter.number": None}
    assert c.path == tmp_path / "unconfirmed/avvnl/Real Consumer Name bill.pdf"

    def read_file(path, *, allow_cloud_model, max_cost_usd, model_a=None, model_b=None):
        return envelope(bill(fields=(value("totals.net_payable", "2,52,30,114.71"),)))

    r = evaluate_golden(read_file, manifest=manifest, root=tmp_path, date="2026-10-12")
    text = render_markdown(r)
    assert text.startswith("# billx eval: golden (unmeasured)")
    assert "**unmeasured**" in text
    assert "Real Consumer" not in text and "2,52,30,114.71" not in text
    assert r.metrics.total.silent_errors == 0 and r.metrics.total.passed == 1 and r.ok()
    assert r.results[0].case.id == sha[:12]

    def refuse(path, *, allow_cloud_model, max_cost_usd, model_a=None, model_b=None):
        return envelope(bill("electricity_bill", "unreadable", unread_reason="unreadable"))

    r = evaluate_golden(refuse, manifest=manifest, root=tmp_path, date="2026-10-12")
    text = render_markdown(r)
    assert r.metrics.total.false_refusals == 1 and not r.ok()
    assert sha[:12] in text and "Real Consumer" not in text and "bill.pdf" not in text


# the synthetic set end to end ---------------------------------------------------------------


@pytest.fixture(scope="module")
def synth(tmp_path_factory) -> Path:
    d = tmp_path_factory.mktemp("synth")
    build(d, 1)
    return d


def _truth_reader(folder: Path, *, catch: bool):
    """A fake engine that answers from the truth files: a passed bill with every printed
    field verified for a bill, a refusal for anything else, and for a planted file the
    declared check failing (when `catch`)."""
    from billx.platform.evals.manifest import load_json
    from billx.platform.synth.values import field_types

    types = {k: field_types(k) for k in ("electricity", "gas")}

    def read_file(path: Path, *, allow_cloud_model, max_cost_usd, model_a=None, model_b=None):
        t = load_json(folder / (path.name.rsplit(".", 1)[0] + ".truth.json"))
        if t["document_type"] not in ("electricity_bill", "gas_bill"):
            return envelope(
                bill("not_a_bill", "not_a_bill", unread_reason="not_a_bill", route="none")
            )
        kind = "electricity" if t["document_type"] == "electricity_bill" else "gas"
        vals = tuple(
            make_value(
                p,
                types[kind][p],
                (reading("text_layer", s, types[kind][p]), reading("local_ocr", s, types[kind][p])),
            )
            for p, s in t["printed"].items()
        )
        checks = ()
        if "planted" in t:
            checks = (check(t["planted"]["check"], "fail" if catch else "pass"),)
        route = "template" if t["input_kind"] == "digital_pdf" else "local_model"
        return envelope(bill(t["document_type"], fields=vals, checks=checks, route=route))

    return read_file


def test_evaluate_synthetic_end_to_end(synth, tmp_path):
    cases = load_synthetic(synth)
    assert len(cases) == 90 and sum(c.planted is not None for c in cases) == 48
    assert {c.input_kind for c in cases} == {"digital_pdf", "scan_pdf", "photo_jpeg"}
    r = evaluate_synthetic(synth, _truth_reader(synth, catch=True), date="2026-10-12")
    t = r.metrics.total
    assert r.set_name == "synthetic-seed-1"
    assert (t.n, t.planted, t.planted_caught, t.planted_missed) == (90, 48, 48, 0)
    assert t.silent_errors == 0 and t.false_refusals == 0 and t.non_bills_read_as_bills == 0
    assert t.bills == 28 + 4 and t.passed == 32 and t.coverage == Decimal("1.0000")
    assert t.correct_refusals == 10
    assert r.metrics.all_planted_caught and r.ok()
    keys = set(r.metrics.groups)
    assert ("avvnl-ht-synth-v1", "digital_pdf", "template") in keys
    assert ("pvvnl-hv2-synth-v1", "photo_jpeg", "local_model") in keys
    assert ("letter-synth-v1", "digital_pdf", "none") in keys
    md, js = write_report(r, tmp_path / "report.md")
    text = md.read_text()
    truth = json.loads((synth / "avvnl-ht-synth-v1_01.digital.truth.json").read_text())
    assert truth["fields"]["totals.net_payable"] not in text
    assert truth["printed"]["totals.net_payable"] not in text
    assert "Planted misreads: 48 caught, 0 missed" in text
    json.loads(js.read_text(), parse_float=_no_float)

    missed = evaluate_synthetic(synth, _truth_reader(synth, catch=False), date="2026-10-12")
    assert missed.metrics.total.planted_missed == 48
    assert not missed.metrics.all_planted_caught and not missed.ok()
    assert (
        "avvnl-ht-synth-v1_01.planted-G16.pdf",
        "G16",
    ) in missed.metrics.total.planted_missed_ids
