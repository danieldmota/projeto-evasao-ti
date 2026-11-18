"""Acesso somente leitura ao warehouse (usado pela API).

Carrega as tabelas pequenas em memória e recarrega automaticamente quando o arquivo do
warehouse é substituído por um novo build (detecção por mtime/tamanho).
"""

from __future__ import annotations

import json
import threading
from dataclasses import dataclass
from pathlib import Path

import duckdb
import pandas as pd


class WarehouseUnavailable(Exception):
    pass


@dataclass
class Snapshot:
    stamp: tuple[float, int]
    fact: pd.DataFrame
    anos: pd.DataFrame
    rotulos: pd.DataFrame
    mudancas: pd.DataFrame
    build_info: dict


class Repository:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._snap: Snapshot | None = None
        self._lock = threading.Lock()

    def _stamp(self) -> tuple[float, int]:
        st = self.path.stat()
        return (st.st_mtime, st.st_size)

    def snapshot(self) -> Snapshot:
        if not self.path.exists():
            raise WarehouseUnavailable(
                "Base consolidada não encontrada. Execute 'evasao-ti update' ou 'evasao-ti build'."
            )
        stamp = self._stamp()
        with self._lock:
            if self._snap is None or self._snap.stamp != stamp:
                self._snap = self._load(stamp)
            return self._snap

    def _load(self, stamp: tuple[float, int]) -> Snapshot:
        con = duckdb.connect(str(self.path), read_only=True)
        try:
            fact = con.execute("SELECT * FROM fact_rotulo").df()
            anos = con.execute("SELECT * FROM anos ORDER BY ano").df()
            rotulos = con.execute("SELECT * FROM rotulos ORDER BY co_cine_rotulo").df()
            mudancas = con.execute("SELECT * FROM cine_mudancas ORDER BY ano").df()
            info_rows = con.execute("SELECT key, value FROM build_info").fetchall()
        finally:
            con.close()
        for col in (
            "qt_cursos",
            "ingressantes",
            "matriculas",
            "concluintes",
            "trancadas",
            "desvinculados",
            "transferidos",
            "falecidos",
        ):
            fact[col] = fact[col].astype("Int64")
        fact["ano"] = fact["ano"].astype(int)
        info = {k: json.loads(v) for k, v in info_rows}
        return Snapshot(stamp, fact, anos, rotulos, mudancas, info)

    def available(self) -> bool:
        return self.path.exists()
