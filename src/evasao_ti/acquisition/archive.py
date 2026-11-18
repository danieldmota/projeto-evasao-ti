"""Inspeção e validação dos ZIPs oficiais.

Observado nos ZIPs reais (2009, 2016, 2023):
- a pasta raiz muda de nome entre anos (ex.: "Microdados do Censo da Educação Superior 2009/"
  vs. "microdados_censo_da_educacao_superior_2023/") e os nomes antigos usam codificação
  cp437 no ZIP — por isso o CSV é localizado pelo *nome do arquivo*, não pelo caminho;
- cada ZIP traz ``dados/md5_microdados_ed_superior_AAAA.txt`` com o MD5 oficial do CSV,
  que usamos para validar a integridade do conteúdo extraído.
"""

from __future__ import annotations

import hashlib
import re
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

CURSOS_MEMBER_RE = re.compile(r"^MICRODADOS_CADASTRO_CURSOS_(\d{4})\.CSV$", re.IGNORECASE)
MD5_MEMBER_RE = re.compile(r"^md5_.*\.txt$", re.IGNORECASE)
_MD5_LINE_RE = re.compile(r"^([0-9a-fA-F]{32})\s+\*?(.+?)\s*$")


class ArchiveError(Exception):
    """ZIP ausente, corrompido, incompleto ou com conteúdo inesperado."""


@dataclass(frozen=True)
class ArchiveInfo:
    path: Path
    member: str
    year: int
    member_size: int
    md5_expected: str | None
    md5_verified: bool


def _basename(name: str) -> str:
    return PurePosixPath(name).name


def find_cursos_member(zf: zipfile.ZipFile, expected_year: int | None = None) -> tuple[str, int]:
    candidates = []
    for name in zf.namelist():
        m = CURSOS_MEMBER_RE.match(_basename(name))
        if m:
            candidates.append((name, int(m.group(1))))
    if not candidates:
        raise ArchiveError("MICRODADOS_CADASTRO_CURSOS_AAAA.CSV não encontrado no ZIP")
    if len(candidates) > 1:
        raise ArchiveError(f"Mais de um CSV de cursos no ZIP: {[c[0] for c in candidates]}")
    name, year = candidates[0]
    if expected_year is not None and year != expected_year:
        raise ArchiveError(f"ZIP do ano {expected_year} contém CSV do ano {year}")
    return name, year


def read_md5_manifest(zf: zipfile.ZipFile) -> dict[str, str]:
    """Retorna {NOME_ARQUIVO_MAIUSCULO: md5} a partir do arquivo md5_*.txt oficial."""
    result: dict[str, str] = {}
    for name in zf.namelist():
        if MD5_MEMBER_RE.match(_basename(name)):
            text = zf.read(name).decode("latin1")
            for line in text.splitlines():
                m = _MD5_LINE_RE.match(line.strip())
                if m:
                    result[m.group(2).upper()] = m.group(1).lower()
    return result


def md5_of_member(zf: zipfile.ZipFile, member: str, chunk: int = 1 << 20) -> str:
    h = hashlib.md5(usedforsecurity=False)
    with zf.open(member) as f:
        while block := f.read(chunk):
            h.update(block)
    return h.hexdigest()


def sha256_of_file(path: Path, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while block := f.read(chunk):
            h.update(block)
    return h.hexdigest()


def inspect_archive(
    path: Path, expected_year: int | None = None, verify_md5: bool = True
) -> ArchiveInfo:
    """Valida o ZIP (estrutura, CRC do membro relevante, MD5 oficial) e localiza o CSV."""
    if not path.exists():
        raise ArchiveError(f"Arquivo não encontrado: {path}")
    try:
        zf = zipfile.ZipFile(path)
    except zipfile.BadZipFile as exc:
        raise ArchiveError(f"ZIP inválido ou incompleto: {path} ({exc})") from exc
    with zf:
        member, year = find_cursos_member(zf, expected_year)
        info = zf.getinfo(member)
        md5_expected = read_md5_manifest(zf).get(_basename(member).upper())
        verified = False
        if verify_md5:
            try:
                actual = md5_of_member(zf, member)  # também valida o CRC do zip
            except (zipfile.BadZipFile, OSError, EOFError) as exc:
                raise ArchiveError(f"Conteúdo corrompido em {member}: {exc}") from exc
            if md5_expected is not None:
                if actual != md5_expected:
                    raise ArchiveError(
                        f"MD5 divergente para {member}: esperado {md5_expected}, obtido {actual}"
                    )
                verified = True
        return ArchiveInfo(
            path=path,
            member=member,
            year=year,
            member_size=info.file_size,
            md5_expected=md5_expected,
            md5_verified=verified,
        )
