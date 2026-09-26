"""Heurísticas locais (sem LLM, sem API paga) pra sinalizar comentários
prováveis de serem spam - dor real documentada em 2026 (bots usando
substituição de caracteres Unicode "confusáveis" pra escapar de filtro de
palavra-chave, e texto gerado por IA que passa por humano à primeira
vista). Isso só SUGERE - a decisão de ocultar/rejeitar continua sendo um
clique explícito do dono na interface (ver settings_ui.channel_comments),
nunca automático.
"""

import re
import unicodedata

_SPAM_KEYWORDS = (
    "ganhe dinheiro", "renda extra", "trabalhe de casa", "clique aqui",
    "inscreva-se no meu canal", "se inscreva no meu canal", "confira meu canal",
    "make money", "work from home", "click here", "check out my channel",
    "subscribe to my channel", "dm me", "chame no whatsapp", "chama no whats",
    "crypto", "investimento garantido", "ganhos garantidos",
)

_URL_PATTERN = re.compile(r"https?://|www\.|\.(com|net|org|io|me)\b", re.IGNORECASE)

# Emojis em excesso é sinal comum de spam/bot (comentário "genuíno" raramente
# tem mais de 3-4 emojis seguidos).
_EMOJI_PATTERN = re.compile(
    "[\U0001F300-\U0001FAFF\U00002700-\U000027BF\U0001F900-\U0001F9FF]"
)


def _has_confusable_unicode(text: str) -> bool:
    """Detecta mistura de letras Latinas com letras de OUTRO alfabeto que
    visualmente se parecem (ex.: "а" cirílico no lugar de "a" latino) -
    técnica conhecida de bot pra escapar de filtro de palavra-chave exato.
    Heurística simples: mistura de blocos Unicode "Latin" e "Cyrillic" (ou
    outro alfabeto) na mesma palavra é suspeita; texto 100% num alfabeto só
    (incluindo só Cyrillic, por exemplo) não é, por si só, spam."""
    scripts_seen = set()
    for ch in text:
        if ch.isalpha():
            try:
                name = unicodedata.name(ch)
            except ValueError:
                continue
            if name.startswith("LATIN"):
                scripts_seen.add("latin")
            elif name.startswith("CYRILLIC"):
                scripts_seen.add("cyrillic")
            elif name.startswith("GREEK"):
                scripts_seen.add("greek")
    return len(scripts_seen) > 1


def spam_score(text: str, author: str = "") -> tuple[int, list[str]]:
    """Score 0-100 (quanto maior, mais suspeito) + lista de motivos - nunca
    decide sozinho, só ordena/sinaliza pra revisão humana priorizar."""
    reasons = []
    score = 0
    lowered = text.lower()

    if _URL_PATTERN.search(text):
        score += 30
        reasons.append("contém link")

    matched_keywords = [kw for kw in _SPAM_KEYWORDS if kw in lowered]
    if matched_keywords:
        score += 35
        reasons.append(f"frase suspeita: \"{matched_keywords[0]}\"")

    emoji_count = len(_EMOJI_PATTERN.findall(text))
    if emoji_count >= 5:
        score += 15
        reasons.append(f"{emoji_count} emojis")

    if _has_confusable_unicode(text):
        score += 25
        reasons.append("mistura de alfabetos (caracteres visualmente parecidos)")

    if len(text.strip()) < 8 and (_URL_PATTERN.search(text) or matched_keywords):
        score += 10
        reasons.append("mensagem curta demais pra ser genuína")

    return min(score, 100), reasons


def flag_duplicates(comments: list[dict]) -> set[str]:
    """Ids de comentários cujo TEXTO é idêntico ao de outro comentário do
    MESMO autor no mesmo lote - bot postando a mesma mensagem repetida em
    vídeos diferentes é um padrão real e objetivo (não precisa de LLM pra
    detectar)."""
    seen: dict[tuple[str, str], list[str]] = {}
    for c in comments:
        key = (c.get("author", ""), c["text"].strip().lower())
        seen.setdefault(key, []).append(c["id"])

    duplicate_ids = set()
    for (author, text), ids in seen.items():
        if author and len(ids) > 1:
            duplicate_ids.update(ids)
    return duplicate_ids
