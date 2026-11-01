"""Where configuration comes from: the environment first, then the repository's git-ignored `.env`.

Rule 11: secrets only by environment variable, read here and nowhere else.
"""

from __future__ import annotations

from decimal import Decimal
from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[4]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(REPO_ROOT / ".env"), env_file_encoding="utf-8", extra="ignore"
    )

    ergplan_env: str = "dev"
    database_url: str = "postgresql+psycopg://ergplan:ergplan@localhost:5432/ergplan"
    ergplan_data_dir: Path = Field(default=REPO_ROOT / "data")
    ergplan_public_url: str = "http://localhost:3000"
    ergplan_web_internal_url: str = "http://localhost:3000"  # where the API reaches the web app (PDF)
    ergplan_analyst_domain: str = "joulewise.in"  # emails here sign in as analysts
    ergplan_analyst_emails: str = ""  # comma-separated, also analysts
    ergplan_smtp_url: str = ""  # smtp[s]://user:password@host:port; empty: links go to the log
    ergplan_mail_from: str = "ergPLAN <no-reply@joulewise.in>"
    ergplan_resettle_tolerance_kwh: Decimal = Decimal("1")
    ergplan_optimizer_time_limit_s: float = 110.0
    ergplan_optimizer_mip_gap: float = 0.001
    ergplan_worker_concurrency: int = 1  # runs solved at once by `python -m ergplan.platform.worker`

    billx_url: str = "http://localhost:8080"
    billx_token: str = ""
    # what one file's reading may spend on model readers (Model A, LlamaParse), in US dollars,
    # and how long ergPLAN waits for billx (Docling and two model readers take minutes)
    billx_max_cost_usd: str = "2.00"
    billx_timeout_s: int = 1500

    # Models: OpenAI only (decision 31 Oct 2026). Read by ergplan.providers and nothing else.
    openai_api_key: str = ""
    openai_model_regreader: str = "gpt-5.1"
    openai_model_explain: str = "gpt-5-mini"
    openai_realtime_model: str = "gpt-realtime"

    tariff_oder_url: str = ""
    tariff_oder_token: str = ""

    @property
    def documents_dir(self) -> Path:
        return self.ergplan_data_dir / "documents"

    @property
    def bill_files_dir(self) -> Path:
        """The client's bill PDFs as uploaded (gitignored), so a bill value links to its page."""
        return self.ergplan_data_dir / "bill_files"

    @property
    def schemas_dir(self) -> Path:
        return REPO_ROOT / "packages" / "rulebooks" / "schemas"

    @property
    def corpus_index(self) -> Path:
        return REPO_ROOT / "packages" / "rulebooks" / "corpus" / "tariff-library.json"

    @property
    def rulebooks_dir(self) -> Path:
        return REPO_ROOT / "packages" / "rulebooks"


@lru_cache
def get_settings() -> Settings:
    return Settings()
