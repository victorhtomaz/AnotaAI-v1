from anotai.domain.entities.Alinhamento import Alinhamento
from anotai.domain.entities.Anotacao import Anotacao
from anotai.domain.entities.Aula import Aula
from anotai.domain.entities.Documento import Documento
from anotai.domain.exceptions.ErroIntegridade import ErroIntegridade


class ValidadorIntegridade:
    """Valida a integridade estrutural interna e referencial cruzada entre entidades do domínio."""

    @classmethod
    def validar_documento(cls, documento: Documento) -> None:
        if not documento.id_documento:
            raise ErroIntegridade("Documento possui id_documento vazio")
        if not documento.paginas:
            raise ErroIntegridade(
                f"Documento '{documento.id_documento}' não possui nenhuma página associada"
            )

        ids_paginas: set[str] = set()
        numeros_paginas: set[int] = set()
        ids_unidades: set[str] = set()

        for pagina in documento.paginas:
            if pagina.id_pagina in ids_paginas:
                raise ErroIntegridade(
                    f"Página duplicada '{pagina.id_pagina}' no documento '{documento.id_documento}'"
                )
            ids_paginas.add(pagina.id_pagina)

            if pagina.numero_pagina in numeros_paginas:
                raise ErroIntegridade(
                    f"Número de página duplicado '{pagina.numero_pagina}' "
                    f"no documento '{documento.id_documento}'"
                )
            numeros_paginas.add(pagina.numero_pagina)

            for unidade in pagina.unidades:
                if unidade.id_documento != documento.id_documento:
                    msg = (
                        f"Unidade '{unidade.id_unidade}' pertence ao documento "
                        f"'{unidade.id_documento}', esperado '{documento.id_documento}'"
                    )
                    raise ErroIntegridade(msg)
                if unidade.id_pagina != pagina.id_pagina:
                    raise ErroIntegridade(
                        f"Unidade '{unidade.id_unidade}' referencia página '{unidade.id_pagina}', "
                        f"mas está na página '{pagina.id_pagina}'"
                    )
                if unidade.id_unidade in ids_unidades:
                    msg = (
                        f"Unidade duplicada '{unidade.id_unidade}' "
                        f"no documento '{documento.id_documento}'"
                    )
                    raise ErroIntegridade(msg)
                ids_unidades.add(unidade.id_unidade)

    @classmethod
    def validar_aula(cls, aula: Aula) -> None:
        if not aula.id_aula:
            raise ErroIntegridade("Aula possui id_aula vazio")

        ids_segmentos_existentes: set[str] = set()
        for idx, segmento in enumerate(aula.segmentos, start=1):
            if segmento.id_aula != aula.id_aula:
                raise ErroIntegridade(
                    f"Segmento '{segmento.id_segmento}' referencia aula '{segmento.id_aula}', "
                    f"mas pertence à aula '{aula.id_aula}'"
                )
            if segmento.id_segmento in ids_segmentos_existentes:
                raise ErroIntegridade(
                    f"Segmento duplicado '{segmento.id_segmento}' na aula '{aula.id_aula}'"
                )
            ids_segmentos_existentes.add(segmento.id_segmento)

            if segmento.ordem != idx:
                raise ErroIntegridade(
                    f"Segmento '{segmento.id_segmento}' tem ordem {segmento.ordem}, "
                    f"esperada ordem sequencial {idx}"
                )

        ids_intervalos_existentes: set[str] = set()
        for idx, intervalo in enumerate(aula.intervalos, start=1):
            if intervalo.id_aula != aula.id_aula:
                raise ErroIntegridade(
                    f"Intervalo '{intervalo.id_intervalo}' referencia aula '{intervalo.id_aula}', "
                    f"mas pertence à aula '{aula.id_aula}'"
                )
            if intervalo.id_intervalo in ids_intervalos_existentes:
                raise ErroIntegridade(
                    f"Intervalo duplicado '{intervalo.id_intervalo}' na aula '{aula.id_aula}'"
                )
            ids_intervalos_existentes.add(intervalo.id_intervalo)

            if intervalo.ordem != idx:
                raise ErroIntegridade(
                    f"Intervalo '{intervalo.id_intervalo}' tem ordem {intervalo.ordem}, "
                    f"esperada ordem sequencial {idx}"
                )

            for seg_id in intervalo.ids_segmentos:
                if seg_id not in ids_segmentos_existentes:
                    raise ErroIntegridade(
                        f"Intervalo '{intervalo.id_intervalo}' referencia segmento inexistente "
                        f"'{seg_id}' na aula '{aula.id_aula}'"
                    )

    @classmethod
    def validar_alinhamento(
        cls,
        alinhamento: Alinhamento,
        aula: Aula | None = None,
        documento: Documento | None = None,
    ) -> None:
        if aula is not None:
            if alinhamento.id_aula != aula.id_aula:
                raise ErroIntegridade(
                    f"Alinhamento referencia aula '{alinhamento.id_aula}', "
                    f"mas foi validado contra a aula '{aula.id_aula}'"
                )
            intervalos_aula = {i.id_intervalo for i in aula.intervalos}
            if alinhamento.id_intervalo not in intervalos_aula:
                raise ErroIntegridade(
                    f"Intervalo '{alinhamento.id_intervalo}' do alinhamento não existe "
                    f"na aula '{aula.id_aula}'"
                )

        if documento is not None:
            if alinhamento.id_documento != documento.id_documento:
                raise ErroIntegridade(
                    f"Alinhamento referencia documento '{alinhamento.id_documento}', "
                    f"mas foi validado contra o documento '{documento.id_documento}'"
                )

            mapa_paginas = {p.id_pagina: p for p in documento.paginas}
            mapa_unidades = {
                u.id_unidade: u for p in documento.paginas for u in p.unidades
            }

            for id_pag in alinhamento.ids_paginas:
                if id_pag not in mapa_paginas:
                    raise ErroIntegridade(
                        f"Página '{id_pag}' referenciada no alinhamento não pertence "
                        f"ao documento '{documento.id_documento}'"
                    )

            for id_unidade in alinhamento.ids_unidades:
                if id_unidade not in mapa_unidades:
                    raise ErroIntegridade(
                        f"Unidade '{id_unidade}' referenciada no alinhamento não pertence "
                        f"ao documento '{documento.id_documento}'"
                    )
                unidade = mapa_unidades[id_unidade]
                if unidade.eh_decorativa:
                    raise ErroIntegridade(
                        f"Unidade '{id_unidade}' é marcada como decorativa e não pode "
                        f"participar de alinhamento"
                    )
                if unidade.id_pagina not in alinhamento.ids_paginas:
                    raise ErroIntegridade(
                        f"Inconsistência hierárquica: unidade '{id_unidade}' pertence à página "
                        f"'{unidade.id_pagina}', que não foi incluída em ids_paginas do alinhamento"
                    )

    @classmethod
    def validar_anotacao(
        cls,
        anotacao: Anotacao,
        aula: Aula | None = None,
        documento: Documento | None = None,
    ) -> None:
        if aula is not None:
            if anotacao.id_aula != aula.id_aula:
                raise ErroIntegridade(
                    f"Anotação referencia aula '{anotacao.id_aula}', "
                    f"mas foi validada contra a aula '{aula.id_aula}'"
                )
            if anotacao.id_intervalo is not None:
                intervalos_aula = {i.id_intervalo for i in aula.intervalos}
                if anotacao.id_intervalo not in intervalos_aula:
                    raise ErroIntegridade(
                        f"Intervalo '{anotacao.id_intervalo}' da anotação não existe "
                        f"na aula '{aula.id_aula}'"
                    )

        if documento is not None:
            if anotacao.id_documento != documento.id_documento:
                raise ErroIntegridade(
                    f"Anotação referencia documento '{anotacao.id_documento}', "
                    f"mas foi validada contra o documento '{documento.id_documento}'"
                )

            paginas_doc = {p.id_pagina for p in documento.paginas}
            unidades_doc = {u.id_unidade for p in documento.paginas for u in p.unidades}

            for id_pag in anotacao.ids_paginas:
                if id_pag not in paginas_doc:
                    msg = (
                        f"Página '{id_pag}' da anotação não pertence "
                        f"ao documento '{documento.id_documento}'"
                    )
                    raise ErroIntegridade(msg)

            for id_unidade in anotacao.ids_unidades:
                if id_unidade not in unidades_doc:
                    msg = (
                        f"Unidade '{id_unidade}' da anotação não pertence "
                        f"ao documento '{documento.id_documento}'"
                    )
                    raise ErroIntegridade(msg)
