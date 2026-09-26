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

# Calibrado empiricamente (ver ROADMAP.md) comparando pares bons/ruins reais:
# pares claramente errados (nebulosa vs foto de sonda sendo montada) ficaram
# em ~0.55-0.60; pares relacionados de verdade ficaram em ~0.65-0.78. 0.60
# é uma linha de corte conservadora - rejeita os casos claramente errados
# sem descartar demais.
MIN_RELEVANCE_SCORE = 0.60


def _get_model():
    global _model
    if _model is None:
        from fastembed import TextEmbedding
        cache_dir = str(config.ASSETS_DIR / "embedding_model")
        _model = TextEmbedding(model_name="BAAI/bge-small-en-v1.5", cache_dir=cache_dir)
    return _model


def _cosine(a, b) -> float:
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-9))


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
