"""Contratos (Pydantic) para o futuro formulário vocacional.

Status: **rascunho de contrato**. Não há rotas publicadas que usem estes modelos, nem
perguntas ou algoritmo de pontuação: ambos dependem do HTML/questionário que será fornecido.
Ver docs/INTEGRACAO_FRONTEND.md para fluxo, versionamento e requisitos de LGPD.

Princípios:
- o questionário e o algoritmo são versionados (``questionnaire_version``, ``scoring_version``)
  para que um resultado possa ser reproduzido/auditado;
- o resultado é "orientação", nunca diagnóstico (``disclaimer`` obrigatório);
- respostas do teste são anônimas por padrão (``session_id`` aleatório gerado no cliente);
- dados de contato só existem no registro de participação, com consentimento explícito.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field

DISCLAIMER = (
    "Este resultado é uma ferramenta de orientação para reflexão sobre interesses. "
    "Não é um diagnóstico psicológico nem um teste validado."
)


class Answer(BaseModel):
    question_id: Annotated[str, Field(min_length=1, max_length=64)]
    # Valor genérico até o questionário existir: escala (int), opção (str) ou múltipla escolha
    value: int | str | list[str]


class VocationalSubmission(BaseModel):
    """POST /api/v1/vocational/submissions (planejado)."""

    session_id: UUID = Field(
        description="UUID aleatório gerado no navegador; não identifica pessoa"
    )
    questionnaire_id: str
    questionnaire_version: str
    answers: Annotated[list[Answer], Field(min_length=1, max_length=200)]
    locale: str = "pt-BR"


class AreaAffinity(BaseModel):
    area_code: str = Field(description="Código de área definido pelo questionário (não INEP)")
    area_label: str
    score: float = Field(ge=0, le=1, description="Pontuação normalizada 0–1")
    rank: int = Field(ge=1)


class VocationalResult(BaseModel):
    session_id: UUID
    questionnaire_version: str
    scoring_version: str
    affinities: list[AreaAffinity]
    disclaimer: str = DISCLAIMER


class ItInterest(StrEnum):
    sim = "sim"
    nao = "nao"
    talvez = "talvez"


class ItInterestRecord(BaseModel):
    """POST /api/v1/vocational/it-interest (planejado). Anônimo."""

    session_id: UUID
    interest: ItInterest


class Consent(BaseModel):
    granted: bool = Field(description="Precisa ser true para o registro ser aceito")
    purpose_code: str = Field(
        description="Finalidade específica, ex.: 'contato_projeto_prevencao_evasao_ti'"
    )
    privacy_policy_version: str
    granted_at: datetime


class ProjectParticipation(BaseModel):
    """POST /api/v1/participation (planejado). Único contrato com dados pessoais."""

    session_id: UUID | None = Field(
        None, description="Opcional: vincula ao teste só se o titular consentir"
    )
    name: Annotated[str, Field(min_length=1, max_length=120)]
    email: EmailStr
    consent: Consent
    # Minimização: nada de CPF, endereço, data de nascimento, etc.
