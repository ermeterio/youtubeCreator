"""Regressão do bug real relatado pelo dono (08/10/2026): termo de busca de
imagem gerado pelo LLM (ex.: "Light-Year Expeditions") colidindo com nome de
arquivo da NASA sem relação nenhuma com o tema (fotos de tripulação "Expedition
Six"/"Expedition 11" da Estação Espacial) - ver script_gen._sanitize_image_query
e o comentário em _IMAGE_QUERY_COLLISION_WORDS."""

from pipeline import script_gen


def test_strips_collision_word_keeping_the_rest():
    assert script_gen._sanitize_image_query("Light-Year Expeditions") == "Light-Year"


def test_strips_collision_word_from_middle():
    assert script_gen._sanitize_image_query("ISS crew mission") == "ISS"


def test_query_entirely_collision_words_returns_none():
    assert script_gen._sanitize_image_query("Mission Expedition Adventure") is None


def test_clean_query_passes_through_unchanged():
    assert script_gen._sanitize_image_query("black hole") == "black hole"
    assert script_gen._sanitize_image_query("Voyager spacecraft") == "Voyager spacecraft"


def test_voyager_proper_noun_not_treated_as_collision_word():
    # "Voyager" (a sonda) não pode ser confundido com "voyage" genérico -
    # é exatamente o tipo de busca específica e boa que não deve ser filtrada.
    assert script_gen._sanitize_image_query("Voyager") == "Voyager"


def test_search_relevant_images_sanitizes_internally(monkeypatch):
    """_search_relevant_images é o único ponto por onde toda busca de
    imagem passa (geração do dia, pedido sob demanda, sugestão de tema) -
    confirma que a sanitização acontece DENTRO dela, não só no chamador,
    senão suggest_topics() (que chama direto) fica desprotegido de novo."""
    seen_queries = []

    def fake_fetch(query, count=6):
        seen_queries.append(query)
        return []

    monkeypatch.setattr(script_gen.visual_source, "fetch_nasa_images_for_topic", fake_fetch)
    monkeypatch.setattr(script_gen.visual_source, "fetch_esa_hubble_images_for_topic", fake_fetch)
    monkeypatch.setattr(script_gen.visual_source, "fetch_eso_images_for_topic", fake_fetch)
    monkeypatch.setattr(script_gen.visual_source, "fetch_noirlab_images_for_topic", fake_fetch)

    script_gen._search_relevant_images(["Light-Year Expeditions"], "Light-Year Expeditions", target_count=4)

    assert all("Expedition" not in q for q in seen_queries)
    assert "Light-Year" in seen_queries


def test_search_relevant_images_drops_all_collision_query(monkeypatch):
    """Se a query inteira for só palavra(s) colidente(s), nenhuma busca
    deve ser disparada - mais seguro não buscar do que buscar errado."""
    calls = []

    def fake_fetch(query, count=6):
        calls.append(query)
        return []

    monkeypatch.setattr(script_gen.visual_source, "fetch_nasa_images_for_topic", fake_fetch)
    monkeypatch.setattr(script_gen.visual_source, "fetch_esa_hubble_images_for_topic", fake_fetch)
    monkeypatch.setattr(script_gen.visual_source, "fetch_eso_images_for_topic", fake_fetch)
    monkeypatch.setattr(script_gen.visual_source, "fetch_noirlab_images_for_topic", fake_fetch)

    result = script_gen._search_relevant_images(["Mission Expedition Adventure"], "Mission Expedition Adventure")

    assert result == []
    assert calls == []
