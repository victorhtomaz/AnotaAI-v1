from anotai.domain.entities.IntervaloExplicativo import IntervaloExplicativo
from anotai.domain.entities.SegmentoTranscricao import SegmentoTranscricao
from anotai.domain.value_objects.IntervaloTempo import IntervaloTempo


class AgrupadorIntervalos:
    def __init__(
        self,
        limiar_silencio: float = 1.5,
        duracao_minima: float = 10.0,
        duracao_maxima: float = 45.0,
    ) -> None:
        self.limiar_silencio = limiar_silencio
        self.duracao_minima = duracao_minima
        self.duracao_maxima = duracao_maxima

    def agrupar(
        self,
        segmentos: list[SegmentoTranscricao],
        id_aula: str,
    ) -> list[IntervaloExplicativo]:
        if not segmentos:
            return []

        intervalos: list[IntervaloExplicativo] = []
        buffer: list[SegmentoTranscricao] = []
        ordem = 1

        for seg in segmentos:
            if not buffer:
                buffer.append(seg)
                continue

            duracao_buffer = buffer[-1].intervalo.fim - buffer[0].intervalo.inicio
            duracao_com_novo = seg.intervalo.fim - buffer[0].intervalo.inicio
            silencio = seg.intervalo.inicio - buffer[-1].intervalo.fim
            ultimo_texto = buffer[-1].texto.rstrip()
            termina_sentenca = any(
                ultimo_texto.endswith(p) for p in (".", "!", "?", "...", ":", ";")
            )

            atingiu_maximo = duracao_com_novo > self.duracao_maxima
            atingiu_condicao_corte = duracao_buffer >= self.duracao_minima and (
                silencio >= self.limiar_silencio or termina_sentenca
            )

            if atingiu_maximo or atingiu_condicao_corte:
                intervalos.append(self._criar_intervalo(buffer, id_aula, ordem))
                ordem += 1
                buffer = [seg]
            else:
                buffer.append(seg)

        if buffer:
            intervalos.append(self._criar_intervalo(buffer, id_aula, ordem))

        return intervalos

    @staticmethod
    def _criar_intervalo(
        buffer: list[SegmentoTranscricao],
        id_aula: str,
        ordem: int,
    ) -> IntervaloExplicativo:
        inicio = buffer[0].intervalo.inicio
        fim = buffer[-1].intervalo.fim
        texto = " ".join(s.texto.strip() for s in buffer if s.texto.strip())
        id_intervalo = f"interval-{id_aula}-{ordem:04d}"

        return IntervaloExplicativo(
            id_intervalo=id_intervalo,
            id_aula=id_aula,
            texto=texto,
            intervalo=IntervaloTempo(inicio=inicio, fim=fim),
            ordem=ordem,
            ids_segmentos=[s.id_segmento for s in buffer],
            tipo="explanation",
        )
