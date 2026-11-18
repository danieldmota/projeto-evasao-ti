"""CLI: ``evasao-ti <comando>``. Use ``evasao-ti --help``."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Annotated

import typer

from evasao_ti.config import get_settings
from evasao_ti.logging_setup import configure_logging, get_logger

app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    help="Pipeline dos microdados do Censo da Educação Superior (INEP) e API.",
)
log = get_logger("cli")

YearsOpt = Annotated[
    str | None,
    typer.Option(
        "--years", "-y", help="Ex.: 2023 | 2009-2024 | 2019,2021-2023. Padrão: série esperada"
    ),
]


def parse_years(spec: str | None, default: list[int]) -> list[int]:
    if not spec:
        return default
    years: set[int] = set()
    for part in spec.split(","):
        part = part.strip()
        if "-" in part:
            a, b = (int(x) for x in part.split("-", 1))
            if a > b:
                raise typer.BadParameter(f"Intervalo inválido: {part}")
            years.update(range(a, b + 1))
        elif part:
            years.add(int(part))
    return sorted(years)


@app.callback()
def _main() -> None:
    s = get_settings()
    configure_logging(s.log_level, s.log_format)


@app.command()
def discover() -> None:
    """Lê a página oficial do INEP e compara os ZIPs publicados com o padrão configurado."""
    from evasao_ti.acquisition.http import make_client
    from evasao_ti.acquisition.sources import discover_urls, url_for_year

    s = get_settings()
    with make_client(s) as client:
        found = discover_urls(s.inep_listing_url, client=client)
    for year in s.expected_years:
        expected = url_for_year(year, s.inep_url_template)
        actual = found.get(year)
        flag = "OK" if actual == expected else ("AUSENTE NA PÁGINA" if not actual else "DIFERENTE")
        typer.echo(f"{year}  {flag:<18} {actual or expected}")


@app.command()
def download(years: YearsOpt = None, force: bool = typer.Option(False, help="Rebaixar")) -> None:
    """Baixa e valida os ZIPs oficiais (ignora arquivos já atualizados)."""
    from evasao_ti.acquisition.download import DownloadError, download_year

    s = get_settings()
    failures = 0
    for y in parse_years(years, s.expected_years):
        try:
            rec = download_year(y, s, force=force)
            typer.echo(
                f"{y}: {rec.status} ({rec.size / 1e6:.1f} MB, md5 CSV ok={rec.csv_md5_verified})"
            )
        except DownloadError as exc:
            failures += 1
            typer.echo(f"{y}: ERRO {exc}", err=True)
    if failures:
        raise typer.Exit(1)


@app.command()
def ingest(years: YearsOpt = None, force: bool = typer.Option(False, help="Reprocessar")) -> None:
    """Processa os ZIPs de data/raw para Parquet (um arquivo por ano)."""
    from evasao_ti.storage.staging import ingest_year

    s = get_settings()
    failures = 0
    for y in parse_years(years, s.expected_years):
        try:
            meta = ingest_year(y, s, force=force)
            warns = meta.get("quality", {}).get("warnings", [])
            typer.echo(f"{y}: {meta['status']} ({meta['rows_out']} cursos, {len(warns)} avisos)")
        except FileNotFoundError as exc:
            failures += 1
            typer.echo(f"{y}: AUSENTE {exc}", err=True)
        except Exception as exc:  # erro explícito por ano, sem interromper os demais
            failures += 1
            log.exception("falha na ingestão", extra={"ctx": {"ano": y}})
            typer.echo(f"{y}: ERRO {type(exc).__name__}: {exc}", err=True)
    if failures:
        raise typer.Exit(1)


@app.command("ingest-csv")
def ingest_csv(
    path: Annotated[Path, typer.Argument(exists=True, dir_okay=False, help="CSV ou ZIP avulso")],
    year: Annotated[int | None, typer.Option(help="Ano (padrão: inferido do nome)")] = None,
    force: bool = False,
) -> None:
    """Processa um MICRODADOS_CADASTRO_CURSOS_AAAA.CSV (ou ZIP) local, sem download."""
    from evasao_ti.storage.staging import ingest_file

    meta = ingest_file(path, get_settings(), year=year, force=force)
    typer.echo(json.dumps({k: meta[k] for k in ("year", "status", "rows_out")}, ensure_ascii=False))


@app.command()
def build() -> None:
    """Consolida o staging no warehouse DuckDB (aplica a classificação vigente)."""
    from evasao_ti.storage.warehouse import build_warehouse

    info = build_warehouse(get_settings())
    typer.echo(json.dumps(info, ensure_ascii=False, indent=2))


@app.command()
def update(years: YearsOpt = None, force: bool = False) -> None:
    """download + ingest + build para os anos informados."""
    from evasao_ti.acquisition.download import download_year
    from evasao_ti.storage.staging import ingest_year
    from evasao_ti.storage.warehouse import build_warehouse

    s = get_settings()
    errors: list[str] = []
    for y in parse_years(years, s.expected_years):
        try:
            download_year(y, s, force=force)
            ingest_year(y, s, force=force)
            typer.echo(f"{y}: ok")
        except Exception as exc:
            errors.append(f"{y}: {exc}")
            log.exception("falha na atualização", extra={"ctx": {"ano": y}})
    build_warehouse(s)
    if errors:
        typer.echo("Anos com erro:\n" + "\n".join(errors), err=True)
        raise typer.Exit(1)


@app.command()
def audit(years: YearsOpt = None) -> None:
    """Gera relatórios comparando a classificação CINE com a lógica do notebook."""
    from evasao_ti.classification.audit import write_audit
    from evasao_ti.storage.staging import list_staged_years, read_staged

    s = get_settings()
    staged = list_staged_years(s.staging_dir)
    sel = [y for y in parse_years(years, staged) if y in staged]
    if not sel:
        typer.echo("Nenhum ano no staging.", err=True)
        raise typer.Exit(1)
    paths = write_audit(read_staged(s.staging_dir, sel), s.reports_dir)
    for k, p in paths.items():
        typer.echo(f"{k}: {p}")


@app.command()
def report(
    group_by: Annotated[
        str, typer.Option(help="area | segmento | cine_geral | total")
    ] = "segmento",
) -> None:
    """Imprime a série anual (taxa de trancamento) a partir do warehouse."""
    import pandas as pd

    from evasao_ti.analytics.queries import Filters, GroupBy, annual, summary
    from evasao_ti.storage.repository import Repository

    snap = Repository(get_settings().warehouse_path).snapshot()
    gb = GroupBy(group_by)
    df = annual(snap.fact, Filters(), gb)
    piv = df.pivot_table(index="ano", columns="grupo_codigo", values="taxa_trancamento")
    with pd.option_context("display.width", 200, "display.max_columns", 20):
        typer.echo("Taxa de trancamento = trancadas / (matriculas + trancadas), graduação\n")
        typer.echo((piv * 100).round(2).to_string())
        tot, yrs = summary(snap.fact, Filters(), gb)
        typer.echo(f"\nConsolidado {yrs[0]}–{yrs[-1]} (vínculos-ano, razão de somas):")
        typer.echo(
            tot[["grupo_codigo", "matriculas", "trancadas", "taxa_trancamento"]]
            .assign(taxa_trancamento=lambda d: (d.taxa_trancamento * 100).round(2))
            .to_string(index=False)
        )


@app.command()
def serve(host: str | None = None, port: int | None = None, reload: bool = False) -> None:
    """Sobe a API (uvicorn)."""
    import uvicorn

    s = get_settings()
    uvicorn.run(
        "evasao_ti.api.app:create_app",
        factory=True,
        host=host or s.api_host,
        port=port or s.api_port,
        reload=reload,
    )


if __name__ == "__main__":  # pragma: no cover
    sys.exit(app())
