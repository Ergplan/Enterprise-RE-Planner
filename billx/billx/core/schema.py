"""Core schema 2.0 (build prompt Stage 1.1): the one data contract the three engines share.

Pydantic v2, strict, `extra="forbid"`, `Decimal` for every amount, quantity and rate (never a
float), frozen results. Value and evidence are separate: a `Value` carries its readings and
proof levels, and its `verification`, `value`, `proof`, `readers` and `source` are exactly
what `billx.core.proof.decide` returns for that evidence; a model validator recomputes them
and rejects a mismatch, so no code path can mark a value verified by hand (invariants 0
and 1).

`Bill` is the engine's own transcription (Developer Guide section 5); the contract's field
objects are produced from the `Value`s. `BillResult` and `Envelope` are what the API modes
render from.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, model_validator

from billx.core.normalize import FieldType
from billx.core.proof import (
    PROOF_RULE_VERSION,
    Decision,
    Method,
    ProofLevel,
    Reader,
    ReadingView,
    Source,
    Verification,
    decide,
)

SCHEMA_VERSION = "2.0"
ENGINE_VERSION = "0.2.1"

Unit = Literal["kWh", "kVAh", "kVArh", "kW", "kVA", "SCM", "MMBtu", "kcal/SCM", "INR", "%", "days"]
BillType = Literal["electricity", "gas"]
DocumentType = Literal[
    "electricity_bill", "gas_bill", "water_bill", "telecom_bill", "other_invoice", "not_a_bill"
]
Route = Literal["template", "local_model", "cloud_model", "none"]
UnreadReason = Literal["model_not_allowed", "budget_exceeded", "unreadable", "not_a_bill"]
ProfileStatus = Literal["final", "draft", "none"]
CheckStatus = Literal["pass", "fail", "warn", "skip"]
Status = Literal[
    "passed",
    "confirmed",
    "needs_review",
    "unreadable",
    "not_a_bill",
    "wrong_document_type",
    "model_not_allowed",
    "budget_exceeded",
]
AuditStatus = Literal["not_audited", "audited", "partially_audited"]
LineKind = Literal["item", "subtotal", "info"]
LineStage = Literal["current", "arrear", "adjustment"]
MeterQuantity = Literal["kWh", "kVAh", "kVA", "kW", "kVArh", "other"]
ReadingType = Literal["actual", "estimated", "assessed", "provisional"]
BillKind = Literal["regular", "revised", "supplementary", "final"]


class Strict(BaseModel):
    """Every model: no extra keys, no coercion (a float or a str never becomes a Decimal)."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)


# evidence ---------------------------------------------------------------------------------


class Region(Strict):
    """Fractions of the page's width and height, from the top left."""

    x: Decimal
    y: Decimal
    w: Decimal
    h: Decimal


class Reading(Strict):
    """One reader's attempt at one field: what it saw (`raw`) and the normalised string that
    is compared with other readers'. `normalised` is None when `raw` could not be read as
    the field's type."""

    reader: Reader
    method: Method
    family: str | None = None
    model_id: str | None = None
    prompt_version: str | None = None
    raw: str
    normalised: str | None
    page: int | None = None
    region: Region | None = None
    cost_usd: Decimal = Decimal(0)
    exact: bool = False
    confirmed_by: str | None = None

    def view(self) -> ReadingView:
        return ReadingView(
            self.reader, self.method, self.family, self.normalised, self.exact, self.confirmed_by
        )


class Value(Strict):
    """A guaranteed field or element amount with its evidence and the decision made from it.

    `value` is the normalised value decide() chose (an exact decimal string, an ISO date or
    month, or text), None when not printed or unreadable. `printed` is the text of the first
    agreeing reading, as it appeared on the page.
    """

    path: str
    field_type: FieldType
    unit: Unit | None = None
    value: str | None
    printed: str | None = None
    page: int | None = None
    region: Region | None = None
    source: Source | None = None
    readers: tuple[Reader, ...] = ()
    readings: tuple[Reading, ...] = ()
    checks: tuple[str, ...] = ()  # ids of the passing equality checks this value took part in
    proof: tuple[ProofLevel, ...] = ()
    verification: Verification
    proof_rule_version: str = PROOF_RULE_VERSION

    @model_validator(mode="after")
    def _decided_by_the_rule(self) -> Value:
        d = decide(tuple(r.view() for r in self.readings), self.checks)
        got = (self.verification, self.value, self.proof, self.readers, self.source)
        want = (d.verification, d.value, d.proof, d.readers, d.source)
        if got != want:
            raise ValueError(
                f"{self.path}: verification not decided by the rule "
                f"(proof_rule_version {PROOF_RULE_VERSION})"
            )
        if self.proof_rule_version != PROOF_RULE_VERSION:
            raise ValueError(f"{self.path}: proof_rule_version is not {PROOF_RULE_VERSION}")
        return self


