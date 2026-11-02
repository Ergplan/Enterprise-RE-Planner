"""Cost estimates before a call and usage records after it (rule 9).

Money is Decimal, written as strings. A usage record carries ids, the model, token counts,
costs and timings; never a bill value.
"""

import json
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from billx.core.settings import load_config

_MILLION = Decimal(1_000_000)


def _price(model_spec: str) -> tuple[Decimal, Decimal]:
    prices = load_config("prices.yaml")
    entry = prices.get("models", {}).get(model_spec)
    if entry is None:
        raise KeyError(f"no price in config/prices.yaml for {model_spec}")
    inp, out = entry["input_per_million_tokens"], entry["output_per_million_tokens"]
    if not isinstance(inp, str) or not isinstance(out, str):
        raise TypeError("prices in config/prices.yaml must be quoted strings")
    return Decimal(inp), Decimal(out)


def prices_are_placeholder() -> bool:
    return bool(load_config("prices.yaml").get("placeholder", True))


def cost(model_spec: str, input_tokens: int, output_tokens: int) -> Decimal:
    inp, out = _price(model_spec)
    return ((inp * input_tokens + out * output_tokens) / _MILLION).quantize(Decimal("0.000001"))


def estimate_tokens(prompt: str, images: int) -> int:
    est = load_config("prices.yaml")["estimate"]
    return len(prompt) // int(est["chars_per_token"]) + images * int(est["tokens_per_image"])


def record_usage(path: Path, entry: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    line = {"at": datetime.now(UTC).isoformat(timespec="seconds"), **entry}
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(line, sort_keys=True) + "\n")
