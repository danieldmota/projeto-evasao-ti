"""Executa os testes JavaScript da jornada (node --test). Pulado se o Node não estiver instalado."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

JS_DIR = Path(__file__).parent / "js"


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js não instalado")
def test_jornada_core_js() -> None:
    files = sorted(str(p) for p in JS_DIR.glob("*.test.js"))
    assert files, "nenhum teste JS encontrado"
    proc = subprocess.run(
        ["node", "--test", *files],
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=120,
        check=False,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
