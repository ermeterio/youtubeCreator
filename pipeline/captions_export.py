"""Exporta a narração em formato .srt pra upload como legenda real do
YouTube - reaproveita o MESMO agrupamento de palavras já usado pra queimar
legenda no vídeo (video_build._group_captions), então o arquivo .srt fica
idêntico ao que aparece na tela, sem nenhuma lógica nova de segmentação.

Por que isso importa (achado de pesquisa, 07/10/2026): o YouTube indexa o
TEXTO da legenda pra busca - uma transcrição de ~10min rende 1500-2000
palavras pesquisáveis contra as 30-50 da descrição, e legenda carregada
manualmente (vs. a auto-gerada pelo YouTube) indexa com mais precisão,
principalmente em vocabulário técnico de nicho (nomes de objetos
astronômicos, termos científicos) que o reconhecimento automático erra.
"""


def _srt_timestamp(seconds: float) -> str:
    total_ms = round(max(seconds, 0.0) * 1000)
    h, rem = divmod(total_ms, 3_600_000)
    m, rem = divmod(rem, 60_000)
    s, ms = divmod(rem, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def build_srt(boundaries: list[dict]) -> str | None:
    """Monta o conteúdo de um arquivo .srt a partir dos WordBoundary da
    narração - None se não houver boundaries (nunca lança exceção, pra não
    travar a publicação do vídeo por causa da legenda)."""
    if not boundaries:
        return None
    try:
        from pipeline.video_build import _group_captions
        groups = _group_captions(boundaries)
    except Exception:
        return None
    if not groups:
        return None

    lines = []
    for i, group in enumerate(groups, start=1):
        lines.append(str(i))
        lines.append(f"{_srt_timestamp(group['start'])} --> {_srt_timestamp(group['end'])}")
        lines.append(group["text"])
        lines.append("")
    return "\n".join(lines)
