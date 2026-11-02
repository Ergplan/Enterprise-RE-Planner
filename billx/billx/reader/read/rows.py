"""Table rows from words (build prompt 5.1): printed charge lines for the element capture
(5.7) and meter-reading rows. Every value is the printed string; nothing is computed.

Charge lines (`extract_lines`): a line qualifies when its last token is money-like (digit
grouping, or a decimal point with two places) and it is not a key-value line (no ":", number
or date among the words before the trailing numbers) nor a meter row. The trailing run of
number-like tokens holds the numbers: one is the amount; two are quantity and amount; three
or more end in quantity, rate, amount. The words before the numbers are the label, less a
unit token at its end (kVAh, kVA, kWh, SCM, MMBtu, month...) and a serial number at its
start. `kind` is "subtotal" when the label is a
current-charges, arrears, net-payable or total label, "info" when the whole label names a
demand or energy fact (recorded MD, billing demand, total units) and "item" otherwise.

Meter rows (`extract_meters`): a line whose trailing numbers are exactly five (present, past,
difference, multiplying factor, consumption) with text before them. The register (kWh, kVAh)
is the first word of the row when it is one, else the register of the nearest heading or row
above; the remaining text is the TOD slot, "Total" for the register total.
"""

from __future__ import annotations

import re

from billx.core.normalize import normalise_date, normalise_number
from billx.core.schema import Region
from billx.reader.read.words import WordBox, group_lines, region_of

_MONEY = re.compile(r"^[+-]?(\d{1,3}(,\d{2,3})+(\.\d+)?|\d+\.\d{2})$")
_UNIT = re.compile(r"^(kvah|kva|kwh|kw|kvarh|scm|mmbtu|months?|nos|kl|days?|%)$", re.I)
_SERIAL = re.compile(r"^\d{1,3}\.?$")
_REGISTER = {"kwh": "kWh", "kvah": "kVAh", "kva": "kVA", "kw": "kW", "kvarh": "kVArh"}
_SUBTOTAL = re.compile(
    r"current (charges?|dues|bill amount|month charges)|arrears?|previous dues|outstanding"
    r"|net payable|net amount|amount payable|total payable|grand total|\btotal\b",
    re.I,
)
_INFO = re.compile(
    r"^((recorded|billing|billable|contract(ed)?|maximum|max) (md|demand)|\bmd\b"
    r"|(average |avg )?(power factor|pf)|total units|units consumed|load factor)"
    r"( \([^()]*\))?$",
    re.I,
)
_TOTAL = re.compile(r"^total$", re.I)


def number_like(text: str) -> bool:
    return normalise_number(text) is not None


def money_like(text: str) -> bool:
    return bool(_MONEY.match(text.replace("−", "-")))


def _trailing_numbers(line: list[WordBox]) -> tuple[list[WordBox], list[WordBox]]:
    """(words before the numbers, the trailing run of number-like words)."""
    n = len(line)
    while n > 0 and number_like(line[n - 1].text):
        n -= 1
    return line[:n], line[n:]


def _meter_row(head: list[WordBox], numbers: list[WordBox], register: str | None):
    """The meter row of a line, or None: five trailing numbers, text before them, a register
    in the row or inherited from above."""
    if len(numbers) != 5 or not head:
        return None
    own = _REGISTER.get(head[0].text.lower())
    slot_words = head[1:] if own else head
    register = own or register
    if register is None or any(w.text == ":" for w in head):
        return None
    slot = " ".join(w.text for w in slot_words) or None
    if slot and _TOTAL.match(slot):
        slot = "Total"
    present, past, difference, mf, consumption = (w.text for w in numbers)
    return {
        "register": register,
        "tod_slot": slot,
        "present": present,
        "past": past,
        "difference": difference,
        "multiplying_factor": mf,
        "consumption": consumption,
        "page": head[0].page,
        "region": region_of(head + numbers),
    }


def extract_meters(words: list[WordBox]) -> list[dict[str, str | int | Region | None]]:
    """Meter-reading rows: register, tod_slot and the five printed numbers, with page and
    region, in reading order."""
    rows = []
    register: str | None = None
    for line in group_lines(words):
        head, numbers = _trailing_numbers(line)
        if head and head[0].text.lower() in _REGISTER:
            register = _REGISTER[head[0].text.lower()]
        row = _meter_row(head, numbers, register)
        if row:
            rows.append(row)
    return rows


def is_meter_row(line: list[WordBox]) -> bool:
    """Five trailing numbers behind a register or slot name (the register may be inherited,
    so any text before five numbers counts here)."""
    head, numbers = _trailing_numbers(line)
    return _meter_row(head, numbers, "any") is not None


def _kind(label: str) -> str:
    if _SUBTOTAL.search(label):
        return "subtotal"
    if _INFO.match(label):
        return "info"
    return "item"


def _key_value(head: list[WordBox]) -> bool:
    """A ":" or a number or date among the words before the trailing numbers: a labelled
    field line, not a charge line."""
    return any(
        w.text == ":" or number_like(w.text) or normalise_date(w.text) is not None for w in head
    )


def extract_lines(words: list[WordBox]) -> list[dict[str, str | int | Region | None]]:
    """Printed lines with an amount: label, quantity, rate, amount, unit, kind, page and
    region, in reading order."""
    rows = []
    register: str | None = None
    for line in group_lines(words):
        head, numbers = _trailing_numbers(line)
        if head and head[0].text.lower() in _REGISTER:
            register = _REGISTER[head[0].text.lower()]
        if not numbers or not head or not money_like(numbers[-1].text):
            continue
        if _meter_row(head, numbers, register):
            continue
        if len(head) > 1 and _SERIAL.match(head[0].text):
            head = head[1:]
        if _key_value(head):
            continue
        unit = None
        if _UNIT.match(head[-1].text) and len(head) > 1:
            unit, head = head[-1].text, head[:-1]
        label = " ".join(w.text for w in head)
        quantity = rate = None
        if len(numbers) == 2:
            quantity = numbers[0].text
        elif len(numbers) >= 3:
            quantity, rate = numbers[-3].text, numbers[-2].text
        rows.append(
            {
                "label": label,
                "quantity": quantity,
                "rate": rate,
                "amount": numbers[-1].text,
                "unit": unit,
                "kind": _kind(label),
                "page": line[0].page,
                "region": region_of(line),
            }
        )
    return rows
