"""Download idempotente e validado dos ZIPs oficiais.

- Evita downloads repetidos comparando tamanho/ETag/Last-Modified do servidor com o
  manifesto local (``raw/downloads.json``).
- Grava em ``.part`` e só promove o arquivo após conferir o tamanho (Content-Length)
  e a integridade do ZIP (MD5 oficial do CSV). Downloads incompletos são descartados.
"""

from __future__ import annotations

import json
import os
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

import httpx

from evasao_ti.acquisition.archive import ArchiveError, inspect_archive, sha256_of_file
from evasao_ti.acquisition.http import is_certificate_error, make_client
from evasao_ti.acquisition.sources import url_for_year
from evasao_ti.config import Settings
from evasao_ti.logging_setup import get_logger

log = get_logger("download")

MANIFEST_NAME = "downloads.json"


class DownloadError(Exception):
    pass


@dataclass
class DownloadRecord:
    year: int
    url: str
    path: str
    size: int
    sha256: str
    etag: str | None
    last_modified: str | None
    downloaded_at: str
    csv_member: str
    csv_md5_verified: bool
    status: str = "downloaded"  # downloaded | up_to_date | updated


def zip_path_for_year(raw_dir: Path, year: int) -> Path:
    return raw_dir / f"microdados_censo_da_educacao_superior_{year}.zip"


def load_manifest(raw_dir: Path) -> dict[str, dict]:
    p = raw_dir / MANIFEST_NAME
    if not p.exists():
        return {}
    return json.loads(p.read_text(encoding="utf-8"))


def save_manifest(raw_dir: Path, manifest: dict[str, dict]) -> None:
    p = raw_dir / MANIFEST_NAME
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, p)


def _retry[T](fn: Callable[[], T], what: str, retries: int, backoff: float) -> T:
    """Executa ``fn`` com retentativas para falhas de rede/HTTP 5xx (o servidor do INEP
    eventualmente reseta conexões). Erros definitivos (404, validação) não são repetidos."""
    last: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            return fn()
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code < 500:
                raise DownloadError(f"{what}: HTTP {exc.response.status_code}") from exc
            last = exc
        except (httpx.TransportError, DownloadError, ArchiveError) as exc:
            if is_certificate_error(exc):
                raise DownloadError(
                    f"{what}: falha na verificação do certificado TLS ({exc}). O servidor do "
                    "INEP envia cadeia incompleta; instale 'truststore' ou defina "
                    "EVASAO_CA_BUNDLE (ver README). A verificação não é desativada."
                ) from exc
            last = exc
        log.warning(
            "falha de rede; nova tentativa",
            extra={"ctx": {"operacao": what, "tentativa": attempt, "erro": str(last)}},
        )
        if attempt < retries:
            time.sleep(min(backoff * 2 ** (attempt - 1), 30))
    raise DownloadError(f"{what}: falhou após {retries} tentativas ({last})")


def _remote_info(client: httpx.Client, url: str) -> dict[str, str | int | None]:
    resp = client.head(url)
    resp.raise_for_status()  # 404 (ano não publicado) vira DownloadError sem retentativa
    length = resp.headers.get("content-length")
    return {
        "size": int(length) if length else None,
        "etag": resp.headers.get("etag"),
        "last_modified": resp.headers.get("last-modified"),
    }


def _stream_to(client: httpx.Client, url: str, dest: Path, expected_size: int | None) -> int:
    written = 0
    with client.stream("GET", url) as resp:
        resp.raise_for_status()
        with dest.open("wb") as f:
            for chunk in resp.iter_bytes(1 << 20):
                f.write(chunk)
                written += len(chunk)
    if expected_size is not None and written != expected_size:
        raise DownloadError(f"Download incompleto de {url}: {written} de {expected_size} bytes")
    return written


def download_year(
    year: int,
    settings: Settings,
    *,
    force: bool = False,
    client: httpx.Client | None = None,
    retries: int = 4,
    backoff: float = 2.0,
) -> DownloadRecord:
    raw_dir = settings.raw_dir
    raw_dir.mkdir(parents=True, exist_ok=True)
    url = url_for_year(year, settings.inep_url_template)
    target = zip_path_for_year(raw_dir, year)
    manifest = load_manifest(raw_dir)
    previous = manifest.get(str(year))

    own = client is None
    client = client or make_client(settings)
    try:
        remote = _retry(lambda: _remote_info(client, url), f"HEAD {year}", retries, backoff)
        if target.exists() and not force:
            same_size = remote["size"] is None or target.stat().st_size == remote["size"]
            same_version = previous is None or (
                previous.get("etag") == remote["etag"]
                and previous.get("last_modified") == remote["last_modified"]
            )
            if same_size and same_version:
                if previous is None:  # arquivo trazido manualmente: valida e registra
                    previous = asdict(_register(year, url, target, remote, status="up_to_date"))
                    manifest[str(year)] = previous
                    save_manifest(raw_dir, manifest)
                log.info(
                    "download ignorado: arquivo local atualizado", extra={"ctx": {"ano": year}}
                )
                rec = DownloadRecord(**{**previous, "status": "up_to_date"})
                return rec

        status = "updated" if target.exists() else "downloaded"
        part = target.with_suffix(".zip.part")

        def attempt() -> None:
            try:
                log.info("baixando microdados", extra={"ctx": {"ano": year, "url": url}})
                _stream_to(client, url, part, remote["size"])  # type: ignore[arg-type]
                inspect_archive(part, expected_year=year, verify_md5=True)
            except BaseException:
                part.unlink(missing_ok=True)  # nunca deixa arquivo incompleto para trás
                raise

        _retry(attempt, f"GET {year}", retries, backoff)
        os.replace(part, target)
        rec = _register(year, url, target, remote, status=status)
        manifest[str(year)] = asdict(rec)
        save_manifest(raw_dir, manifest)
        return rec
    finally:
        if own:
            client.close()


def _register(year: int, url: str, target: Path, remote: dict, status: str) -> DownloadRecord:
    info = inspect_archive(target, expected_year=year, verify_md5=True)
    return DownloadRecord(
        year=year,
        url=url,
        path=str(target),
        size=target.stat().st_size,
        sha256=sha256_of_file(target),
        etag=remote.get("etag"),
        last_modified=remote.get("last_modified"),
        downloaded_at=datetime.now(UTC).isoformat(),
        csv_member=info.member,
        csv_md5_verified=info.md5_verified,
        status=status,
    )
