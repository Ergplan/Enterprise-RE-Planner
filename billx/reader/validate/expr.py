"""Rule expressions (Developer Guide section 6, layer 2): parsed with `ast`, evaluated in
`Decimal`, and allowed to contain ONLY arithmetic operators, numeric constants, parentheses
and calls to the helper names below. Attribute access, subscripts, lambdas, comprehensions,
any other name, a call to anything that is not a helper, `__import__`: refused, with a
clear error, both when a version is checked (`validate_expression`) and when an expression
is evaluated (`evaluate`, which validates again before it touches the tree).

Numeric literals are taken from the source text (`0.5` becomes `Decimal("0.5")`), never
from the float Python parsed. String literals are allowed only as a helper's arguments (a
label regex, a group, a kind, an attribute name).
"""

from __future__ import annotations

import ast
from collections.abc import Callable
from decimal import Decimal
from typing import Any

ALLOWED_HELPERS: frozenset[str] = frozenset(
    {
        "field",
        "param",
        "item",
        "items_sum",
        "subtotal",
        "meter",
        "meters_sum",
        "abs",
        "min",
        "max",
        "round",
    }
)
_BINARY = {ast.Add: "+", ast.Sub: "-", ast.Mult: "*", ast.Div: "/"}
_UNARY = {ast.USub: "-", ast.UAdd: "+"}


class ExpressionError(ValueError):
    """An expression outside the allow-list (the message names the construct, never a value)."""


def parse(text: str) -> ast.Expression:
    if not isinstance(text, str) or not text.strip():
        raise ExpressionError("empty expression")
    try:
        tree = ast.parse(text.strip(), mode="eval")
    except SyntaxError as e:
        raise ExpressionError(f"syntax error at column {e.offset}") from e
    _check(tree.body, text)
    return tree


def validate_expression(text: str) -> None:
    """Raises ExpressionError when `text` uses anything outside the allow-list."""
    parse(text)


def referenced_params(text: str) -> set[str]:
    """The names passed to `param(...)` as a literal first argument."""
    tree = parse(text)
    out: set[str] = set()
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "param"
            and node.args
            and isinstance(node.args[0], ast.Constant)
            and isinstance(node.args[0].value, str)
        ):
            out.add(node.args[0].value)
    return out


def _check(node: ast.AST, src: str, *, as_argument: bool = False) -> None:
    if isinstance(node, ast.Constant):
        if isinstance(node.value, bool):
            raise ExpressionError("boolean constants are not allowed")
        if isinstance(node.value, int | float | Decimal):
            return
        if isinstance(node.value, str) and as_argument:
            return
        kind = type(node.value).__name__
        raise ExpressionError(f"{kind} constant is allowed only as a helper argument")
    if isinstance(node, ast.BinOp):
        if type(node.op) not in _BINARY:
            raise ExpressionError(f"operator {type(node.op).__name__} is not allowed")
        _check(node.left, src)
        _check(node.right, src)
        return
    if isinstance(node, ast.UnaryOp):
        if type(node.op) not in _UNARY:
            raise ExpressionError(f"operator {type(node.op).__name__} is not allowed")
        _check(node.operand, src)
        return
    if isinstance(node, ast.Call):
        if not isinstance(node.func, ast.Name):
            raise ExpressionError("only the helper names may be called")
        if node.func.id not in ALLOWED_HELPERS:
            raise ExpressionError(f"call to {node.func.id!r} is not allowed")
        for arg in node.args:
            _check(arg, src, as_argument=True)
        for kw in node.keywords:
            if kw.arg is None:
                raise ExpressionError("** arguments are not allowed")
            _check(kw.value, src, as_argument=True)
        return
    if isinstance(node, ast.Name):
        if node.id in ALLOWED_HELPERS:
            raise ExpressionError(f"helper {node.id!r} must be called")
        raise ExpressionError(f"name {node.id!r} is not allowed")
    if isinstance(node, ast.Attribute):
        raise ExpressionError("attribute access is not allowed")
    if isinstance(node, ast.Subscript):
        raise ExpressionError("subscripts are not allowed")
    if isinstance(node, ast.Lambda):
        raise ExpressionError("lambdas are not allowed")
    raise ExpressionError(f"{type(node).__name__} is not allowed")


def _literal(node: ast.Constant, src: str) -> Decimal:
    segment = ast.get_source_segment(src, node)
    if segment is None or isinstance(node.value, Decimal):
        return Decimal(str(node.value))
    return Decimal(segment.replace("_", ""))


def evaluate(text: str, helpers: dict[str, Callable[..., Any]]) -> Decimal:
    """Evaluate `text` with the given helper implementations. Every arithmetic result is a
    Decimal; a helper's return value must be a Decimal (an int is widened)."""
    src = text.strip()
    tree = parse(src)
    missing = ALLOWED_HELPERS - set(helpers)
    if missing:
        raise ExpressionError(f"helpers not provided: {sorted(missing)}")
    return _eval(tree.body, src, helpers)


def _eval(node: ast.AST, src: str, helpers: dict[str, Callable[..., Any]]) -> Decimal:
    if isinstance(node, ast.Constant):
        return _literal(node, src)
    if isinstance(node, ast.BinOp):
        left = _eval(node.left, src, helpers)
        right = _eval(node.right, src, helpers)
        op = type(node.op)
        if op is ast.Add:
            return left + right
        if op is ast.Sub:
            return left - right
        if op is ast.Mult:
            return left * right
        if op is ast.Div:
            if right == 0:
                raise ExpressionError("division by zero")
            return left / right
        raise ExpressionError(f"operator {op.__name__} is not allowed")
    if isinstance(node, ast.UnaryOp):
        value = _eval(node.operand, src, helpers)
        return -value if isinstance(node.op, ast.USub) else value
    if isinstance(node, ast.Call):
        assert isinstance(node.func, ast.Name)
        fn = helpers[node.func.id]
        args = [_arg(a, src, helpers) for a in node.args]
        kwargs = {kw.arg: _arg(kw.value, src, helpers) for kw in node.keywords if kw.arg}
        result = fn(*args, **kwargs)
        return _as_decimal(result, node.func.id)
    raise ExpressionError(f"{type(node).__name__} is not allowed")


def _arg(node: ast.AST, src: str, helpers: dict[str, Callable[..., Any]]) -> Any:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return _eval(node, src, helpers)


def _as_decimal(value: Any, name: str) -> Decimal:
    if isinstance(value, Decimal):
        return value
    if isinstance(value, bool) or isinstance(value, float):
        raise ExpressionError(f"helper {name!r} returned a {type(value).__name__}")
    if isinstance(value, int):
        return Decimal(value)
    raise ExpressionError(f"helper {name!r} returned a {type(value).__name__}")


__all__ = [
    "ALLOWED_HELPERS",
    "ExpressionError",
    "evaluate",
    "parse",
    "referenced_params",
    "validate_expression",
]
