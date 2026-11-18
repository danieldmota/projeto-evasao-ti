"""Validação estrutural do conteúdo editorial das seções 7 e 8 (web/conteudo/trilha-ti.json)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

CONTENT = Path(__file__).resolve().parents[1] / "web" / "conteudo" / "trilha-ti.json"


@pytest.fixture(scope="module")
def conteudo() -> dict:
    return json.loads(CONTENT.read_text(encoding="utf-8"))


def test_metadata(conteudo: dict) -> None:
    for key in ("versao", "revisado_em", "aviso"):
        assert conteudo[key]


def test_exactly_five_competencias(conteudo: dict) -> None:
    itens = conteudo["competencias"]["itens"]
    assert len(itens) == 5
    assert len({i["id"] for i in itens}) == 5
    for it in itens:
        for key in ("titulo", "resumo", "por_que_importa"):
            assert it[key].strip()
        assert len(it["como_desenvolver"]) >= 2
        assert it["recursos"]


def test_every_referenced_resource_exists(conteudo: dict) -> None:
    recursos = conteudo["recursos"]
    refs = [r for it in conteudo["competencias"]["itens"] for r in it["recursos"]]
    refs += [r for e in conteudo["recomendacoes"]["etapas"] for r in e["recursos"]]
    missing = sorted(set(refs) - set(recursos))
    assert not missing, f"Recursos referenciados sem cadastro: {missing}"


def test_no_orphan_resources(conteudo: dict) -> None:
    refs = {r for it in conteudo["competencias"]["itens"] for r in it["recursos"]}
    refs |= {r for e in conteudo["recomendacoes"]["etapas"] for r in e["recursos"]}
    orphans = sorted(set(conteudo["recursos"]) - refs)
    assert not orphans, f"Recursos cadastrados e não usados: {orphans}"


def test_resources_are_https_and_free(conteudo: dict) -> None:
    for rid, r in conteudo["recursos"].items():
        assert r["url"].startswith("https://"), rid
        assert r["custo"].startswith("gratuito"), rid
        for key in ("nome", "descricao", "idioma"):
            assert r[key].strip(), (rid, key)


def test_recommendations_structure(conteudo: dict) -> None:
    rec = conteudo["recomendacoes"]
    assert rec["etapas"]
    for e in rec["etapas"]:
        assert e["titulo"] and e["quando"] and e["objetivos"] and e["recursos"]
    assert rec["habitos"]["itens"]
    assert rec["antes_de_trancar"]["itens"]
