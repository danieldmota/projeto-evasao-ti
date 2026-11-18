"""Download idempotente e validado (HTTP simulado com httpx.MockTransport)."""

from __future__ import annotations

import httpx
import pytest

from evasao_ti.acquisition.download import DownloadError, download_year, load_manifest
from evasao_ti.acquisition.sources import parse_listing, url_for_year
from synthetic import default_rows, to_csv_bytes, write_zip


@pytest.fixture
def zip_bytes(tmp_path):
    return write_zip(tmp_path / "src.zip", 2023, to_csv_bytes(default_rows(2023))).read_bytes()


def make_client(
    payload: bytes,
    *,
    etag: str = '"v1"',
    truncate: bool = False,
    status: int = 200,
    counter: dict | None = None,
) -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        if counter is not None:
            counter[request.method] = counter.get(request.method, 0) + 1
        headers = {
            "etag": etag,
            "last-modified": "Tue, 30 Dec 2025 20:15:19 GMT",
            "content-length": str(len(payload)),
        }
        if status != 200:
            return httpx.Response(status)
        if request.method == "HEAD":
            return httpx.Response(200, headers=headers)
        body = payload[: len(payload) // 2] if truncate else payload
        return httpx.Response(
            200, headers={**headers, "content-length": str(len(body))}, content=body
        )

    return httpx.Client(transport=httpx.MockTransport(handler))


def test_download_validates_and_registers(settings, zip_bytes) -> None:
    rec = download_year(2023, settings, client=make_client(zip_bytes), backoff=0)
    assert rec.status == "downloaded"
    assert rec.csv_md5_verified
    assert load_manifest(settings.raw_dir)["2023"]["etag"] == '"v1"'


def test_second_download_is_skipped(settings, zip_bytes) -> None:
    download_year(2023, settings, client=make_client(zip_bytes), backoff=0)
    calls: dict = {}
    rec = download_year(2023, settings, client=make_client(zip_bytes, counter=calls), backoff=0)
    assert rec.status == "up_to_date"
    assert calls.get("GET", 0) == 0


def test_new_remote_version_triggers_update(settings, zip_bytes) -> None:
    download_year(2023, settings, client=make_client(zip_bytes), backoff=0)
    rec = download_year(2023, settings, client=make_client(zip_bytes, etag='"v2"'), backoff=0)
    assert rec.status == "updated"


def test_incomplete_download_is_discarded(settings, zip_bytes) -> None:
    with pytest.raises(DownloadError):
        download_year(
            2023, settings, client=make_client(zip_bytes, truncate=True), retries=2, backoff=0
        )
    assert not list(settings.raw_dir.glob("*.zip"))
    assert not list(settings.raw_dir.glob("*.part"))


def test_404_is_not_retried(settings) -> None:
    calls: dict = {}
    with pytest.raises(DownloadError, match="404"):
        download_year(2030, settings, client=make_client(b"", status=404, counter=calls), backoff=0)
    assert calls["HEAD"] == 1


def test_only_official_domain_is_accepted() -> None:
    with pytest.raises(ValueError):
        url_for_year(2023, "https://example.com/{year}.zip")


def test_parse_listing_extracts_only_official_links() -> None:
    html = """
    <a href="https://download.inep.gov.br/microdados/microdados_censo_da_educacao_superior_2024.zip">2024</a>
    <a href="https://download.inep.gov.br/microdados/microdados_censo_da_educacao_superior_2009.zip">2009</a>
    <a href="https://mirror.example.com/microdados_censo_da_educacao_superior_2010.zip">x</a>
    """
    assert sorted(parse_listing(html)) == [2009, 2024]
