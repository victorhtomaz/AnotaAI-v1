from __future__ import annotations

from collections.abc import Sequence

from anotai.application.ports import (
    RepositorioAlinhamento,
    RepositorioAula,
    RepositorioDocumento,
)
from anotai.domain.entities import Alinhamento, Aula
from anotai.domain.value_objects import OrigemAlinhamento


class ConsultarAcervo:
    """Caso de uso de consulta para relacionar documentos, aulas e vínculos ativos."""

    def __init__(
        self,
        repo_doc: RepositorioDocumento,
        repo_aula: RepositorioAula,
        repo_alin: RepositorioAlinhamento,
    ) -> None:
        self.repo_doc = repo_doc
        self.repo_aula = repo_aula
        self.repo_alin = repo_alin

    def resolver_aula_para_documento(
        self,
        id_documento: str,
        id_aula_param: str | None = None,
        id_aula_sugerida: str | None = None,
        *,
        aulas_precarregadas: list[Aula] | None = None,
    ) -> tuple[Aula | None, list[Alinhamento]]:
        """Resolve a aula associada a um documento e seus alinhamentos existentes."""
        if id_aula_param:
            aula = self.repo_aula.buscar_por_id(id_aula_param)
            if aula is None:
                raise LookupError(f"Aula '{id_aula_param}' não encontrada no banco de dados.")
            alins = self.repo_alin.listar_por_aula(aula.id_aula, id_documento=id_documento)
            return aula, alins

        aulas = aulas_precarregadas if aulas_precarregadas is not None else self.repo_aula.listar()
        for aula in aulas:
            alins = self.repo_alin.listar_por_aula(aula.id_aula, id_documento=id_documento)
            if alins:
                return aula, alins

        if id_aula_sugerida:
            aula_mem = next((a for a in aulas if a.id_aula == id_aula_sugerida), None)
            if aula_mem is None:
                aula_mem = self.repo_aula.buscar_por_id(id_aula_sugerida)
            if aula_mem is not None:
                return aula_mem, []

        if len(aulas) == 1:
            return aulas[0], []

        return None, []

    @staticmethod
    def selecionar_vinculos_ativos(
        alinhamentos: Sequence[Alinhamento],
    ) -> dict[str, Alinhamento]:
        """Seleciona o vínculo ativo por intervalo, priorizando revisões manuais."""
        ativos: dict[str, Alinhamento] = {}
        for alinhamento in alinhamentos:
            atual = ativos.get(alinhamento.id_intervalo)
            eh_manual = alinhamento.origem == OrigemAlinhamento.MANUAL.value
            atual_eh_manual = atual is not None and atual.origem == OrigemAlinhamento.MANUAL.value
            if atual is None or (eh_manual and not atual_eh_manual):
                ativos[alinhamento.id_intervalo] = alinhamento
        return ativos
