"""Where configuration comes from (rule 12): the config folder, the data folder, and
settings from the environment or the git-ignored env file (~/billx/.env by default).

Values read here are never logged; a key is only ever handed to the provider that uses it.
"""

import os
from pathlib import Path

import yaml

_REPO_CONFIG = Path(__file__).resolve().parents[2] / "config"


def config_dir() -> Path:
    return Path(os.environ.get("BILLX_CONFIG_DIR", _REPO_CONFIG))


def load_config(name: str) -> dict:
    with open(config_dir() / name, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def data_dir() -> Path:
    return Path(os.environ.get("BILLX_DATA_DIR", "~/billx-data")).expanduser()


def _env_file() -> dict[str, str]:
    path = Path(os.environ.get("BILLX_ENV_FILE", "~/billx/.env")).expanduser()
    if not path.is_file():
        return {}
    out = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        out[key.strip()] = value.strip().strip("'\"")
    return out


def setting(name: str, default: str | None = None) -> str | None:
    """The environment first, then the env file; an empty value counts as unset."""
    value = os.environ.get(name) or _env_file().get(name)
    return value or default
