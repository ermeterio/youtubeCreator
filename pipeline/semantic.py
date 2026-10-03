"""Matching semântico leve pra filtrar imagens irrelevantes que a busca por
palavra-chave (NASA/ESA) às vezes retorna - a causa raiz de um bug real
relatado (roteiro sobre nebulosas recebendo fotos de "spacecraft processing"
porque a busca por texto literal não tem noção de significado, só de
substring/metadado).

Usa `fastembed` (ONNX Runtime, sem PyTorch) em vez de sentence-transformers -
mesma família de modelo, mas dependência bem mais leve (dezenas de MB, não
~2GB+) e sem GPU. Modelo (~70MB) baixado uma vez e cacheado em
data/assets/embedding_model/.

Isso NÃO troca a busca em si (a API da NASA continua sendo busca por
palavra-chave) - é uma camada de verificação DEPOIS da busca, que rejeita
resultados que vieram mas não têm relação semântica real com o que estava
sendo procurado, em vez de aceitar cegamente qualquer coisa que a API
devolveu.
"""

import numpy as np

import config

_model = None
_image_model = None
_clip_text_model = None

# Calibrado empiricamente (ver ROADMAP.md) comparando pares bons/ruins reais:
# pares claramente errados (nebulosa vs foto de sonda sendo montada) ficaram
# em ~0.55-0.60; pares relacionados de verdade ficaram em ~0.65-0.78. 0.60
# é uma linha de corte conservadora - rejeita os casos claramente errados
# sem descartar demais.
#
# USADO SÓ pra max_similarity/pairwise_high_similarity_fraction (comparação
# TEXTO-vs-TEXTO em português, ex. título novo vs títulos recentes do canal -
# aí não tem problema de idioma, os dois lados são sempre português). NÃO
# USAR mais pra relevância de IMAGEM - ver filter_relevant_by_image abaixo.
MIN_RELEVANCE_SCORE = 0.60


def _get_model():
    global _model
    if _model is None:
        from fastembed import TextEmbedding
        cache_dir = str(config.ASSETS_DIR / "embedding_model")
        _model = TextEmbedding(model_name="BAAI/bge-small-en-v1.5", cache_dir=cache_dir)
    return _model


# Verificação de relevância de imagem baseada no CONTEÚDO REAL da foto (CLIP,
# via fastembed/ONNX - mesma filosofia leve/sem GPU do resto do módulo), não
# só no título/metadado que a fonte (NASA/ESA/ESO/NOIRLab) publicou junto.
#
# Por que isso existe: a verificação antiga (`filter_relevant`, baseada só no
# TÍTULO da imagem) deixou passar fotos institucionais completamente sem
# relação com o vídeo - ex. "Meeting of Brazil Participation Group" e
# "Autoridades en premiación" batendo com termos de busca genéricos o
# bastante, ou com o modelo de texto (só-inglês) produzindo pontuação
# essencialmente aleatória contra referência em português. Um filtro que só
# lê texto nunca pode saber se a FOTO é mesmo de astronomia - só se a
# LEGENDA parece ser. CLIP resolve isso de verdade: embeda os PIXELS da
# imagem e o texto da busca no mesmo espaço vetorial, então a comparação é
# contra o conteúdo visual real, não contra metadado que pode estar genérico,
# impreciso ou em outro idioma.
#
# Threshold calibrado empiricamente (30/09-03/10/2026) com fotos reais que já
# causaram o problema: as 3 fotos de reunião/premiação do caso relatado
# ficaram entre 0.034 e 0.224; imagens reais de astronomia (Hubble/ESO,
# temas variados) ficaram entre 0.211 e 0.30. 0.20 fica na folga entre os
# dois grupos, com margem pros dois lados.
MIN_VISUAL_RELEVANCE_SCORE = 0.20


def _get_image_model():
    global _image_model
    if _image_model is None:
        from fastembed import ImageEmbedding
        cache_dir = str(config.ASSETS_DIR / "clip_model")
        _image_model = ImageEmbedding("Qdrant/clip-ViT-B-32-vision", cache_dir=cache_dir)
    return _image_model


def _get_clip_text_model():
    global _clip_text_model
    if _clip_text_model is None:
        from fastembed import TextEmbedding
        cache_dir = str(config.ASSETS_DIR / "clip_model")
        _clip_text_model = TextEmbedding("Qdrant/clip-ViT-B-32-text", cache_dir=cache_dir)
    return _clip_text_model


def filter_relevant_by_image(query_en: str, candidates: list, path_fn=lambda c: c.local_path,
                              min_score: float = MIN_VISUAL_RELEVANCE_SCORE) -> list:
    """Filtra `candidates` comparando o CONTEÚDO REAL de cada imagem (via
    CLIP) contra `query_en` - SEMPRE em inglês (CLIP é majoritariamente
    treinado em inglês; texto em português produz embedding ruim). Falha
    aberta (retorna candidates sem filtrar) se o modelo não carregar - a
    checagem é um reforço de qualidade, nunca pode travar a geração do vídeo
    do dia por falta de internet pra baixar o modelo na 1ª vez, por exemplo."""
    if not candidates:
        return []
    try:
        img_model = _get_image_model()
        txt_model = _get_clip_text_model()
        paths = [str(path_fn(c)) for c in candidates]
        img_vectors = list(img_model.embed(paths))
        query_vec = list(txt_model.embed([query_en]))[0]
    except Exception:
        return candidates

    kept = []
    for candidate, vec in zip(candidates, img_vectors):
        if _cosine(query_vec, vec) >= min_score:
            kept.append(candidate)
    return kept


