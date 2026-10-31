from decimal import Decimal

import pytest
from pydantic import ValidationError

from ergplan.core.sourced import RefKind, SourcedValue, SourceRef, assumed, derive, stated
from ergplan.core.units import Unit

REF = SourceRef(kind=RefKind.ORDER, document_id="doc-1", page=352, quote="Energy Charge Rs 7.10/kVAh")


def test_rejects_empty_source_refs() -> None:
    with pytest.raises(ValidationError):
        SourcedValue(value=Decimal("1"), unit=Unit.INR_PER_KWH, source_refs=())


def test_rejects_float_value() -> None:
    with pytest.raises(ValidationError):
        SourcedValue(value=7.1, unit=Unit.INR_PER_KWH, source_refs=(REF,))  # type: ignore[arg-type]


def test_accepts_printed_string_and_serialises_as_string() -> None:
    sv = SourcedValue(value="7.10", unit=Unit.INR_PER_KWH, source_refs=(REF,))  # type: ignore[arg-type]
    assert sv.value == Decimal("7.10")
    assert sv.model_dump(mode="json")["value"] == "7.10"


def test_order_ref_requires_document_page_and_quote() -> None:
    with pytest.raises(ValidationError):
        SourceRef(kind=RefKind.ORDER, document_id="doc-1", page=3)
    with pytest.raises(ValidationError):
        SourceRef(kind=RefKind.REGULATION, page=3, quote="x")


def test_ref_url_opens_pdf_at_page() -> None:
    assert REF.url == "/documents/doc-1#page=352"
    assert REF.to_json()["url"] == "/documents/doc-1#page=352"


def test_derive_carries_every_input_ref_once() -> None:
    other = SourceRef(kind=RefKind.REGULATION, document_id="doc-2", page=14, quote="banking 8%")
    a = SourcedValue(value=Decimal("2"), unit=Unit.INR_PER_KWH, source_refs=(REF,))
    b = SourcedValue(value=Decimal("3"), unit=Unit.INR_PER_KWH, source_refs=(other, REF))
    d = derive(a.value + b.value, Unit.INR_PER_KWH, [a, b])
    assert d.source_refs == (REF, other)
    assert d.is_sourced


def test_stated_and_assumed_are_not_sourced() -> None:
    assert not stated("1000", Unit.KVA).is_sourced
    a = assumed("0.95", Unit.RATIO, note="normative power factor")
    assert a.source_refs[0].kind == RefKind.ASSUMPTION
    assert not a.is_sourced


def test_bill_and_measured_refs_count_as_sourced() -> None:
    bill = SourceRef(kind=RefKind.BILL, bill_id="b", field_path="energy.kwh", page=2)
    assert bill.url == "/bills/b/file#page=2"
    assert SourcedValue(value="1", unit=Unit.KWH, source_refs=(bill,)).is_sourced
    assert SourcedValue(
        value="1", unit=Unit.KW, source_refs=(SourceRef(kind=RefKind.MEASURED, note="meter"),)
    ).is_sourced
    with pytest.raises(ValueError, match="bill ref"):
        SourceRef(kind=RefKind.BILL, bill_id="b")
