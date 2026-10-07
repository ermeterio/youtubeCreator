"""Capítulos automáticos (YouTube Chapters) a partir do mesmo timing por
palavra que já existe pra legendas/b-roll por trecho - SEM nenhuma chamada
nova ao LLM, só formatação de dado que o pipeline já calcula.

Regras exigidas pelo YouTube (confirmadas por pesquisa real, 07/10/2026 -
vidIQ "YouTube SEO 2026", Zubtitle guia de capítulos):
- O primeiro timestamp precisa ser EXATAMENTE 0:00 - sem isso o YouTube
  ignora TODOS os capítulos silenciosamente, não só o primeiro.
- Mínimo de 3 capítulos.
- Cada capítulo precisa ter pelo menos 10 segundos.
- Formato M:SS (ou H:MM:SS pra vídeos de 1h+), em ordem crescente, um por
  linha na descrição.
"""

MIN_CHAPTER_SECONDS = 10.0
MIN_CHAPTERS = 3
MAX_TITLE_WORDS = 6


def _format_timestamp(seconds: float) -> str:
    total = int(seconds)
    h, rem = divmod(total, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


def _chapter_title(paragraph: str) -> str:
    words = paragraph.strip().split()[:MAX_TITLE_WORDS]
    title = " ".join(words).rstrip(".,;:!?-")
    return title or "Trecho"


def build_chapters(script: str, boundaries: list[dict]) -> list[tuple[float, str]] | None:
    """Retorna [(segundos, título), ...] com o 1º item SEMPRE em 0.0, ou
    None se não der pra formar pelo menos MIN_CHAPTERS capítulos válidos
    (roteiro curto demais, boundaries ausentes, ou timing inconsistente) -
    nesse caso o chamador simplesmente não inclui capítulos na descrição,
    sem quebrar nada. Nunca lança exceção."""
    try:
        paragraphs = [p.strip() for p in script.split("\n") if p.strip()]
        if len(paragraphs) < 2 or not boundaries:
            return None

        word_counts = [len(p.split()) for p in paragraphs]
        total_words = sum(word_counts)
        if total_words == 0 or len(boundaries) < total_words * 0.5:
            # Mismatch grande entre nº de palavras do roteiro e nº de
            # boundaries reais (acontece quando o texto foi expandido pra
            # narração - ver text_normalize.py, "km/s" vira 3 palavras) -
            # não arrisca gerar capítulo mal alinhado nesse caso.
            return None

        # Mesma técnica já usada em script_gen._compute_image_durations/
        # _segment_keywords: distribui os boundaries proporcionalmente ao
        # nº de palavras de cada parágrafo do roteiro ORIGINAL (não do
        # texto normalizado pro TTS, que pode ter mais palavras).
        ratio = len(boundaries) / total_words
        raw_chapters: list[list] = []
        idx = 0
        for paragraph, count in zip(paragraphs, word_counts):
            n = max(1, round(count * ratio))
            group = boundaries[idx: idx + n]
            idx += n
            if not group:
                continue
            raw_chapters.append([group[0]["start"], _chapter_title(paragraph)])

        if not raw_chapters:
            return None
        raw_chapters[0][0] = 0.0  # exigência do YouTube - sem exceção

        # Funde um capítulo no anterior se ficar abaixo do mínimo de 10s -
        # só pula a entrada (o capítulo anterior "absorve" esse trecho).
        merged: list[list] = []
        for start, title in raw_chapters:
            if merged and (start - merged[-1][0]) < MIN_CHAPTER_SECONDS:
                continue
            merged.append([start, title])

        if len(merged) < MIN_CHAPTERS:
            return None
        return [(start, title) for start, title in merged]
    except Exception:
        return None


def format_chapters_for_description(chapters: list[tuple[float, str]]) -> str:
    return "\n".join(f"{_format_timestamp(start)} {title}" for start, title in chapters)
