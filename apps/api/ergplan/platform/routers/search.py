"""Bill search and analytics (after Stage 8): keyword search over the bills a person may see,
and each account's months with the figures planning uses, each with its bill source_ref."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query

from ...db.base import session_scope
from ...search import bills as bill_search
from ..auth import ANONYMOUS, Caller, caller

router = APIRouter(tags=["bills"])


def _staff(who: Caller) -> bool:
    return who.role == "analyst" and who.actor != ANONYMOUS


@router.get("/bill-search", response_model=bill_search.SearchOut)
def search_bills(
    who: Annotated[Caller, Depends(caller)],
    q: Annotated[str, Query(min_length=1, max_length=200)],
    top_k: Annotated[int, Query(ge=1, le=50)] = 10,
) -> bill_search.SearchOut:
    """The bills that match the words asked (DISCOM, consumer, month, a field, a slot, a charge,
    a failing check), best first, each with the lines that matched."""
    with session_scope() as s:
        bills = bill_search.visible_bills(s, who.actor if who.signed_in else None, _staff(who))
        return bill_search.search(bills, q, top_k)


@router.get("/bill-analytics", response_model=bill_search.AnalyticsOut)
def bill_analytics(who: Annotated[Caller, Depends(caller)]) -> bill_search.AnalyticsOut:
    """Each account's months: consumption by slot, open access set off and its share, billed
    units, demand, power factor and charges, every figure linked to its bill page."""
    with session_scope() as s:
        bills = bill_search.visible_bills(s, who.actor if who.signed_in else None, _staff(who))
        return bill_search.analytics(s, bills)
