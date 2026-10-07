from pipeline import chapters


def _boundaries_for(paragraphs: list[str], seconds_per_word: float = 0.4):
    """Gera boundaries sintéticos mas com o mesmo formato real (start
    crescente, 1 por palavra) - não é preciso áudio de verdade pra testar a
    lógica de distribuição proporcional e junção de capítulos curtos."""
    boundaries = []
    t = 0.0
    for p in paragraphs:
        for _ in p.split():
            boundaries.append({"text": "", "start": t, "duration": seconds_per_word})
            t += seconds_per_word
    return boundaries


def test_single_paragraph_script_returns_none():
    script = "Um parágrafo só, sem quebras de linha, não dá pra formar capítulos."
    boundaries = _boundaries_for([script])
    assert chapters.build_chapters(script, boundaries) is None


def test_no_boundaries_returns_none():
    script = "Primeiro parágrafo aqui.\nSegundo parágrafo aqui.\nTerceiro parágrafo aqui."
    assert chapters.build_chapters(script, []) is None


def test_four_paragraphs_real_shaped_script_produces_chapters():
    paragraphs = [
        "O telescópio espacial James Webb capturou uma imagem inédita da nebulosa de Órion esta semana.",
        "A nova imagem revela detalhes nunca vistos antes da formação de estrelas na região central.",
        "Cientistas da NASA afirmam que os dados vão ajudar a entender melhor o nascimento de sistemas solares.",
        "O próximo passo é comparar essas observações com dados do telescópio Hubble feitos há vinte anos.",
    ]
    script = "\n".join(paragraphs)
    # 0.8s/palavra pra cada parágrafo (~15 palavras) durar bem mais que os
    # 10s mínimos por capítulo - narração real roda por volta de 2-3
    # palavras/segundo, então isso é conservador, não otimista.
    boundaries = _boundaries_for(paragraphs, seconds_per_word=0.8)

    result = chapters.build_chapters(script, boundaries)

    assert result is not None
    assert len(result) >= chapters.MIN_CHAPTERS
    assert result[0][0] == 0.0
    starts = [start for start, _ in result]
    assert starts == sorted(starts)
    for a, b in zip(starts, starts[1:]):
        assert (b - a) >= chapters.MIN_CHAPTER_SECONDS


def test_chapters_merge_when_under_minimum_duration():
    # 5 parágrafos bem curtos e rápidos - boundaries rápidos o bastante pra
    # alguns capítulos nascerem abaixo de 10s e precisarem ser fundidos.
    paragraphs = [f"Parágrafo número {i} curto aqui." for i in range(1, 6)]
    script = "\n".join(paragraphs)
    boundaries = _boundaries_for(paragraphs, seconds_per_word=0.3)

    result = chapters.build_chapters(script, boundaries)

    if result is not None:
        starts = [start for start, _ in result]
        for a, b in zip(starts, starts[1:]):
            assert (b - a) >= chapters.MIN_CHAPTER_SECONDS


def test_word_boundary_mismatch_returns_none():
    script = "Primeiro parágrafo com várias palavras aqui dentro.\nSegundo parágrafo também com várias palavras."
    # Muito menos boundaries do que metade das palavras do roteiro - mismatch grande, deve abortar.
    boundaries = [{"text": "", "start": 0.0, "duration": 0.3}]
    assert chapters.build_chapters(script, boundaries) is None


def test_format_chapters_for_description():
    result = chapters.format_chapters_for_description([(0.0, "Intro"), (75.0, "Meio"), (610.0, "Final")])
    assert result == "0:00 Intro\n1:15 Meio\n10:10 Final"
