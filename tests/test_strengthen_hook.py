"""Regressão de 2 bugs reais encontrados em 09/10/2026 ao investigar a
auditoria de "sameness" (96% dos últimos 25 vídeos com gancho muito
parecido):

1. strengthen_hook() reescrevia a abertura sem saber qual dos 4
   PROMPT_ANGLES o roteiro original tentou seguir, convergindo sempre pro
   mesmo estilo favorito do LLM - corrigido passando `angle` explicitamente.
2. O guarda-corpo que verifica "o resto do roteiro não mudou" comparava uma
   fatia de tamanho FIXO a partir do fim do texto - rejeitava (sempre,
   silenciosamente) qualquer reescrita onde a nova abertura tivesse um
   tamanho bem diferente da original, que é o caso comum (frase genérica
   virando pergunta/comparação). Corrigido comparando a partir do fim da
   1ª frase do ORIGINAL (_first_sentence_end), não um deslocamento fixo.
"""

from pipeline import script_gen


def test_first_sentence_end_simple():
    text = "Primeira frase aqui mesmo. Segunda frase continua."
    end = script_gen._first_sentence_end(text)
    assert text[:end] == "Primeira frase aqui mesmo."


def test_first_sentence_end_ignores_early_abbreviation():
    # "Dr." nos primeiros 15 caracteres não deve ser tratado como fim de frase.
    text = "Dr. Silva descobriu algo incrível sobre Marte. Isso mudou tudo."
    end = script_gen._first_sentence_end(text)
    assert text[:end] == "Dr. Silva descobriu algo incrível sobre Marte."


def test_first_sentence_end_none_without_punctuation():
    assert script_gen._first_sentence_end("sem pontuação nenhuma aqui") is None


def test_strengthen_hook_accepts_rewrite_with_very_different_length(monkeypatch):
    """O caso real que motivou a correção: abertura curta e genérica virando
    uma pergunta bem mais longa - tinha que ser aceita, e não era."""
    script = (
        "Hoje vamos falar sobre o Monte Olimpo em Marte.\n"
        "O Monte Olimpo tem cerca de 22 km de altura, quase tres vezes o Monte Everest.\n"
        "Cientistas acreditam que ele se formou porque Marte nao tem placas tectonicas moveis."
    )
    rewritten = (
        "ROTEIRO_REVISADO: O que e o Monte Olimpo em Marte e por que e tres vezes maior que o "
        "Monte Everest?\n"
        "O Monte Olimpo tem cerca de 22 km de altura, quase tres vezes o Monte Everest.\n"
        "Cientistas acreditam que ele se formou porque Marte nao tem placas tectonicas moveis."
    )
    monkeypatch.setattr(script_gen, "_call_ollama", lambda prompt, timeout=90: rewritten)

    result = script_gen.strengthen_hook(script, niche="astronomia", angle=script_gen.PROMPT_ANGLES[0])

    assert result.startswith("O que e o Monte Olimpo em Marte")
    assert result != script


def test_strengthen_hook_rejects_when_rest_of_script_changed(monkeypatch):
    """Guarda-corpo original ainda precisa funcionar: se o LLM mexer em
    qualquer coisa além da 1ª frase (ex.: inventar um fato), rejeita tudo e
    devolve o roteiro original - isso é o que impede alucinação na abertura."""
    script = (
        "Hoje vamos falar sobre o Monte Olimpo em Marte.\n"
        "O Monte Olimpo tem cerca de 22 km de altura, quase tres vezes o Monte Everest.\n"
        "Cientistas acreditam que ele se formou porque Marte nao tem placas tectonicas moveis."
    )
    tampered = (
        "ROTEIRO_REVISADO: O maior vulcao ja descoberto em todo o universo fica em Marte!\n"
        "O Monte Olimpo tem cerca de 50 km de altura, dez vezes o Monte Everest.\n"
        "Cientistas acreditam que ele se formou porque Marte nao tem placas tectonicas moveis."
    )
    monkeypatch.setattr(script_gen, "_call_ollama", lambda prompt, timeout=90: tampered)

    result = script_gen.strengthen_hook(script, niche="astronomia", angle=script_gen.PROMPT_ANGLES[0])

    assert result == script


def test_strengthen_hook_rejects_when_llm_returns_nothing(monkeypatch):
    monkeypatch.setattr(script_gen, "_call_ollama", lambda prompt, timeout=90: None)
    script = "Um roteiro qualquer aqui."
    assert script_gen.strengthen_hook(script) == script


def test_strengthen_hook_keeps_original_when_llm_declines_to_change(monkeypatch):
    script = "O planeta Marte tem a maior montanha do sistema solar. Mais detalhes aqui."
    unchanged = f"ROTEIRO_REVISADO: {script}"
    monkeypatch.setattr(script_gen, "_call_ollama", lambda prompt, timeout=90: unchanged)
    assert script_gen.strengthen_hook(script, angle=script_gen.PROMPT_ANGLES[0]) == script


def test_strengthen_hook_passes_angle_into_prompt(monkeypatch):
    captured = {}

    def fake_call(prompt, timeout=90):
        captured["prompt"] = prompt
        return None

    monkeypatch.setattr(script_gen, "_call_ollama", fake_call)
    angle = script_gen.PROMPT_ANGLES[2]
    script_gen.strengthen_hook("Um roteiro.", angle=angle)
    assert angle in captured["prompt"]
