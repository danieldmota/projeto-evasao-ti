"""Modelos de resposta da API (documentados no OpenAPI)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class Fonte(BaseModel):
    nome: str
    instituicao: str
    url: str
    arquivo: str
    classificacao: str
    nota: str


class Periodo(BaseModel):
    solicitado_inicio: int | None
    solicitado_fim: int | None
    anos_com_dados: list[int]
    anos_ausentes: list[int] = Field(
        description="Anos do intervalo solicitado sem dados processados (não são zero)."
    )


class Classificacao(BaseModel):
    versao_mapeamento: str
    sha256_mapeamento: str | None = None
    regra_ti: str


class Atualizacao(BaseModel):
    build_em: str | None
    versao_codigo: str | None
    detalhes_por_ano: str = "/api/v1/years"


class Paginacao(BaseModel):
    total: int
    limit: int
    offset: int


class Meta(BaseModel):
    fonte: Fonte
    unidade: str
    escopo: str
    metodo: dict[str, Any]
    periodo: Periodo | None = None
    classificacao: Classificacao
    atualizacao: Atualizacao
    filtros: dict[str, Any] = Field(default_factory=dict)
    avisos: list[str] = Field(default_factory=list)
    paginacao: Paginacao | None = None


class Indicadores(BaseModel):
    qt_cursos: int | None = None
    ingressantes: int | None = None
    matriculas: int | None = Field(None, description="QT_MAT: vínculos Cursando + Formado")
    concluintes: int | None = None
    trancadas: int | None = Field(None, description="QT_SIT_TRANCADA")
    desvinculados: int | None = None
    transferidos: int | None = None
    falecidos: int | None = None
    denominador_trancamento: int | None = Field(None, description="matriculas + trancadas")
    vinculos_total: int | None = None
    taxa_trancamento: float | None = Field(None, description="trancadas / (matriculas + trancadas)")
    participacao_trancadas_vinculos: float | None = None
    taxa_desvinculacao: float | None = None


class LinhaAnual(Indicadores):
    ano: int
    grupo_codigo: str
    grupo_nome: str


class LinhaResumo(Indicadores):
    grupo_codigo: str
    grupo_nome: str


class LinhaCurso(Indicadores):
    no_cine_rotulo: str | None = Field(description="Nome padronizado do curso (CINE)")
    codigos_cine: list[str] = Field(
        description="Códigos CINE do rótulo no período (mais de um quando a CINE foi revisada)"
    )
    area: str
    area_nome: str
    segmento: str
    is_ti: bool
    co_cine_area_geral: str | None
    no_cine_area_geral: str | None
    areas_detalhadas: list[str]
    regras: list[str] = Field(description="Regras de correspondência aplicadas (nível:código)")
    confianca: str = Field(description="Confiança mais conservadora entre os códigos")
    anos_com_dados: list[int]
    base_pequena: bool = Field(
        description="True quando o denominador é pequeno (< 100) e a taxa é instável."
    )


class AnnualResponse(BaseModel):
    data: list[LinhaAnual]
    meta: Meta


class SummaryResponse(BaseModel):
    data: list[LinhaResumo]
    meta: Meta


class CoursesResponse(BaseModel):
    data: list[LinhaCurso]
    meta: Meta


class AnoInfo(BaseModel):
    ano: int
    status: str = Field(description="'disponivel' ou 'ausente'")
    esperado: bool
    comparabilidade: str | None = Field(
        None, description="'comparavel' ou 'atencao' (ver alertas e notas)"
    )
    alertas_automaticos: list[str] = Field(default_factory=list)
    notas_curadas: list[str] = Field(default_factory=list)
    arquivo_fonte: str | None
    url_fonte: str | None
    fonte_last_modified: str | None
    md5_oficial_verificado: bool | None
    processado_em: str | None
    linhas_lidas: int | None
    avisos: list[str]


class YearsResponse(BaseModel):
    data: list[AnoInfo]
    meta: Meta


class AreaInfo(BaseModel):
    codigo: str
    nome: str
    tipo: str = Field(description="'area' (4 áreas do projeto) ou 'segmento' (TI separada)")
    rotulos_cine: int


class RegraMapeamento(BaseModel):
    nivel: str
    codigo: str
    descricao_cine: str
    area: str
    confianca: str
    justificativa: str


class AreasResponse(BaseModel):
    data: list[AreaInfo]
    regras: list[RegraMapeamento]
    meta: Meta


class RotuloInfo(BaseModel):
    co_cine_rotulo: str | None
    no_cine_rotulo: str | None
    nomes_distintos: int
    co_cine_area_geral: str | None
    no_cine_area_geral: str | None
    co_cine_area_detalhada: str | None
    no_cine_area_detalhada: str | None
    area: str
    segmento: str
    is_ti: bool
    regra_nivel: str | None
    regra_codigo: str | None
    confianca: str
    justificativa: str
    motivo: str
    primeiro_ano: int
    ultimo_ano: int
    anos: list[int]


class RotulosResponse(BaseModel):
    data: list[RotuloInfo]
    meta: Meta


class MudancaCine(BaseModel):
    ano: int
    rotulos_presentes: int
    rotulos_novos: list[str]
    rotulos_ausentes_vs_ano_anterior: list[str]


class ChangesResponse(BaseModel):
    data: list[MudancaCine]
    meta: Meta


class HealthResponse(BaseModel):
    status: str
    versao: str
    warehouse: bool
    build_em: str | None = None
    anos_disponiveis: list[int] = Field(default_factory=list)


class ErrorBody(BaseModel):
    code: str
    message: str
    details: Any | None = None


class ErrorResponse(BaseModel):
    error: ErrorBody
