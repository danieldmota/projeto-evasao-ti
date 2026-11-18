"""Fontes oficiais dos microdados do Censo da Educação Superior.

O padrão de URL abaixo foi confirmado na página oficial de dados abertos do INEP
(https://www.gov.br/inep/pt-br/acesso-a-informacao/dados-abertos/microdados/censo-da-educacao-superior),
que lista um ZIP por ano em ``download.inep.gov.br/microdados/``. A função
:func:`discover_urls` relê essa página para detectar mudanças, aceitando apenas
links do domínio oficial.
"""

from __future__ import annotations

import re

import httpx

OFFICIAL_DOWNLOAD_HOST = "download.inep.gov.br"

_LINK_RE = re.compile(
    r"https://download\.inep\.gov\.br/microdados/"
    r"microdados_censo_da_educacao_superior_(\d{4})\.zip",
    re.IGNORECASE,
)


def url_for_year(year: int, template: str) -> str:
    url = template.format(year=year)
    if httpx.URL(url).host != OFFICIAL_DOWNLOAD_HOST:
        raise ValueError(f"URL fora do domínio oficial do INEP: {url}")
    return url


def parse_listing(html: str) -> dict[int, str]:
    """Extrai {ano: url} de um HTML da página oficial (somente domínio oficial)."""
    found: dict[int, str] = {}
    for match in _LINK_RE.finditer(html):
        found[int(match.group(1))] = match.group(0)
    return dict(sorted(found.items()))


def discover_urls(
    listing_url: str, client: httpx.Client | None = None, timeout: float = 60.0
) -> dict[int, str]:
    own = client is None
    client = client or httpx.Client(timeout=timeout, follow_redirects=True)
    try:
        resp = client.get(listing_url)
        resp.raise_for_status()
        return parse_listing(resp.text)
    finally:
        if own:
            client.close()
