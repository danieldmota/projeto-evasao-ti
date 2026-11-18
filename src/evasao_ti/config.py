"""Configuração centralizada (variáveis de ambiente com prefixo EVASAO_)."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Annotated

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="EVASAO_", env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    data_dir: Path = Path("./data")
    expected_year_start: int = 2009
    expected_year_end: int = 2024

    # Padrão confirmado em
    # https://www.gov.br/inep/pt-br/acesso-a-informacao/dados-abertos/microdados/censo-da-educacao-superior
    inep_url_template: str = (
        "https://download.inep.gov.br/microdados/microdados_censo_da_educacao_superior_{year}.zip"
    )
    inep_listing_url: str = (
        "https://www.gov.br/inep/pt-br/acesso-a-informacao/dados-abertos/microdados/"
        "censo-da-educacao-superior"
    )
    http_timeout: float = 120.0
    # PEM com a cadeia de CA (opcional; ver acquisition/http.py)
    ca_bundle: Path | None = None

    # NoDecode: aceita "a,b,c" na variável de ambiente (em vez de exigir JSON)
    cors_origins: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["http://localhost:5173"]
    )
    api_host: str = "127.0.0.1"
    api_port: int = 8000

    log_level: str = "INFO"
    log_format: str = "json"

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_origins(cls, v: object) -> object:
        if isinstance(v, str):
            return [o.strip() for o in v.split(",") if o.strip()]
        return v

    @property
    def raw_dir(self) -> Path:
        return self.data_dir / "raw"

    @property
    def staging_dir(self) -> Path:
        return self.data_dir / "staging"

    @property
    def warehouse_path(self) -> Path:
        return self.data_dir / "warehouse" / "evasao_ti.duckdb"

    @property
    def reports_dir(self) -> Path:
        return self.data_dir / "reports"

    @property
    def expected_years(self) -> list[int]:
        return list(range(self.expected_year_start, self.expected_year_end + 1))


@lru_cache
def get_settings() -> Settings:
    return Settings()
