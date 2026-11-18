"""Teste ponta a ponta da jornada em navegador real (Chrome via Playwright).

Sobe a API (warehouse real em data/warehouse) e um servidor estático de web/ em portas
próprias, percorre as 8 etapas no celular e no desktop e verifica regras críticas:
validação, bloqueios, persistência ao recarregar, privacidade (nome/e-mail fora do
sessionStorage), rotas protegidas e ausência de erros de console.

Requer: `pip install -e ".[e2e]"` e Google Chrome instalado. Pulado se faltar algo.
Rodar: `pytest -m e2e`
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

import httpx
import pytest

ROOT = Path(__file__).resolve().parents[2]
WAREHOUSE = ROOT / "data" / "warehouse" / "evasao_ti.duckdb"
API_PORT, WEB_PORT = 8765, 5175

pytestmark = pytest.mark.e2e
playwright_api = pytest.importorskip("playwright.sync_api")


def _wait(url: str, timeout: float = 30) -> None:
    end = time.time() + timeout
    while time.time() < end:
        try:
            if httpx.get(url, timeout=2).status_code == 200:
                return
        except httpx.HTTPError:
            pass
        time.sleep(0.3)
    raise RuntimeError(f"servidor não respondeu: {url}")


@pytest.fixture(scope="module")
def servers():
    if not WAREHOUSE.exists():
        pytest.skip("warehouse ausente; rode 'evasao-ti update' antes")
    env = {
        **os.environ,
        "EVASAO_CORS_ORIGINS": f"http://localhost:{WEB_PORT}",
        "EVASAO_DATA_DIR": str(ROOT / "data"),
        "EVASAO_LOG_LEVEL": "WARNING",
    }
    api = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "evasao_ti.api.app:create_app",
            "--factory",
            "--host",
            "127.0.0.1",
            "--port",
            str(API_PORT),
        ],
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    web = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "http.server",
            str(WEB_PORT),
            "--bind",
            "127.0.0.1",
            "--directory",
            str(ROOT / "web"),
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        _wait(f"http://127.0.0.1:{API_PORT}/api/v1/health")
        _wait(f"http://127.0.0.1:{WEB_PORT}/index.html")
        yield f"http://localhost:{WEB_PORT}/index.html?api=http://127.0.0.1:{API_PORT}/api/v1"
    finally:
        api.terminate()
        web.terminate()


@pytest.fixture(scope="module")
def browser():
    with playwright_api.sync_playwright() as p:
        try:
            b = p.chromium.launch(channel="chrome")
        except Exception as exc:  # pragma: no cover
            pytest.skip(f"Chrome indisponível para o Playwright: {exc}")
        yield b
        b.close()


def _answer_form(page, nxt) -> None:
    nxt()  # tenta avançar sem responder
    assert page.is_visible(".jf-page:not([hidden]) .jf-error")
    page.check("input[name=atividades][value=logica]")
    nxt()
    page.check("input[name=materia][value=informatica]")
    nxt()
    page.eval_on_selector(
        "input[name=gosto_tecnologia]",
        "e=>{e.value=5;e.dispatchEvent(new Event('input',{bubbles:true}))}",
    )
    nxt()
    page.check("input[name=grupo][value=construir]")
    nxt()
    nxt()  # escala com valor padrão
    page.check("input[name=ambiente][value=remoto]")
    nxt()
    page.check("input[name=motivacao][value=criar]")
    nxt()


@pytest.mark.parametrize(
    "viewport",
    [{"width": 390, "height": 844}, {"width": 1280, "height": 860}],
    ids=["mobile", "desktop"],
)
def test_jornada_completa(servers, browser, viewport) -> None:
    ctx = browser.new_context(viewport=viewport)
    page = ctx.new_page()
    errors: list[str] = []
    page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
    page.on("pageerror", lambda e: errors.append(str(e)))
    nxt = lambda: page.click("#j-next")  # noqa: E731

    page.goto(servers)
    page.wait_for_selector(".v-inicio")
    nxt()
    page.wait_for_selector(".jf-form")
    _answer_form(page, nxt)

    page.reload()  # respostas e posição sobrevivem ao recarregar
    page.wait_for_selector(".jf-form")
    assert "8 de 8" in page.inner_text("#q-counter").lower()
    nxt()

    page.wait_for_selector(".v-resultado")
    assert "Tecnologia da Informação" in page.inner_text("h1")
    nxt()
    page.wait_for_selector(".v-interesse")
    page.click("#j-next", force=True)  # bloqueado sem escolha
    assert page.is_visible("#j-hint")
    page.check("input[name=interesse][value=sim]")
    nxt()

    page.wait_for_selector(".v-projeto")
    page.click(".pform [type=submit]")  # consentimento obrigatório
    assert page.is_visible(".pform .jf-error")
    page.fill("input[name=nome]", "Pessoa Teste")
    page.fill("input[name=email]", "teste@example.com")
    page.check("input[name=consentimento]")
    page.click(".pform [type=submit]")
    page.wait_for_selector(".done-box.demonstracao")
    stored = page.evaluate("sessionStorage.getItem('evasao-ti:jornada')")
    assert "teste@example.com" not in stored and "Pessoa" not in stored
    nxt()

    page.wait_for_selector(".v-dados .chart svg")
    nxt()
    page.wait_for_selector(".acc-item")
    nxt()
    page.wait_for_selector(".v-estudos .step h2")
    nxt()
    page.wait_for_selector(".v-fim")
    page.go_back()
    page.wait_for_selector(".v-estudos")

    fresh = browser.new_context(viewport=viewport).new_page()
    fresh.goto(servers + "#/dados")
    fresh.wait_for_selector(".v-inicio")  # rota protegida volta ao início
    fresh.context.close()

    assert errors == [], errors
    ctx.close()
