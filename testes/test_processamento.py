import pytest
from conftest import CABECALHO, linha, linhas_padrao

from evasao.processamento import ler_cursos, processar_ano


def test_le_zip_sintetico(criar_zip):
    df, info = ler_cursos(criar_zip(2023), 2023)
    assert info["md5_ok"]
    assert info["linhas"] == 10
    assert set(df["co_cine_rotulo"]) == {"0615S02", "0915E01", "0113P01", "0011A09", "0732E01",
                                         "9999X99"}  # aspas removidas


def test_ead_soma_municipios_e_mantem_nulos(criar_zip):
    df, _ = ler_cursos(criar_zip(2023), 2023)
    ead = df[df["co_curso"] == "2"].iloc[0]
    assert ead["matriculas"] == 500
    assert ead["trancadas"] == 100
    assert ead["qt_cursos"] == 1  # só a linha TP_DIMENSAO=3 tem QT_CURSO


def test_curso_so_com_nulos_continua_nulo(criar_zip):
    linhas = [linha(2023, 1, "X", "0615S02", dimensao=3, mat="", tranc="", desv="", transf="",
                    fal="", ing="", conc="")]
    df, _ = ler_cursos(criar_zip(2023, linhas), 2023)
    assert df["matriculas"].isna().all()  # sem informação não vira zero


def test_coluna_ausente_falha(criar_zip):
    cabecalho = [c for c in CABECALHO if c != "QT_SIT_TRANCADA"]
    with pytest.raises(ValueError, match="QT_SIT_TRANCADA"):
        ler_cursos(criar_zip(2023, cabecalho=cabecalho), 2023)


def test_valor_nao_numerico_falha(criar_zip):
    linhas = linhas_padrao(2023)
    linhas[0]["QT_MAT"] = "abc"
    with pytest.raises(ValueError, match="não numéricos"):
        ler_cursos(criar_zip(2023, linhas), 2023)


def test_valor_negativo_falha(criar_zip):
    linhas = linhas_padrao(2023)
    linhas[0]["QT_SIT_TRANCADA"] = -5
    with pytest.raises(ValueError, match="negativos"):
        ler_cursos(criar_zip(2023, linhas), 2023)


def test_md5_errado_falha(criar_zip):
    with pytest.raises(ValueError, match="md5"):
        ler_cursos(criar_zip(2023, md5_errado=True), 2023)


def test_ano_divergente_falha(criar_zip):
    caminho = criar_zip(2023, linhas_padrao(2022))
    with pytest.raises(ValueError, match="NU_ANO_CENSO"):
        ler_cursos(caminho, 2023)


def test_apelido_coluna_2020(criar_zip):
    cabecalho = ["CO_CINE_ROTULO2" if c == "CO_CINE_ROTULO" else c for c in CABECALHO]
    linhas = [{**lin, "CO_CINE_ROTULO2": lin["CO_CINE_ROTULO"]} for lin in linhas_padrao(2020)]
    df, _ = ler_cursos(criar_zip(2020, linhas, cabecalho), 2020)
    assert "0615S02" in set(df["co_cine_rotulo"])


def test_rede_derivada_da_categoria(criar_zip):
    linhas = [
        linha(2013, 1, "A", "0615S02", rede="", categoria=1, mat=10),
        linha(2013, 2, "B", "0615S02", rede="", categoria=5, mat=10),
        linha(2013, 3, "C", "0615S02", rede="", categoria=7, mat=10),
    ]
    df, info = ler_cursos(criar_zip(2013, linhas), 2013)
    assert df.set_index("co_curso")["tp_rede"].to_dict() == {"1": "1", "2": "2", "3": "1"}
    assert "TP_REDE" in info["avisos"][0]


def test_processar_pula_ano_sem_mudanca(criar_zip, tmp_path):
    criar_zip(2023)
    pastas = {"brutos": tmp_path / "brutos", "saida": tmp_path / "processados"}
    primeiro = processar_ano(2023, **pastas)
    assert (tmp_path / "processados" / "cursos_2023.parquet").exists()
    parquet = tmp_path / "processados" / "cursos_2023.parquet"
    antes = parquet.stat().st_mtime_ns
    assert processar_ano(2023, **pastas) == primeiro
    assert parquet.stat().st_mtime_ns == antes