def average_visual_relevance(query_en: str, candidates: list, path_fn=lambda c: c.local_path) -> float | None:
    """Equivalente a `average_relevance`, mas comparando o conteúdo real da
    imagem (CLIP) em vez do título - usado pro sub-score de "relevância de
    imagem" no resumo de qualidade (ver script_gen.compute_quality_score)."""
    if not candidates:
        return None
    try:
        img_model = _get_image_model()
        txt_model = _get_clip_text_model()
        paths = [str(path_fn(c)) for c in candidates]
        img_vectors = list(img_model.embed(paths))
        query_vec = list(txt_model.embed([query_en]))[0]
    except Exception:
        return None

    scores = [_cosine(query_vec, vec) for vec in img_vectors]
    return sum(scores) / len(scores)


def _cosine(a, b) -> float:
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-9))


def average_relevance(query: str, candidates: list, text_fn=lambda c: c.title) -> float | None:
    """Score médio (0-1) de quão relacionados `candidates` estão de `query` -
    usado pro score de qualidade agregado do vídeo (ver script_gen.
    compute_quality_score), não pra filtrar/rejeitar nada. Retorna None se
    não houver candidatos ou o modelo não carregar."""
    if not candidates:
        return None
    try:
        model = _get_model()
        texts = [query] + [text_fn(c) for c in candidates]
        vectors = list(model.embed(texts))
    except Exception:
        return None

    query_vec = vectors[0]
    scores = [_cosine(query_vec, vec) for vec in vectors[1:]]
    return sum(scores) / len(scores)


# Calibrado empiricamente comparando título/gancho reais do canal: paráfrase
# do mesmo tema (repetição de verdade) ficou em ~0.92; títulos de temas
# genuinamente diferentes do mesmo canal ficaram em ~0.64-0.75. 0.85 separa
# bem os dois casos sem marcar vídeos só por serem do mesmo nicho.
REPETITION_THRESHOLD = 0.85


def max_similarity(text: str, recent_texts: list[str]) -> float | None:
    """Maior similaridade entre `text` e qualquer item de `recent_texts` -
    usado pra detectar se um vídeo novo está repetindo o título/gancho de um
    vídeo recente demais do mesmo canal (o YouTube penaliza reciclagem de
    hook/formato - ver ROADMAP.md). Retorna None se não houver textos
    recentes pra comparar ou o modelo não carregar."""
    if not recent_texts:
        return None
    try:
        model = _get_model()
        vectors = list(model.embed([text] + recent_texts))
    except Exception:
        return None

    query_vec = vectors[0]
    return max(_cosine(query_vec, vec) for vec in vectors[1:])


def pairwise_high_similarity_fraction(texts: list[str], threshold: float = REPETITION_THRESHOLD) -> dict | None:
    """Fração de itens de `texts` que têm ALGUM outro item na mesma lista
    acima de `threshold` de similaridade - sinal de "sameness" estrutural do
    conjunto inteiro, não só do item mais recente contra o histórico (ver
    max_similarity). Usado pro "Channel Sameness Audit" (ROADMAP.md): a
    política do YouTube de "inauthentic content" (2026) pune no nível do
    CANAL quando uma fração alta do watch time vem de vídeos com pouca
    variação estrutural entre si, não só título repetido individualmente.
    Retorna None se a amostra for pequena demais (< 8) pra não gerar ruído."""
    if len(texts) < 8:
        return None
    try:
        model = _get_model()
        vectors = list(model.embed(texts))
    except Exception:
        return None

    n = len(vectors)
    flagged_pairs = []
    flagged_count = 0
    for i in range(n):
        best_score, best_j = 0.0, None
        for j in range(n):
            if i == j:
                continue
            score = _cosine(vectors[i], vectors[j])
            if score > best_score:
                best_score, best_j = score, j
        if best_score >= threshold:
            flagged_count += 1
            flagged_pairs.append((i, best_j, best_score))

    return {
        "sample_size": n,
        "flagged_count": flagged_count,
        "fraction": flagged_count / n,
        "flagged_pairs": flagged_pairs,
    }


def filter_relevant(query: str, candidates: list, text_fn=lambda c: c.title,
                     min_score: float = MIN_RELEVANCE_SCORE) -> list:
    """Filtra `candidates` mantendo só os semanticamente relacionados a
    `query` (comparando `query` contra `text_fn(candidate)`, por padrão o
    título/descrição da imagem). Falha aberta (retorna candidates sem
    filtrar) se o modelo não carregar por qualquer motivo - a checagem de
    relevância é um reforço de qualidade, nunca pode travar a geração do
    vídeo do dia."""
    if not candidates:
        return []
    try:
        model = _get_model()
        texts = [query] + [text_fn(c) for c in candidates]
        vectors = list(model.embed(texts))
    except Exception:
        return candidates

    query_vec = vectors[0]
    kept = []
    for candidate, vec in zip(candidates, vectors[1:]):
        if _cosine(query_vec, vec) >= min_score:
            kept.append(candidate)
    return kept
