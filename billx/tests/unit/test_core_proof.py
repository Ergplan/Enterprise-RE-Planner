"""The verification rule (5.2) in billx/core/proof.py: the only place a verdict is made."""

import ast
from pathlib import Path

from billx.core.proof import ReadingView, decide, independent

ROOT = Path(__file__).resolve().parents[2]


def rv(reader, value, method=None, family=None, **kw):
    methods = {
        "text_layer": "text_layer",
        "local_ocr": "ocr",
        "model_a": "vision",
        "model_b": "vision",
        "human": "human",
    }
    fam = family or {"model_a": "openai", "model_b": "anthropic"}.get(reader)
    return ReadingView(reader, method or methods[reader], fam, value, **kw)


def test_one_reading_is_unverified():
    d = decide((rv("text_layer", "100"),))
    assert d.verification == "unverified" and d.value == "100" and d.proof == ("single",)


def test_no_reading_is_unverified_with_no_value():
    d = decide(())
    assert d.verification == "unverified" and d.value is None and d.proof == ()


def test_text_layer_and_ocr_agreeing_is_not_consensus():
    """Both find the field by the same label rule, so they can share a wrong pick (proof
    rule 2): their agreement leaves the field unverified."""
    d = decide((rv("text_layer", "100"), rv("local_ocr", "100")))
    assert d.verification == "unverified" and d.value == "100"


def test_a_local_reader_and_a_model_agreeing_is_consensus():
    d = decide((rv("text_layer", "100"), rv("local_ocr", "100"), rv("model_a", "100")))
    assert d.verification == "verified" and d.proof == ("consensus",)
    assert d.readers == ("text_layer", "local_ocr", "model_a") and d.source == "ocr"


def test_two_model_families_agreeing_is_consensus():
    d = decide((rv("model_a", "5"), rv("model_b", "5")))
    assert d.verification == "verified" and d.source == "model"


def test_same_family_twice_is_not_independent():
    assert not independent(rv("model_a", "5"), rv("model_b", "5", family="openai"))
    d = decide((rv("model_a", "5"), rv("model_b", "5", family="openai")))
    assert d.verification == "unverified"


def test_a_reader_never_agrees_with_itself():
    d = decide((rv("local_ocr", "7"), rv("local_ocr", "7")))
    assert d.verification == "unverified"


def test_disagreement_is_disputed_and_keeps_the_first_value():
    d = decide((rv("text_layer", "100"), rv("local_ocr", "190")))
    assert d.verification == "disputed" and d.value == "100" and d.readers == ("text_layer",)


def test_outvoted_third_reading_is_kept_in_readers_not_a_failure():
    d = decide((rv("text_layer", "100"), rv("model_a", "190"), rv("model_b", "100")))
    assert d.verification == "verified" and d.readers == ("text_layer", "model_b")


def test_arithmetic_is_extra_assurance_never_proof_alone():
    d = decide((rv("local_ocr", "100"),), ("G09",))
    assert d.verification == "unverified"
    d = decide((rv("text_layer", "100"), rv("model_a", "100")), ("G09",))
    assert d.proof == ("consensus", "arithmetic")


def test_exact_needs_arithmetic_for_a_number():
    d = decide((rv("text_layer", "100", exact=True),))
    assert d.verification == "unverified"
    d = decide((rv("text_layer", "100", exact=True),), ("G09",))
    assert d.verification == "verified" and d.proof == ("exact", "arithmetic")


def test_a_person_confirms():
    d = decide((rv("local_ocr", "190"), rv("human", "100", confirmed_by="A Person")))
    assert d.verification == "confirmed" and d.value == "100" and d.readers == ("human",)


def test_unreadable_reading_never_matches():
    d = decide((rv("text_layer", None), rv("local_ocr", None)))
    assert d.verification == "unverified" and d.value is None


def _assigns_verification(path: Path) -> bool:
    tree = ast.parse(path.read_text(), filename=str(path))
    for node in ast.walk(tree):
        if isinstance(node, ast.keyword) and node.arg == "verification":
            return True
        if isinstance(node, ast.Attribute) and node.attr == "verification":
            if isinstance(getattr(node, "ctx", None), ast.Store):
                return True
    return False


def test_no_module_other_than_proof_assigns_a_verification():
    """Invariant 1: decide() in core/proof.py decides; schema.make_value only copies its
    decision into a Value. Every other module may read a verification, never set one."""
    allowed = {"billx/core/proof.py", "billx/core/schema.py"}
    offenders = [
        str(p.relative_to(ROOT))
        for p in (ROOT / "billx").rglob("*.py")
        if str(p.relative_to(ROOT)) not in allowed and _assigns_verification(p)
    ]
    assert offenders == []
