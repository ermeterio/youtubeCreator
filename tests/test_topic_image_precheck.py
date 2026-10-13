"""Regressão de um problema arquitetural real relatado pelo dono (13/10/2026,
depois de uma madrugada com vários erros empilhados): o pipeline escolhia o
tema da rotação TOTALMENTE às cegas quanto a disponibilidade de imagem,
escrevia o roteiro inteiro (múltiplas chamadas ao Ollama - minutos), só
ENTÃO descobria que não tinha imagem o bastante, e tentava de novo do zero
com outro tema igualmente às cegas - o padrão exato que empilhou gerações
simultâneas e causou a colisão de arquivo temporário (WinError 32) na mesma
madrugada. _pick_topic_with_images/_topic_has_images fazem essa checagem
ANTES de pagar o custo de escrever o roteiro."""

from pipeline import script_gen


def test_topic_has_images_true_when_search_finds_enough(monkeypatch):
    monkeypatch.setattr(
        script_gen, "_search_relevant_images",
        lambda queries, ref, target_count=6, seen_paths=None: ["a", "b", "c"],
    )
    assert script_gen._topic_has_images("black hole") is True


def test_topic_has_images_false_when_search_finds_too_few(monkeypatch):
    monkeypatch.setattr(
        script_gen, "_search_relevant_images",
        lambda queries, ref, target_count=6, seen_paths=None: ["a"],
    )
    assert script_gen._topic_has_images("some vague topic") is False


def test_topic_has_images_fails_open_on_exception(monkeypatch):
    def boom(*a, **kw):
        raise RuntimeError("rede fora do ar")
    monkeypatch.setattr(script_gen, "_search_relevant_images", boom)
    # Falha na checagem não pode travar a escolha de tema - assume que
    # passou e deixa o MIN_REAL_IMAGES no fim do roteiro como rede de
    # segurança final.
    assert script_gen._topic_has_images("qualquer coisa") is True


def test_pick_topic_with_images_skips_bad_candidates(monkeypatch):
    good_queries = {"black hole"}

    def fake_search(queries, ref, target_count=6, seen_paths=None):
        return ["a", "b", "c"] if queries[0] in good_queries else []

    monkeypatch.setattr(script_gen, "_search_relevant_images", fake_search)

    candidates = [("tema ruim 1", "vague phrase one"), ("tema bom", "black hole"), ("tema ruim 2", "vague phrase two")]
    # Roda várias vezes - a ordem é embaralhada, o resultado tem que ser
    # sempre o único candidato bom, não um dos ruins por sorte de ordem.
    for _ in range(10):
        picked = script_gen._pick_topic_with_images(candidates)
        assert picked == ("tema bom", "black hole")


def test_pick_topic_with_images_returns_none_when_all_fail(monkeypatch):
    monkeypatch.setattr(
        script_gen, "_search_relevant_images",
        lambda queries, ref, target_count=6, seen_paths=None: [],
    )
    candidates = [("a", "x"), ("b", "y")]
    assert script_gen._pick_topic_with_images(candidates) is None


def test_choose_fallback_topic_prefers_candidate_with_images(monkeypatch):
    channel_row = {"id": 1, "name": "Canal Teste"}

    class FakeChannel(dict):
        def keys(self):
            return super().keys()

    channel = FakeChannel(channel_row)

    monkeypatch.setattr(script_gen.channels, "topics_for", lambda ch: [
        ("tema sem imagem", "vague narrative phrase"),
        ("tema com imagem", "black hole"),
    ])
    monkeypatch.setattr(script_gen.catalog, "recent_topics", lambda channel_id, lookback=10: [])
    monkeypatch.setattr(
        script_gen, "_search_relevant_images",
        lambda queries, ref, target_count=6, seen_paths=None: (
            ["a", "b", "c"] if queries[0] == "black hole" else []
        ),
    )

    for _ in range(10):
        label, query = script_gen._choose_fallback_topic(channel)
        assert (label, query) == ("tema com imagem", "black hole")
