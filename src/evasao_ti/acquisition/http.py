"""Cliente HTTP com verificação TLS **sempre ativa**.

Diagnóstico (18/11/2026): ``download.inep.gov.br`` envia apenas o certificado final
(``CN=*.inep.gov.br``), sem o intermediário ``RNP ICPEdu GR46 OV TLS CA 2025``
(``openssl s_client`` → "Verify return code: 21"). O bundle ``certifi`` padrão do Python não
consegue montar a cadeia e falha com CERTIFICATE_VERIFY_FAILED.

Solução, em ordem de preferência:
1. ``EVASAO_CA_BUNDLE`` definido → usa esse arquivo PEM (ex.: servidor Linux com o
   intermediário RNP adicionado ao bundle);
2. ``truststore`` → valida com o repositório de certificados do sistema operacional
   (Windows e macOS completam cadeias incompletas via AIA);
3. padrão do httpx (certifi).

Nunca desativamos a verificação de certificado.
"""

from __future__ import annotations

import ssl

import httpx

from evasao_ti.config import Settings


def ssl_context(settings: Settings) -> ssl.SSLContext | bool:
    if settings.ca_bundle:
        return ssl.create_default_context(cafile=str(settings.ca_bundle))
    try:
        import truststore
    except ImportError:  # pragma: no cover
        return True
    return truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)


def make_client(settings: Settings) -> httpx.Client:
    return httpx.Client(
        timeout=settings.http_timeout,
        follow_redirects=True,
        verify=ssl_context(settings),
        headers={"User-Agent": "evasao-ti-pipeline/0.1 (+dados abertos INEP)"},
    )


def is_certificate_error(exc: BaseException) -> bool:
    return "CERTIFICATE_VERIFY_FAILED" in str(exc)