def make_value(
    path: str,
    field_type: FieldType,
    readings: tuple[Reading, ...],
    *,
    unit: Unit | None = None,
    checks: tuple[str, ...] = (),
) -> Value:
    """The only way a Value is built: everything about its verdict comes from decide()."""
    d: Decision = decide(tuple(r.view() for r in readings), checks)
    first = next((r for r in readings if r.normalised == d.value and r.reader != "human"), None)
    if first is None:
        first = next((r for r in readings if r.normalised == d.value), None)
    return Value(
        path=path,
        field_type=field_type,
        unit=unit,
        value=d.value,
        printed=first.raw if first else None,
        page=first.page if first else None,
        region=first.region if first else None,
        source=d.source,
        readers=d.readers,
        readings=readings,
        checks=checks,
        proof=d.proof,
        verification=d.verification,
    )


def with_checks(value: Value, check_ids: tuple[str, ...]) -> Value:
    """A new Value carrying the passing equality checks it took part in (adds `arithmetic`)."""
    return make_value(
        value.path, value.field_type, value.readings, unit=value.unit, checks=tuple(check_ids)
    )


# the transcription (Developer Guide section 5, version 2.0) ----------------------------


class Discom(Strict):
    name_as_printed: str | None = None
    short_code: str | None = None
    state: str | None = None
    office: str | None = None


class Consumer(Strict):
    name: str | None = None
    address: str | None = None
    account_number: str | None = None
    service_connection_number: str | None = None
    gstin: str | None = None
    pan: str | None = None


class Connection(Strict):
    tariff_code: str | None = None
    tariff_category: str | None = None
    supply_kv: Decimal | None = None
    metering_side: str | None = None
    meter_number: str | None = None
    contract_demand_kva: Decimal | None = None
    minimum_billable_kva: Decimal | None = None
    sanctioned_load: Decimal | None = None
    sanctioned_load_unit: str | None = None


class Period(Strict):
    bill_month: str | None = None  # YYYY-MM
    bill_number: str | None = None
    bill_date: str | None = None  # YYYY-MM-DD
    due_date: str | None = None
    disconnection_date: str | None = None
    reading_from: str | None = None
    reading_to: str | None = None
    billing_days: int | None = None
    reading_type: ReadingType | None = None
    bill_kind: BillKind | None = None


class MeterRow(Strict):
    label: str
    quantity: MeterQuantity
    tod_slot: str | None = None
    present: Decimal | None = None
    past: Decimal | None = None
    difference: Decimal | None = None
    multiplying_factor: Decimal | None = None
    multiplying_factor_printed: str | None = None
    gross_units: Decimal | None = None
    open_access_units: Decimal | None = None
    net_units: Decimal | None = None
    page: int | None = None


class Demand(Strict):
    recorded_kva: Decimal | None = None
    billing_kva: Decimal | None = None


class TodSlot(Strict):
    slot: str
    kwh: Decimal | None = None
    kvah: Decimal | None = None


class Energy(Strict):
    billed_units: Decimal | None = None
    billed_unit: Literal["kWh", "kVAh"] | None = None
    gross_kwh: Decimal | None = None
    gross_kvah: Decimal | None = None
    open_access_kwh: Decimal | None = None
    open_access_re_kwh: Decimal | None = None
    open_access_non_re_kwh: Decimal | None = None
    open_access_banked_kwh: Decimal | None = None
    # the unit the open-access figures are printed in (stored as printed, never converted)
    open_access_unit: Literal["kWh", "kVAh"] | None = None
    green_tariff_kwh: Decimal | None = None
    net_metering_import_kwh: Decimal | None = None
    net_metering_export_kwh: Decimal | None = None
    off_peak_kwh: Decimal | None = None
    power_factor: Decimal | None = None
    load_factor: Decimal | None = None
    tod: tuple[TodSlot, ...] = ()


class Gas(Strict):
    customer_id: str | None = None
    volume_scm: Decimal | None = None
    gcv_kcal_per_scm: Decimal | None = None
    energy_mmbtu: Decimal | None = None
    correction_factor: Decimal | None = None
    reading_previous: Decimal | None = None
    reading_current: Decimal | None = None


class LineItem(Strict):
    """Every printed line with an amount, as printed (5.7). `quantity`, `rate` and
    `rate_unit` are filled only when printed on the same line."""

    index: int
    group: str | None = None
    label: str
    kind: LineKind = "item"
    stage: LineStage = "current"
    quantity: Decimal | None = None
    rate: Decimal | None = None
    rate_unit: str | None = None
    unit: str | None = None
    amount: Decimal
    tod_slot: str | None = None
    code: str | None = None
    signed: bool = False
    detail_of: str | None = None  # the label of the printed line this line itemises
    page: int | None = None


class Totals(Strict):
    current_charges: Decimal | None = None
    arrears_total: Decimal | None = None
    adjustments_total: Decimal | None = None
    net_payable: Decimal | None = None
    due_date_rebate: Decimal | None = None
    payable_after_due: Decimal | None = None


class Payments(Strict):
    previous_bill_amount: Decimal | None = None
    last_payment_amount: Decimal | None = None
    last_payment_date: str | None = None


class HistoryRow(Strict):
    month: str
    units: Decimal | None = None
    amount: Decimal | None = None


class Extra(Strict):
    label: str
    value: str


