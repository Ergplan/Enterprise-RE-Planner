"""One one-token call to a configured model id, so a wrong or retired id is found early.

    python -m billx.reader.providers.ping openai:gpt-6.1-sol

Prints `ok <spec>` or `fail <spec>: <error class>`; never a key, never the reply.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

KEY_ENV = {
    "openai": ("BILLX_OPENAI_API_KEY", "OPENAI_BUILD_REVIEW_KEY"),
    "anthropic": ("BILLX_ANTHROPIC_API_KEY",),
}


ENV_FILE = Path.home() / "billx" / ".env"


def load_env(path: Path = ENV_FILE) -> None:
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        name, sep, value = line.partition("=")
        if sep and not name.strip().startswith("#") and value.strip():
            os.environ.setdefault(name.strip(), value.strip())


def ping(spec: str, key_env: str | None = None, timeout: float = 30.0) -> None:
    provider, _, model = spec.partition(":")
    names = (key_env,) if key_env else KEY_ENV[provider]
    key = next((os.environ[n] for n in names if os.environ.get(n)), None)
    if not key:
        raise RuntimeError(f"no key in {' or '.join(names)}")
    if provider == "openai":
        import openai

        client = openai.OpenAI(api_key=key, timeout=timeout, max_retries=1)
        client.responses.create(model=model, input="1", max_output_tokens=16)
    elif provider == "anthropic":
        import anthropic

        client = anthropic.Anthropic(api_key=key, timeout=timeout, max_retries=1)
        client.messages.create(
            model=model, max_tokens=1, messages=[{"role": "user", "content": "1"}]
        )
    else:
        raise ValueError(f"unknown provider {provider}")


def main(argv: list[str]) -> int:
    load_env()
    spec, key_env = argv[0], (argv[1] if len(argv) > 1 else None)
    try:
        ping(spec, key_env)
    except Exception as exc:  # report the class only: messages can echo request content
        print(f"fail {spec}: {type(exc).__name__}")
        return 1
    print(f"ok {spec}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
