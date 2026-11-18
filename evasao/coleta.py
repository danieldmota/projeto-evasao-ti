"""Download dos ZIPs oficiais do INEP e validação dos arquivos."""

import hashlib
import json
import logging
import re
import ssl
import time
import zipfile
from pathlib import PurePosixPath

import httpx
import truststore

from evasao.config import BRUTOS, URL_INEP, caminho_zip

log = logging.getLogger(__name__)


def achar_csv(zf, ano):
    # a pasta raiz muda de nome entre os anos, então procuramos pelo nome do arquivo
    nome = f"MICRODADOS_CADASTRO_CURSOS_{ano}.CSV"
    achados = [m for m in zf.namelist() if PurePosixPath(m).name.upper() == nome]
    if len(achados) != 1:
        raise ValueError(f"{nome} não encontrado (ou repetido) no ZIP")
    return achados[0]


def md5_oficial(zf, nome_csv):
    # cada ZIP traz um md5_*.txt com o md5 do CSV ("<md5> *ARQUIVO.csv")
    for membro in zf.namelist():
        if re.match(r"md5_.*\.txt$", PurePosixPath(membro).name, re.IGNORECASE):
            for linha in zf.read(membro).decode("latin1").splitlines():
                partes = linha.strip().split(maxsplit=1)
                if len(partes) == 2 and partes[1].lstrip("*").upper() == nome_csv.upper():
                    return partes[0].lower()
    return None


def verificar_zip(caminho, ano):
    """Confere se o ZIP abre e se o CSV de cursos bate com o md5 oficial."""
    try:
        zf = zipfile.ZipFile(caminho)
    except zipfile.BadZipFile as erro:
        raise ValueError(f"ZIP inválido ou incompleto: {caminho}") from erro
    with zf:
        membro = achar_csv(zf, ano)
        esperado = md5_oficial(zf, PurePosixPath(membro).name)
        h = hashlib.md5(usedforsecurity=False)
        with zf.open(membro) as f:
            while bloco := f.read(1 << 20):
                h.update(bloco)
        if esperado and h.hexdigest() != esperado:
            raise ValueError(f"md5 do CSV não confere ({h.hexdigest()} != {esperado})")
        return membro, esperado is not None


def ler_registro(pasta=BRUTOS):
    arq = pasta / "downloads.json"
    return json.loads(arq.read_text(encoding="utf-8")) if arq.exists() else {}


def salvar_registro(ano, url, cabecalho, pasta=BRUTOS):
    registro = ler_registro(pasta)
    registro[str(ano)] = {
        "url": url,
        "size": int(cabecalho.get("content-length", 0)) or None,
        "last_modified": cabecalho.get("last-modified"),
        "etag": cabecalho.get("etag"),
    }
    (pasta / "downloads.json").write_text(json.dumps(registro, indent=2), encoding="utf-8")


def baixar_ano(ano, pasta=BRUTOS, forcar=False, tentativas=4):
    pasta.mkdir(parents=True, exist_ok=True)
    url = URL_INEP.format(ano=ano)
    destino = caminho_zip(ano, pasta)
    parcial = destino.with_suffix(".zip.part")
    # o servidor do INEP manda a cadeia de certificados incompleta; o truststore usa os
    # certificados do sistema operacional, que completam a cadeia (não desligamos o TLS)
    contexto = truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    with httpx.Client(verify=contexto, timeout=120, follow_redirects=True) as cliente:
        for tentativa in range(1, tentativas + 1):
            try:
                cab = cliente.head(url)
                cab.raise_for_status()
                tamanho = int(cab.headers.get("content-length", 0))
                ja_tem = destino.exists() and (not tamanho or destino.stat().st_size == tamanho)
                if ja_tem and not forcar:
                    log.info("%s já baixado", ano)
                    if str(ano) not in ler_registro(pasta):
                        salvar_registro(ano, url, cab.headers, pasta)
                    return destino

                log.info("baixando %s", url)
                with cliente.stream("GET", url) as resp, parcial.open("wb") as f:
                    resp.raise_for_status()
                    for bloco in resp.iter_bytes(1 << 20):
                        f.write(bloco)
                if tamanho and parcial.stat().st_size != tamanho:
                    raise ValueError(f"download incompleto ({parcial.stat().st_size} de {tamanho})")
                verificar_zip(parcial, ano)
                parcial.replace(destino)
                salvar_registro(ano, url, cab.headers, pasta)
                return destino
            except httpx.HTTPStatusError as erro:
                if erro.response.status_code < 500:
                    raise  # 404 = ano ainda não publicado, não adianta tentar de novo
                log.warning("tentativa %d de %s falhou: %s", tentativa, ano, erro)
            except (httpx.TransportError, ValueError) as erro:
                if "CERTIFICATE_VERIFY_FAILED" in str(erro):
                    raise
                log.warning("tentativa %d de %s falhou: %s", tentativa, ano, erro)
            finally:
                parcial.unlink(missing_ok=True)
            time.sleep(2**tentativa)
    raise RuntimeError(f"não foi possível baixar {ano} depois de {tentativas} tentativas")