class Bill(Strict):
    schema_version: str = SCHEMA_VERSION
    bill_type: BillType
    discom: Discom = Discom()
    consumer: Consumer = Consumer()
    connection: Connection = Connection()
    period: Period = Period()
    meters: tuple[MeterRow, ...] = ()
    demand: Demand = Demand()
    energy: Energy = Energy()
    gas: Gas = Gas()
    line_items: tuple[LineItem, ...] = ()
    totals: Totals = Totals()
    payments: Payments = Payments()
    history: tuple[HistoryRow, ...] = ()
    extra: tuple[Extra, ...] = ()
    extraction_notes: tuple[str, ...] = ()


# checks, elements, results ---------------------------------------------------------------


class CheckResult(Strict):
    id: str
    description: str
    status: CheckStatus
    expected: str | None = None
    actual: str | None = None
    tolerance: str | None = None
    paths: tuple[str, ...] = ()
    detects: str
    proves: tuple[str, ...] = ()
    equality: bool = False
    unverified_inputs: tuple[str, ...] = ()  # paths whose value was not verified
    note: str | None = None


class FormulaRecheck(Strict):
    status: Literal["match", "differs", "not_computable"]
    computed: str | None = None
    billed: str | None = None
    difference: str | None = None
    reason: str | None = None
    formula: str | None = None


class TariffRecheck(Strict):
    status: Literal["match", "differs", "not_computable"] = "not_computable"
    reason: str | None = "tariff_engine_pending"
    computed: str | None = None
    billed: str | None = None
    difference: str | None = None
    citations: tuple[str, ...] = ()


class Element(Strict):
    """One charge element (5.7): the printed line, its code and amount with proof."""

    index: int
    label: str
    group: str | None = None
    kind: LineKind
    stage: LineStage
    code: str
    quantity: str | None = None
    rate: str | None = None
    unit: str | None = None
    tod_slot: str | None = None
    amount: Value
    formula_recheck: FormulaRecheck
    tariff_recheck: TariffRecheck = TariffRecheck()


class Utility(Strict):
    id: str | None = None
    name_as_printed: str | None = None
    state: str | None = None


class Profile(Strict):
    id: str | None = None
    version: str | None = None
    status: ProfileStatus = "none"


class UsageRecord(Strict):
    provider: str
    model: str
    purpose: str
    input_tokens: int
    output_tokens: int
    cost_usd: Decimal


class ArrayValue(Strict):
    """One item of a guaranteed array (`readings[]`, `energy.tod[]`, `charges.by_code[]`):
    its key and its fields as Values."""

    key: str
    fields: tuple[Value, ...]


class BillResult(Strict):
    index: int
    pages: tuple[int, ...]
    bill_type: BillType | None
    document_type: DocumentType
    utility: Utility = Utility()
    profile: Profile = Profile()
    route: Route
    routes_used: tuple[str, ...] = ()
    fields: tuple[Value, ...] = ()
    arrays: tuple[tuple[str, tuple[ArrayValue, ...]], ...] = ()
    data: Bill | None = None
    checks: tuple[CheckResult, ...] = ()
    elements: tuple[Element, ...] = ()
    passed: bool
    status: Status
    review_reasons: tuple[str, ...] = ()
    flags: tuple[str, ...] = ()
    unread_reason: UnreadReason | None = None
    notes: tuple[str, ...] = ()
    accepted: bool
    accepted_by: Literal["engine", "human"] | None = None
    audit_status: AuditStatus = "not_audited"
    proof_rule_version: str = PROOF_RULE_VERSION

    def field(self, path: str) -> Value | None:
        return next((v for v in self.fields if v.path == path), None)


class FileInfo(Strict):
    sha256: str
    pages: int
    media_type: str


class Envelope(Strict):
    contract_version: str
    engine_version: str = ENGINE_VERSION
    schema_version: str = SCHEMA_VERSION
    file: FileInfo
    bills: tuple[BillResult, ...]
    usage: tuple[UsageRecord, ...] = ()
    seconds: Decimal


class Word(Strict):
    text: str
    region: Region


class PageText(Strict):
    page: int
    text: str
    words: tuple[Word, ...]


class TextEnvelope(Strict):
    """A `kind: "text"` job (contract 5.3): pages, text and words; nothing extracted."""

    contract_version: str
    engine_version: str = ENGINE_VERSION
    schema_version: str = SCHEMA_VERSION
    file: FileInfo
    pages: tuple[PageText, ...]
    usage: tuple[UsageRecord, ...] = ()
    seconds: Decimal


ALL_MODELS: tuple[type[BaseModel], ...] = (
    Region,
    Reading,
    Value,
    Discom,
    Consumer,
    Connection,
    Period,
    MeterRow,
    Demand,
    TodSlot,
    Energy,
    Gas,
    LineItem,
    Totals,
    Payments,
    HistoryRow,
    Extra,
    Bill,
    CheckResult,
    FormulaRecheck,
    TariffRecheck,
    Element,
    Utility,
    Profile,
    UsageRecord,
    ArrayValue,
    BillResult,
    FileInfo,
    Envelope,
    Word,
    PageText,
    TextEnvelope,
)
