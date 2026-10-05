"""Gera o roteiro narrado do dia.

Prioriza a APOD (imagem + explicação factual real da NASA) como base do
roteiro - assim o conteúdo tem uma fonte checável, não é só o LLM
"inventando" fatos de astronomia. Se a APOD do dia não render um bom tema
(ex.: explicação muito técnica/curta) ou a chamada falhar, cai para um tema
da lista rotativa configurada no canal (ver pipeline.channels).

IMPORTANTE: o texto gerado aqui é ponto de partida, não produto final. O
pipeline força uma pausa de revisão humana (ver orchestrator.py) antes do
upload - é isso que caracteriza "decisão editorial humana" exigida pela
política de conteúdo do YouTube, e também sua garantia de que os fatos
citados estão corretos.
"""

import random
import re
import sqlite3

import requests
from PIL import Image

import config
from pipeline import catalog, channels, notify, semantic, visual_source, youtube_analytics

OLLAMA_URL = "http://localhost:11434/api/generate"
OLLAMA_TAGS_URL = "http://localhost:11434/api/tags"
OLLAMA_MODEL = "llama3.1"

# Diacríticos que só aparecem em português (não em inglês) - usado pra
# detectar quando o LLM devolve termo de busca/palavra-chave de imagem em
# português apesar de instruído a responder em inglês (ver build_daily_script).
_PT_DIACRITICS_RE = re.compile(r"[áàãâéêíóôõúçÁÀÃÂÉÊÍÓÔÕÚÇ]")


def ollama_available() -> bool:
    """Checagem rápida (timeout curto) se o Ollama está de pé - usada pra
    logar uma mensagem clara ("Ollama não está rodando") em vez de deixar o
    pipeline cair silenciosamente no fallback fraco de roteiro sem o dono
    entender por quê."""
    try:
        requests.get(OLLAMA_TAGS_URL, timeout=5).raise_for_status()
        return True
    except Exception:
        return False

# Variações de estrutura/ângulo narrativo do gancho inicial - alterna entre
# vídeos pra evitar que o roteiro siga sempre o mesmo molde frase-a-frase
# todo dia (sinal de "conteúdo repetitivo" que a política do YouTube observa
# em canais automatizados; também deixa o canal menos previsível/monótono
# pra quem assiste vários vídeos seguidos).
PROMPT_ANGLES = [
    "Abra com uma PERGUNTA direta e curiosa pro espectador.",
    "Abra com uma AFIRMAÇÃO surpreendente ou contraintuitiva, sem ser pergunta.",
    "Abra com uma COMPARAÇÃO de escala (tamanho, tempo ou distância) que seja chocante.",
    "Abra com um cenário hipotético do tipo 'imagine se...' ou 'e se...'.",
]

PROMPT_TEMPLATE = """Você é roteirista de um canal de divulgação científica sobre {niche}.
Escreva um roteiro narrado ORIGINAL, EM {language_name} (todo o roteiro e o título, nesse idioma -
não em português, a menos que {language_name} seja português), de 60 a 90 segundos de fala,
sobre o tema: "{topic}".
Baseie-se SOMENTE nestes fatos reais como referência - não invente números,
datas, distâncias ou nomes que não estejam no texto abaixo; reescreva com
suas próprias palavras, em tom acessível e curioso, para um público geral:
---
{facts}
---
Estrutura: {angle} Depois, desenvolva o tema, e feche convidando o espectador
a pensar mais sobre o assunto.
{feedback_section}
Além do roteiro, liste de 4 a 6 termos de busca EM INGLÊS (independente do
idioma do roteiro - são pra buscar imagem, não pra narrar), bem específicos
sobre os elementos visuais concretos citados nos fatos-fonte (ex.: nome do
objeto, tipo de fenômeno, instrumento/telescópio usado, evento) - esses
termos serão usados para buscar imagens reais da NASA/ESA que combinem com
o que está sendo narrado. Não use termos genéricos demais (evite só "space"
ou "galaxy" sozinhos) - prefira específicos, como apareceriam nos fatos-fonte.

Responda EXATAMENTE neste formato (as palavras TITULO/PALAVRAS_CHAVE_IMAGEM/ROTEIRO ficam em
português mesmo, são só marcadores - o CONTEÚDO depois de cada uma é que vai em {language_name}),
sem nenhum texto antes ou depois:
TITULO: <título curto e chamativo do vídeo, em {language_name}>
PALAVRAS_CHAVE_IMAGEM: <termo1, termo2, termo3, termo4>
ROTEIRO:
<o roteiro completo, só o texto que será narrado, em {language_name}>
"""

FEEDBACK_SECTION_TEMPLATE = """
O dono do canal já revisou vídeos anteriores. Use isso como guia de estilo:
{liked_block}{disliked_block}"""

FACT_CHECK_TEMPLATE = """Você é um verificador de fatos rigoroso. Abaixo estão os FATOS-FONTE (a
única informação confiável disponível) e um ROTEIRO escrito a partir deles.

FATOS-FONTE:
---
{facts}
---

ROTEIRO:
---
{script}
---

Liste TODA afirmação numérica ou factual específica do roteiro (números,
datas, distâncias, nomes próprios, superlativos como "o maior"/"o primeiro").
Para cada uma, diga se ela está PRESENTE ou AUSENTE nos fatos-fonte.

Responda EXATAMENTE neste formato, sem texto antes ou depois:
RESULTADO: <OK se todas as afirmações estão presentes nos fatos-fonte, ou
ATENCAO se pelo menos uma afirmação não está rastreável à fonte>
DETALHES: <lista curta das afirmações e se estão presentes ou ausentes>
"""

CLARITY_REVIEW_TEMPLATE = """Você é um espectador leigo, curioso mas SEM formação em {niche} - nunca
estudou o assunto, só assiste vídeos curtos de ciência por curiosidade. Leia o roteiro abaixo como
se fosse a primeira vez que ouve falar disso.

ROTEIRO:
---
{script}
---

Aponte, em até 3 itens curtos, trechos que você (nesse papel de leigo) acharia CONFUSOS (termo
técnico sem explicação, salto lógico, frase longa demais) ou EXCESSIVAMENTE EXPLICADOS (redundante,
pode entediar quem já entendeu no início). Se o roteiro estiver claro o bastante pra um leigo do
início ao fim, diga isso.

Responda EXATAMENTE neste formato, sem texto antes ou depois:
RISCOS: <lista curta de trechos problemáticos com motivo, ou "nenhum - roteiro claro pra leigo" se não houver>
"""


COMMENT_REPLY_TEMPLATE = """Você é quem administra um canal de YouTube automatizado sobre {niche},
respondendo comentários do público de forma simpática, breve e humana (não robótica, não genérica).

COMENTÁRIO DO ESPECTADOR:
---
{comment}
---

Escreva UMA resposta curta (1-3 frases) em {language_name}, num tom acolhedor e específico ao que a
pessoa disse (evite respostas genéricas tipo "obrigado pelo comentário!" sem relação com o conteúdo).
Se for uma pergunta, tente respondê-la com o conhecimento geral que você tem sobre {niche}; se for
elogio, agradeça de forma específica; se for crítica construtiva, reconheça sem ser defensivo.

Responda EXATAMENTE neste formato, sem texto antes ou depois:
RESPOSTA: <a resposta sugerida>
"""


def suggest_comment_reply(comment_text: str, niche: str = "ciência", language_name: str = "português do Brasil") -> str | None:
    """Sugere uma resposta a UM comentário real do canal - sempre revisada e
    editável pelo dono antes de publicar (ver settings_ui rota de
    comentários). Retorna None se o Ollama não responder; nesse caso a
    interface mostra um campo de texto vazio pro dono escrever na mão."""
    prompt = COMMENT_REPLY_TEMPLATE.format(comment=comment_text, niche=niche, language_name=language_name)
    text = _call_ollama(prompt, timeout=60)
    if not text or not _has_marker(text, "RESPOSTA:"):
        return None
    return _split_at_marker(text, "RESPOSTA:")[1].strip()


def clarity_review(script: str, niche: str = "ciência") -> str | None:
    """Segunda passada do LLM local simulando um espectador leigo lendo o
    roteiro antes da revisão humana - sinaliza trechos confusos ou
    redundantes pro revisor não precisar achar isso sozinho. Complementa o
    fact-check (que checa PRECISÃO) com um checador de CLAREZA. Retorna None
    se o Ollama não responder - é um reforço opcional pro revisor, nunca
    bloqueia o pipeline."""
    prompt = CLARITY_REVIEW_TEMPLATE.format(script=script, niche=niche)
    text = _call_ollama(prompt, timeout=90)
    if not text or not _has_marker(text, "RISCOS:"):
        return None
    return _split_at_marker(text, "RISCOS:")[1].strip()


POLISH_TEMPLATE = """Você é um editor de texto especializado em preparar roteiros para narração em voz
alta (texto-para-fala) de um canal de YouTube sobre {niche}. Revise o roteiro abaixo e devolva uma
versão corrigida - sem mudar fatos, números, nomes próprios ou a ordem das ideias - só consertando:
- erros de gramática, concordância verbal/nominal e pontuação
- frases estranhas, longas demais ou com jeito de tradução automática (soam artificiais faladas em
  voz alta)
- palavras repetidas muito perto uma da outra
- termos técnicos usados sem nenhuma explicação que um leigo entenderia

NÃO adicione informação nova, NÃO resuma, NÃO mude o tamanho do roteiro de forma relevante. Se o
roteiro já estiver bom, devolva ele exatamente como está, sem alterar nada.

ROTEIRO ORIGINAL:
---
{script}
---

Responda EXATAMENTE neste formato, sem texto antes ou depois:
ROTEIRO_REVISADO: <roteiro corrigido completo, pronto pra narração>
"""


def polish_script(script: str, niche: str = "ciência") -> str:
    """Passada de revisão de texto feita pelo Llama ANTES do fact-check/
    narração - ao contrário do clarity_review (que só SINALIZA problemas pro
    revisor humano), essa aqui efetivamente corrige gramática, fluência e
    naturalidade do texto pra narração. Guarda-corpo contra resposta
    degenerada do LLM (vazia, ou com tamanho muito diferente do original,
    sinal de que "comeu" ou inventou conteúdo): nesses casos mantém o
    roteiro original sem risco. Se o Ollama não responder, também mantém o
    original - é um reforço opcional, nunca bloqueia o pipeline."""
    prompt = POLISH_TEMPLATE.format(script=script, niche=niche)
    text = _call_ollama(prompt, timeout=90)
    if not text or not _has_marker(text, "ROTEIRO_REVISADO:"):
        return script
    revised = _clean_llm_text(_split_at_marker(text, "ROTEIRO_REVISADO:")[1].strip())
    if not revised or not (0.6 <= len(revised) / max(len(script), 1) <= 1.4):
        return script
    return revised


REVIEW_TEMPLATE = """Você é o roteirista responsável por melhorar os próximos vídeos de um canal
automatizado do YouTube sobre {niche}. O dono do canal revisou um vídeo já publicado/gerado e
deixou uma observação sobre ele.

TÍTULO DO VÍDEO: {title}
ROTEIRO DO VÍDEO:
---
{script}
---

OBSERVAÇÃO DO DONO: "{observation}"

Responda em português, curto e direto (no máximo 6 linhas no total):
1. Confirme, em 1 frase, que entendeu exatamente o que o dono está apontando.
2. Proponha de 1 a 3 ações CONCRETAS e ESPECÍFICAS a aplicar nos PRÓXIMOS vídeos gerados por este
   pipeline para resolver isso (ex.: mudar como as palavras-chave de imagem são extraídas, ajustar
   a estrutura do roteiro, mudar o tom, evitar um tipo de abertura específico). Não sugira nada
   genérico tipo "melhorar a qualidade" - seja específico sobre O QUE muda no processo.

Responda EXATAMENTE neste formato, sem texto antes ou depois:
ENTENDIMENTO: <resumo curto do que foi entendido>
ACOES: <ação 1>; <ação 2>; <ação 3 se houver>
"""


def _image_resolution(asset) -> int:
    """Área em pixels, usada para priorizar imagens de maior qualidade nos
    primeiros segundos do vídeo (onde a retenção é decidida)."""
    try:
        with Image.open(asset.local_path) as img:
            return img.size[0] * img.size[1]
    except Exception:
        return 0


def _clean_llm_text(text: str) -> str:
    return text.strip().strip("*").strip('"').strip()


def _strip_accents(text: str) -> str:
    import unicodedata
    return "".join(c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c))


def _has_marker(text: str, marker: str) -> bool:
    return _strip_accents(marker) in _strip_accents(text)


def _split_at_marker(text: str, marker: str, maxsplit: int = 1) -> list[str]:
    """Como text.split(marker, maxsplit), mas tolera o LLM escrever o
    marcador com acentuação gramaticalmente correta em português (ex.
    "AÇÕES:" em vez de "ACOES:", "SUGESTÕES:" em vez de "SUGESTOES:",
    "TÍTULO:" em vez de "TITULO:") mesmo quando instruído a manter sem
    acento - isso acontece com frequência real o bastante pra quebrar o
    parsing silenciosamente se não for tolerado. Os acentos em português
    substituem 1 caractere por 1 caractere, então a posição encontrada no
    texto sem-acento bate exatamente com a posição no texto original."""
    stripped = _strip_accents(text)
    marker_stripped = _strip_accents(marker)
    parts_positions = []
    start = 0
    count = 0
    while count < maxsplit:
        idx = stripped.find(marker_stripped, start)
        if idx == -1:
            break
        parts_positions.append(idx)
        start = idx + len(marker_stripped)
        count += 1
    if not parts_positions:
        return [text]
    result = []
    prev = 0
    for idx in parts_positions:
        result.append(text[prev:idx])
        prev = idx + len(marker_stripped)
    result.append(text[prev:])
    return result


def _parse_llm_output(text: str) -> dict | None:
    if not _has_marker(text, "TITULO:") or not _has_marker(text, "ROTEIRO:"):
        return None
    title_part = _clean_llm_text(_split_at_marker(_split_at_marker(text, "TITULO:")[1], "ROTEIRO:")[0])
    script_part = _clean_llm_text(_split_at_marker(text, "ROTEIRO:")[1])
    if not title_part or not script_part:
        return None

    image_keywords = []
    if _has_marker(title_part, "PALAVRAS_CHAVE_IMAGEM:"):
        title_part, keywords_raw = _split_at_marker(title_part, "PALAVRAS_CHAVE_IMAGEM:")
        title_part = _clean_llm_text(title_part)
        image_keywords = [k.strip() for k in keywords_raw.split(",") if k.strip()]

    return {"title": title_part, "script": script_part, "image_keywords": image_keywords}


# Textos do roteiro de fallback por idioma - usado só quando o LLM local não
# respondeu, então não tenta traduzir os fatos-fonte (isso exigiria o próprio
# LLM), só monta a moldura (título/abertura/fechamento) no idioma certo do
# canal, pra pelo menos não sair um vídeo em português num canal em inglês.
_FALLBACK_TEXT = {
    "pt-BR": {
        "title": "O que a ciência já descobriu sobre {topic}",
        "intro": "Você já parou pra pensar sobre {topic}? Aqui está um fato real da NASA sobre "
                 "o assunto (em inglês, reescreva isso ao revisar): \"{facts}\"",
        "outro": "A ciência continua avançando pra entender cada vez mais sobre {topic}.",
    },
    "en-US": {
        "title": "What science already knows about {topic}",
        "intro": "Have you ever stopped to think about {topic}? Here's a real fact from NASA "
                 "about it: \"{facts}\"",
        "outro": "Science keeps advancing to understand more and more about {topic}.",
    },
    "es-ES": {
        "title": "Lo que la ciencia ya sabe sobre {topic}",
        "intro": "¿Alguna vez te has parado a pensar en {topic}? Aquí tienes un dato real de la "
                 "NASA al respecto: \"{facts}\"",
        "outro": "La ciencia sigue avanzando para entender cada vez más sobre {topic}.",
    },
}


def _fallback_script(topic: str, facts: str, language_code: str = "pt-BR") -> dict:
    """Fallback usado quando o LLM local não está disponível. Os `facts` da
    APOD vêm em inglês e podem ser longos - aqui só truncamos por segurança
    de duração de vídeo. Isso é DELIBERADAMENTE um roteiro fraco (fatos em
    inglês, sem reescrita): serve para o pipeline não travar, mas o vídeo
    gerado a partir dele deve ser tratado como rascunho, não como algo
    publicável sem revisão/reescrita manual do roteiro.
    """
    text = _FALLBACK_TEXT.get(language_code, _FALLBACK_TEXT["pt-BR"])
    trimmed_facts = facts[:280].rsplit(".", 1)[0] + "." if len(facts) > 280 else facts
    title = text["title"].format(topic=topic)
    script = (
        text["intro"].format(topic=topic, facts=trimmed_facts)
        + "\n\n" + text["outro"].format(topic=topic)
    )
    return {"title": title, "script": script, "image_keywords": [topic]}


def _call_ollama(prompt: str, timeout: int = 240) -> str | None:
    try:
        response = requests.post(
            OLLAMA_URL,
            json={"model": OLLAMA_MODEL, "prompt": prompt, "stream": False},
            timeout=timeout,
        )
        response.raise_for_status()
        return response.json()["response"]
    except Exception:
        return None


def _feedback_section(channel_id: int, limit: int = 3) -> str:
    """Monta um bloco de few-shot a partir dos vídeos que o dono já avaliou
    (👍/👎 na interface de revisão) - é como o LLM local "aprende" com o
    tempo sem precisar de fine-tuning: cada roteiro novo já nasce vendo
    exemplos reais do que agradou e notas do que evitar."""
    liked = catalog.feedback_examples(channel_id, "liked", limit)
    disliked = catalog.feedback_examples(channel_id, "disliked", limit)
    seo_block = _seo_performance_section(channel_id)
    if not liked and not disliked:
        return seo_block

    liked_block = ""
    if liked:
        examples = "\n".join(f'- "{t["title"]}": {t["script"][:220]}...' for t in liked)
        liked_block = f"\nRoteiros que o dono APROVOU no passado (siga esse estilo/tom):\n{examples}\n"

    disliked_block = ""
    notes = []
    for t in disliked:
        if t["feedback_action"]:
            notes.append(t["feedback_action"])
        elif t["feedback_notes"]:
            notes.append(t["feedback_notes"])
    if notes:
        joined_notes = "\n".join(f"- {n}" for n in notes)
        disliked_block = f"\nO dono REJEITOU roteiros anteriores pelos seguintes motivos - EVITE repetir isso:\n{joined_notes}\n"

    return FEEDBACK_SECTION_TEMPLATE.format(liked_block=liked_block, disliked_block=disliked_block) + seo_block


def _seo_performance_section(channel_id: int, limit: int = 3, min_sample: int = 5) -> str:
    """Fecha o loop entre desempenho real no YouTube (retenção medida via
    Analytics) e a geração de título/gancho - sem isso, o canal repete os
    mesmos padrões de título pra sempre, mesmo que uns performem muito melhor
    que outros. Só entra em ação depois que o canal já tem `min_sample`
    vídeos com métrica real (amostra pequena demais vira ruído, não sinal).
    Falha silenciosa (retorna "") se o canal ainda não está autorizado, sem
    conexão, ou a API não responder - isso é só um reforço opcional do
    prompt, nunca pode travar a geração do vídeo do dia."""
    try:
        channel = channels.get_channel(channel_id)
        secret_path = channels.client_secret_path(channel["slug"])
        token_path = channels.token_path(channel["slug"])
        if not token_path.exists():
            return ""

        per_video = youtube_analytics.video_metrics(secret_path, token_path, days=90, max_results=50)
        if len(per_video) < min_sample:
            return ""

        local_by_youtube_id = {}
        for t in catalog.list_tracks(channel_id=channel_id, limit=200):
            if t["youtube_video_id"]:
                local_by_youtube_id[t["youtube_video_id"]] = (t["title"], False)
            if t["youtube_short_video_id"]:
                local_by_youtube_id[t["youtube_short_video_id"]] = (t["title"], True)

        scored = []
        shorts_below_cutoff = []
        for video_id, metrics in per_video.items():
            entry = local_by_youtube_id.get(video_id)
            pct = metrics.get("averageViewPercentage")
            if not entry or pct is None:
                continue
            title, is_short = entry
            scored.append((title, float(pct)))
            # Shorts abaixo de ~70% de retenção nos primeiros minutos tendem a
            # perder a janela de distribuição prioritária do YouTube (achado
            # de pesquisa de mercado 2026, ver ROADMAP.md) - sinal mais
            # acionável pro LLM que só "retenção baixa" genérico.
            if is_short and float(pct) < 70:
                shorts_below_cutoff.append((title, float(pct)))
        if len(scored) < min_sample:
            return ""

        scored.sort(key=lambda pair: pair[1], reverse=True)
        best = scored[:limit]
        worst = scored[-limit:] if len(scored) > limit else []

        best_block = "\n".join(f'- "{t}" ({pct:.0f}% de retenção média)' for t, pct in best)
        section = (
            f"\nDesempenho real medido no YouTube (retenção média dos últimos vídeos) - use "
            f"como sinal de que TIPO de título/gancho prende mais atenção:\n"
            f"Títulos com MELHOR retenção (título/abertura nesse estilo tendem a funcionar):\n{best_block}\n"
        )
        if worst:
            worst_block = "\n".join(f'- "{t}" ({pct:.0f}% de retenção média)' for t, pct in worst)
            section += f"Títulos com retenção mais BAIXA (evite repetir esse padrão de título/abertura):\n{worst_block}\n"
        if shorts_below_cutoff:
            cutoff_block = "\n".join(f'- "{t}" ({pct:.0f}%)' for t, pct in shorts_below_cutoff[:limit])
            section += (
                f"ATENÇÃO - Shorts abaixo de 70% de retenção (o YouTube reduz a distribuição de Shorts "
                f"que não seguram atenção nos primeiros segundos): capriche ESPECIALMENTE no gancho "
                f"inicial pra evitar repetir esse padrão:\n{cutoff_block}\n"
            )
        return section
    except Exception:
        return ""


def consult_feedback(title: str, script: str, observation: str, niche: str = "ciência") -> dict:
    """Chama o LLM local imediatamente com a observação que o dono deixou
    sobre um vídeo específico, pedindo confirmação de entendimento + ações
    concretas pros próximos roteiros. Usado pela interface de revisão quando
    o dono clica em "Enviar observação" - dá um retorno na hora, em vez de só
    guardar o texto silenciosamente."""
    prompt = REVIEW_TEMPLATE.format(niche=niche, title=title, script=script, observation=observation)
    text = _call_ollama(prompt, timeout=120)
    if not text or not _has_marker(text, "ENTENDIMENTO:"):
        return {
            "understanding": None,
            "actions": None,
            "error": "O Llama não respondeu (confira se o Ollama está rodando) - a observação foi salva mesmo assim.",
        }

    after_entendimento = _split_at_marker(text, "ENTENDIMENTO:")[1]
    if _has_marker(after_entendimento, "ACOES:"):
        understanding, actions = _split_at_marker(after_entendimento, "ACOES:")
        understanding, actions = understanding.strip(), actions.strip()
    else:
        understanding, actions = after_entendimento.strip(), ""
    return {"understanding": understanding, "actions": actions, "error": None}


CHANNEL_KIT_TEMPLATE = """Você é consultor de canais de YouTube automatizados. Alguém quer criar um
canal novo sobre o nicho: "{niche}".

Gere um kit inicial pra esse canal, em {language_name}:
1. De 8 a 10 temas rotativos específicos desse nicho (não genéricos demais) - cada um com um rótulo
   curto e chamativo NO IDIOMA {language_name}, e um termo de busca em INGLÊS pra achar imagens
   relacionadas (mesmo que o roteiro seja em outro idioma, a busca de imagem é sempre em inglês).
2. Dois nomes de "série"/selo curtos e chamativos pra esse canal, em {language_name}: um pra quando o
   vídeo tem uma fonte factual real do dia (ex.: "Direto da Fonte"), outro pra quando é um tema
   rotativo sem fonte do dia (ex.: "Round-up Rápido") - adapte os NOMES ao nicho específico, não
   copie esses exemplos literalmente.

Responda EXATAMENTE neste formato, sem texto antes ou depois:
TEMAS:
<rótulo 1> | <termo de busca em inglês 1>
<rótulo 2> | <termo de busca em inglês 2>
(... até 8-10 linhas)
SERIE_PRIMARIA: <nome da série pra vídeos com fonte factual do dia>
SERIE_FALLBACK: <nome da série pra vídeos de tema rotativo>
"""


def _clean_item(value: str) -> str:
    # remove numeração de lista ("1. ", "- ") e aspas/traços que o LLM às
    # vezes inclui em cada item, mesmo sendo instruído a não fazer isso
    value = value.strip()
    value = re.sub(r"^[\d]+[.)]\s*", "", value)
    return value.strip(" -\"'“”‘’")


def generate_channel_kit(niche: str, language_code: str = "pt-BR") -> dict | None:
    """Gera um kit inicial (temas rotativos + nomes de série) pra um canal
    novo a partir só da descrição do nicho - poupa o trabalho de escrever
    8-10 linhas de tema na mão toda vez que um canal novo é criado. Retorna
    None se o Ollama não responder (quem chama cai pros defaults genéricos)."""
    language = config.LANGUAGES.get(language_code, config.LANGUAGES[config.DEFAULT_LANGUAGE])
    prompt = CHANNEL_KIT_TEMPLATE.format(niche=niche, language_name=language["llm_language_name"])
    text = _call_ollama(prompt, timeout=120)
    if not text or not _has_marker(text, "TEMAS:"):
        return None

    topics_block = _split_at_marker(text, "TEMAS:")[1]
    if _has_marker(topics_block, "SERIE_PRIMARIA:"):
        topics_block = _split_at_marker(topics_block, "SERIE_PRIMARIA:")[0]
    topics = []
    for line in topics_block.strip().splitlines():
        line = line.strip()
        if "|" not in line:
            continue
        label, query = line.split("|", 1)
        label, query = _clean_item(label), _clean_item(query)
        if label and query:
            topics.append((label, query))

    series_primary = None
    if _has_marker(text, "SERIE_PRIMARIA:"):
        series_primary = _clean_item(_split_at_marker(text, "SERIE_PRIMARIA:")[1].split("\n", 1)[0])
    series_fallback = None
    if _has_marker(text, "SERIE_FALLBACK:"):
        series_fallback = _split_at_marker(text, "SERIE_FALLBACK:")[1].split("\n", 1)[0].strip()

    if not topics:
        return None

    return {
        "topics": topics,
        "series_primary": series_primary or language["default_series_primary"],
        "series_fallback": series_fallback or language["default_series_fallback"],
    }


SUGGEST_TOPICS_TEMPLATE = """Você é o roteirista/curador de conteúdo de um canal de YouTube automatizado
sobre "{niche}". O dono quer ideias novas de vídeo pra pedir sob demanda (fora do agendamento
automático diário).

TEMAS QUE O CANAL JÁ USA NA ROTAÇÃO PADRÃO:
{existing_topics}

TEMAS JÁ NARRADOS RECENTEMENTE (evite repetir estes, mesmo que reformulados):
{recent_topics}
{comments_section}
Sugira {count} ideias de vídeo NOVAS, em {language_name}, que façam sentido pra esse canal.
Pode incluir variações mais específicas dos temas que o canal já cobre, MAS também pode sugerir
assuntos adjacentes/relacionados que ainda não estão na lista - contanto que fiquem claramente
alinhados com a proposta do canal ("{niche}"). Não repita os temas recentes listados acima. Se
houver perguntas/pedidos reais do público listados acima, priorize temas que respondam a eles.

Responda EXATAMENTE neste formato, sem texto antes ou depois:
SUGESTOES:
<rótulo do tema 1, em {language_name}> | <termo de busca em inglês 1>
<rótulo do tema 2, em {language_name}> | <termo de busca em inglês 2>
(... até {count} linhas)
"""


def _recent_comments_section(channel: sqlite3.Row, limit: int = 25) -> str:
    """Puxa comentários reais recentes do canal no YouTube (quando já
    autorizado) como sinal de pauta - o que o público está de fato
    perguntando/pedindo, em vez de só o LLM inventando tema no vácuo. Falha
    silenciosa (string vazia) se o canal não estiver conectado ou a API
    negar - é só um reforço opcional do prompt de sugestão de temas."""
    try:
        secret_path = channels.client_secret_path(channel["slug"])
        token_path = channels.token_path(channel["slug"])
        if not token_path.exists():
            return ""
        from pipeline import youtube_upload
        comments = youtube_upload.list_recent_comments(secret_path, token_path, max_results=limit)
        if not comments:
            return ""
        sample = "\n".join(f"- {c['text'][:180]}" for c in comments[:limit])
        return f"\nCOMENTÁRIOS/PERGUNTAS REAIS RECENTES DO PÚBLICO NO CANAL:\n{sample}\n"
    except Exception:
        return ""


def suggest_topics(channel: sqlite3.Row, count: int = 8) -> list[tuple[str, str]]:
    """Sugere temas de vídeo novos, alinhados ao nicho do canal - pode
    reformular/aprofundar os temas já configurados OU propor assuntos
    adjacentes que ainda não estão na lista, desde que façam sentido pro
    canal. Usado pela interface pra dar ideias antes de um pedido de vídeo
    sob demanda. Retorna lista vazia se o Ollama não responder."""
    niche = channel["niche"] or "conteúdo geral"
    language = channels.language_for(channel)
    existing = channels.topics_for(channel)
    recent = catalog.recent_topics(channel["id"], lookback=10)

    prompt = SUGGEST_TOPICS_TEMPLATE.format(
        niche=niche,
        existing_topics="\n".join(f"- {label}" for label, _ in existing) or "(nenhum cadastrado ainda)",
        recent_topics="\n".join(f"- {t}" for t in recent) or "(nenhum vídeo gerado ainda)",
        comments_section=_recent_comments_section(channel),
        count=count,
        language_name=language["llm_language_name"],
    )
    text = _call_ollama(prompt, timeout=120)
    if not text or not _has_marker(text, "SUGESTOES:"):
        return []

    block = _split_at_marker(text, "SUGESTOES:")[1]
    raw_suggestions = []
    for line in block.strip().splitlines():
        line = line.strip()
        if "|" not in line:
            continue
        label, query = line.split("|", 1)
        label, query = _clean_item(label), _clean_item(query)
        if label and query:
            raw_suggestions.append((label, query))

    # Regra do dono: tema sugerido só entra na lista se achar imagem REAL
    # correlata ao assunto (mesma busca de 4 fontes + verificação visual CLIP
    # usada na geração do vídeo em si) - senão é descartado aqui, antes de
    # chegar a ser oferecido. Evita convidar o dono a pedir um vídeo sobre um
    # tema bonito no papel mas sem nenhuma imagem real pra ilustrar (caso
    # real: "Mistérios das Galáxias Desaparecidas" - tema inventado, sem
    # cobertura de imagem específica, só achava foto genérica/institucional).
    MIN_SUGGESTION_IMAGES = 3
    validated = []
    for label, query in raw_suggestions:
        if len(validated) >= count:
            break
        try:
            found = _search_relevant_images([query], query, target_count=MIN_SUGGESTION_IMAGES)
        except Exception:
            found = []
        if len(found) >= MIN_SUGGESTION_IMAGES:
            validated.append((label, query))
        else:
            notify.log(
                f"[{channel['name']}] Sugestão de tema descartada por falta de imagem real: "
                f"\"{label}\" (achou só {len(found)}/{MIN_SUGGESTION_IMAGES} pra \"{query}\")."
            )
    return validated


def _generate_with_llm(topic: str, facts: str, angle: str, niche: str, feedback_section: str,
                        language_name: str) -> dict | None:
    # Sem "format: json" - modelos locais rodando em CPU podem travar o
    # decodificador com gramática JSON quando o texto de entrada tem
    # caracteres especiais (aspas curvas, etc). Texto livre com marcadores
    # simples é mais robusto aqui.
    prompt = PROMPT_TEMPLATE.format(
        topic=topic, facts=facts, angle=angle, niche=niche, feedback_section=feedback_section,
        language_name=language_name,
    )
    text = _call_ollama(prompt)
    return _parse_llm_output(text) if text else None


def _fact_check(script: str, facts: str) -> tuple[str, str | None]:
    """Segunda passada do LLM conferindo se as afirmações do roteiro batem
    com os fatos-fonte. Não bloqueia o pipeline (o gate de revisão humana já
    existe pra isso) - só marca o track pra o dono saber que aquele vídeo
    merece uma conferida extra antes de aprovar, em vez de tratar todos os
    vídeos como igualmente confiáveis.

    Retorna "sem_fonte" (fallback sem fatos reais pra checar), "ok", "atencao"
    ou "indisponivel" (Ollama fora do ar - roteiro segue pro pipeline normal,
    só sem o selo extra de confiança).
    """
    if not facts or facts.startswith("(sem explicação factual") or facts.startswith("(tema pedido manualmente"):
        return "sem_fonte", None

    prompt = FACT_CHECK_TEMPLATE.format(facts=facts, script=script)
    text = _call_ollama(prompt, timeout=120)
    if not text or not _has_marker(text, "RESULTADO:"):
        return "indisponivel", None

    after_result = _split_at_marker(text, "RESULTADO:")[1]
    result_line = after_result.split("\n", 1)[0].strip().upper()
    flag = "ok" if result_line.startswith("OK") else "atencao"

    details = None
    if _has_marker(after_result, "DETALHES:"):
        details = _split_at_marker(after_result, "DETALHES:")[1].strip()
    return flag, details


_NEWS_IMAGE_VOCAB = {
    "hubble", "webb", "jwst", "iss", "mars", "moon", "venus", "jupiter", "saturn",
    "mercury", "neptune", "uranus", "pluto", "galaxy", "nebula", "comet", "asteroid",
    "rocket", "satellite", "telescope", "station", "launch", "mission", "orbit",
    "astronaut", "sun", "solar", "lunar", "meteor", "planet", "star", "esa", "nasa",
    "spacex", "starship", "artemis", "supernova", "eclipse", "spacewalk",
}


def _news_image_keywords(title: str) -> list[str]:
    """Extrai termos concretos e prováveis de dar match na busca de imagem
    (NASA/ESA) a partir de um título de notícia em inglês - usar o título
    inteiro como query falha quase sempre (a busca da NASA é por texto
    literal em metadado, não semântica). Prioriza nomes próprios (sequências
    de palavras capitalizadas: "Vera Rubin", "James Webb"), siglas
    (instrumentos/agências: NASA, ESA, JWST) e vocabulário conhecido de
    astronomia/espaço que aparece na frase."""
    keywords = []
    keywords += re.findall(r"\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)+\b", title)
    keywords += re.findall(r"\b[A-Z]{2,6}\b", title)
    words = re.findall(r"[A-Za-z][A-Za-z']*", title)
    keywords += [w for w in words if w.lower() in _NEWS_IMAGE_VOCAB]

    seen = set()
    unique = []
    for k in keywords:
        key = k.lower()
        if key not in seen:
            seen.add(key)
            unique.append(k)
    return unique[:5]


def _choose_news_topic(channel: sqlite3.Row) -> tuple[str, str, str, list] | None:
    """Fallback de conteúdo por notícia real recente (Spaceflight News API),
    tentado ANTES de cair no tema genérico fixo da rotação - dá ao canal
    conteúdo atual/factual em vez de só reciclar a mesma lista de temas.
    Só usa a notícia se a busca de imagem pra ela realmente encontrar pelo
    menos 2 imagens reais (NASA/ESA) - sem isso, cai silenciosamente pra
    próxima notícia, e se nenhuma render imagem, retorna None pro chamador
    seguir pro fallback de tema rotativo de sempre. Também evita repetir
    notícia cujo título já apareceu num tema recente do canal."""
    try:
        articles = visual_source.fetch_recent_space_news(limit=10)
    except Exception:
        return None

    recent = list(catalog.recent_topics(channel["id"], lookback=15))
    for article in articles:
        title = (article.get("title") or "").strip()
        summary = (article.get("summary") or "").strip()
        if not title or len(summary) < 100:
            continue
        if any(title.lower() in r.lower() or r.lower() in title.lower() for r in recent):
            continue

        keywords = _news_image_keywords(title)
        if not keywords:
            continue

        assets = []
        seen_paths = set()

        def _collect(new_assets):
            for a in new_assets:
                if a.local_path not in seen_paths:
                    assets.append(a)
                    seen_paths.add(a.local_path)

        for kw in keywords:
            if len(assets) >= 4:
                break
            try:
                found = visual_source.fetch_nasa_images_for_topic(kw, count=4 - len(assets))
                _collect(semantic.filter_relevant_by_image(title, found))
            except Exception:
                pass
        for kw in keywords:
            if len(assets) >= 4:
                break
            try:
                found = visual_source.fetch_esa_hubble_images_for_topic(kw, count=4 - len(assets))
                _collect(semantic.filter_relevant_by_image(title, found))
            except Exception:
                pass
        for kw in keywords:
            if len(assets) >= 4:
                break
            try:
                found = visual_source.fetch_eso_images_for_topic(kw, count=4 - len(assets))
                _collect(semantic.filter_relevant_by_image(title, found))
            except Exception:
                pass
        for kw in keywords:
            if len(assets) >= 4:
                break
            try:
                found = visual_source.fetch_noirlab_images_for_topic(kw, count=4 - len(assets))
                _collect(semantic.filter_relevant_by_image(title, found))
            except Exception:
                pass
        if len(assets) < 2:
            continue

        return title, keywords[0], summary, assets

    return None


def _choose_fallback_topic(channel: sqlite3.Row) -> tuple[str, str]:
    """Escolhe um tema da lista rotativa do canal evitando repetir os últimos
    usados - sem isso, rodando 1x/dia por meses, a lista de 10 temas padrão
    se esgota (repetição perceptível) em ~1-2 semanas. Se todos os temas
    estiverem "recentes" (lista curta ou canal muito ativo), cai de volta pra
    sorteio livre em vez de travar."""
    topics = channels.topics_for(channel)
    recent = catalog.recent_topics(channel["id"], lookback=max(len(topics) - 2, 3))
    available = [t for t in topics if t[0] not in recent]
    return random.choice(available or topics)


# Framework de fontes de conteúdo plugável - cada fonte é uma função
# (channel, api_key) -> dict | None. None significa "essa fonte não rendeu
# conteúdo hoje, tenta a próxima"; um dict de resultado precisa ter as
# chaves topic/image_query/facts/assets/has_source (has_source=True usa a
# série "primária" do canal, por ter uma fonte factual real e checável -
# ver build_daily_script). Adicionar uma fonte nova (ex.: um feed RSS de
# outro nicho) é só escrever a função no mesmo formato e colocar na lista
# CONTENT_SOURCES, na ordem de prioridade desejada - nenhuma outra parte do
# pipeline precisa mudar. _source_rotation é o fallback garantido (nunca
# retorna None), por isso fica fora da lista, chamado só se todas as fontes
# em CONTENT_SOURCES falharem.
def _source_apod(channel: sqlite3.Row, api_key: str) -> dict | None:
    """NASA Astronomy Picture of the Day - fonte factual primária de sempre,
    prioridade máxima quando rende uma explicação longa o bastante pra
    embasar um roteiro de verdade."""
    try:
        apod = visual_source.fetch_apod(api_key=api_key)
    except Exception:
        return None
    if not (apod and apod["asset"] and len(apod["explanation"]) > 100):
        return None

    # Bug real (relatado pelo dono, com print do vídeo): a "imagem do dia"
    # da APOD às vezes é literalmente o LOGOTIPO da NASA, não uma foto -
    # passava sem checagem nenhuma porque essa imagem nunca passava pelo
    # filtro de relevância (só as imagens achadas por busca passavam). Se não
    # parecer foto de verdade, não usa como âncora - o conteúdo factual
    # (título/explicação) continua valendo normalmente, e a busca por
    # palavra-chave mais abaixo acha uma foto real pro vídeo.
    if not semantic.is_real_photo(apod["asset"].local_path):
        apod = {**apod, "asset": None}

    return {
        "topic": apod["title"], "image_query": apod["title"], "facts": apod["explanation"],
        "assets": [apod["asset"]] if apod["asset"] else [], "has_source": True, "apod": apod,
    }


def _source_news(channel: sqlite3.Row, api_key: str) -> dict | None:
    """Notícia real recente de espaço/astronomia (Spaceflight News API), só
    aceita se conseguir imagem de verdade pra ela (ver _choose_news_topic)."""
    news_result = _choose_news_topic(channel)
    if not news_result:
        return None
    topic, image_query, facts, assets = news_result
    return {"topic": topic, "image_query": image_query, "facts": facts, "assets": assets, "has_source": True}


CONTENT_SOURCES = [_source_apod, _source_news]


def _source_rotation(channel: sqlite3.Row) -> dict:
    """Fallback garantido - tema da lista rotativa configurada no canal, sem
    fonte factual do dia pra checar. Nunca retorna None."""
    topic, image_query = _choose_fallback_topic(channel)
    facts = f"(sem explicação factual da APOD hoje - roteirista deve pesquisar sobre {topic} antes de gravar)"
    return {"topic": topic, "image_query": image_query, "facts": facts, "assets": [], "has_source": False}


def _search_relevant_images(search_queries: list[str], relevance_reference: str,
                             target_count: int = 6, seen_paths: set | None = None) -> list:
    """Busca imagens reais (NASA + ESA/Hubble + ESO + NOIRLab) pros termos em
    `search_queries` e mantém só as que o CLIP confirma serem visualmente
    relacionadas a `relevance_reference` (ambos sempre em inglês - ver
    comentário em build_daily_script sobre por quê). Extraído como função
    própria pra ser reaproveitado tanto na geração do vídeo em si quanto na
    validação de sugestão de tema (suggest_topics) - mesma régua nos dois
    lugares, sem duplicar a lógica."""
    assets: list = []
    seen_paths = seen_paths if seen_paths is not None else set()

    def _add_unique(new_assets):
        for a in new_assets:
            if a.local_path not in seen_paths:
                assets.append(a)
                seen_paths.add(a.local_path)

    fetchers = [
        visual_source.fetch_nasa_images_for_topic,
        visual_source.fetch_esa_hubble_images_for_topic,
        visual_source.fetch_eso_images_for_topic,
        visual_source.fetch_noirlab_images_for_topic,
    ]
    for query in search_queries:
        if len(assets) >= target_count:
            break
        for fetch in fetchers:
            if len(assets) >= target_count:
                break
            try:
                found = fetch(query, count=target_count - len(assets))
                _add_unique(semantic.filter_relevant_by_image(relevance_reference, found))
            except Exception:
                continue
    return assets


def build_daily_script(channel: sqlite3.Row, forced_topic: tuple[str, str] | None = None,
                        _exclude_topics: set[str] | None = None, _is_retry: bool = False) -> dict:
    """Retorna {"title", "script", "topic", "visual_assets", "fact_check"}.

    `topic` é o rótulo em português usado no roteiro. `image_query` (interno)
    é o termo em inglês usado pra buscar imagens relacionadas de verdade ao
    assunto do vídeo - as APIs da NASA/ESA só indexam metadado em inglês, e
    perguntar por um termo genérico desconectado do tema faria a imagem não
    condizer com o que está sendo narrado.

    `forced_topic` (label, termo_busca_ingles) - quando o dono pede um vídeo
    sob demanda com tema específico (ver orchestrator.prepare_daily_video),
    pula a busca de APOD/tema rotativo e usa esse tema direto. Sem fonte
    factual do dia pra checar (mesma limitação honesta do fallback de tema
    rotativo - o LLM escreve com conhecimento geral, fact-check fica
    "sem_fonte" em vez de "ok", o que é o sinal correto nesse caso).

    `_exclude_topics`/`_is_retry` são uso interno (ver mais abaixo): quando a
    geração automática (sem forced_topic do dono) não acha imagens REAIS o
    bastante pro tema escolhido, troca pra outro tema da rotação em vez de
    completar o vídeo com imagem genérica/sem relação - "não é permitido
    criar vídeo com imagens genéricas" é uma regra do dono, não só uma
    preferência. Um `forced_topic` vindo de pedido explícito do dono NUNCA
    troca de tema sozinho (ele pediu aquele tema especificamente) - só falha
    com um erro claro, pra ele decidir o que fazer.
    """
    api_key = channels.nasa_api_key_for(channel)
    user_forced = forced_topic is not None and not _is_retry

    if forced_topic:
        topic, image_query = forced_topic
        if _is_retry:
            facts = (
                f"(tema alternativo escolhido automaticamente - o tema anterior não teve imagens reais "
                f"suficientes - sem explicação factual do dia; roteirista deve usar conhecimento geral "
                f"confiável sobre {topic})"
            )
        else:
            facts = f"(tema pedido manualmente pelo dono - sem explicação factual do dia; roteirista deve usar conhecimento geral confiável sobre {topic})"
        assets = []
        apod = None
        series = channel["series_fallback"]
    else:
        apod = None
        result = None
        for source_fn in CONTENT_SOURCES:
            try:
                result = source_fn(channel, api_key)
            except Exception:
                result = None
            if result:
                break
        if not result:
            result = _source_rotation(channel)

        topic, image_query, facts, assets = result["topic"], result["image_query"], result["facts"], result["assets"]
        series = channel["series_primary"] if result["has_source"] else channel["series_fallback"]
        apod = result.get("apod")

    angle = random.choice(PROMPT_ANGLES)
    niche = channel["niche"] or "ciência"
    language = channels.language_for(channel)
    language_code = channel["language"] or config.DEFAULT_LANGUAGE

    if not ollama_available():
        notify.log(
            f"[{channel['name']}] Ollama não respondeu em localhost:11434 - usando fallback fraco de "
            "roteiro (fatos em inglês, sem reescrita). Confira se `ollama serve` está rodando."
        )
        generated = _fallback_script(topic, facts, language_code)
        fact_check, fact_check_details = "indisponivel", None
    else:
        feedback_section = _feedback_section(channel["id"])
        generated = (
            _generate_with_llm(topic, facts, angle, niche, feedback_section, language["llm_language_name"])
            or _fallback_script(topic, facts, language_code)
        )
        # Revisão de texto (gramática/fluência/naturalidade) ANTES do
        # fact-check, pra checar precisão sobre o texto que de fato vai ser
        # narrado (a revisão não deve mudar fatos, mas se mudar algo por
        # engano, é essa versão final que precisa ser validada).
        generated["script"] = polish_script(generated["script"], niche)
        fact_check, fact_check_details = _fact_check(generated["script"], facts)

    # Um vídeo longo com uma imagem só fica monótono. Busca por várias
    # imagens relacionadas ao tema real (NASA + ESA/Hubble). Prioriza as
    # palavras-chave específicas que o próprio LLM extraiu dos fatos-fonte
    # (ex.: nome do objeto, instrumento, fenômeno) em vez de só o título bruto
    # da APOD, que às vezes é genérico/estilizado demais pra achar imagens
    # relacionadas de verdade - imagem que não bate com o que está sendo
    # narrado faz o vídeo perder sentido, mesmo com imagens bonitas.
    seen_paths = {asset.local_path for asset in assets}
    target_count = 6
    # O LLM nem sempre obedece à instrução de responder as palavras-chave de
    # imagem em inglês (bug real observado: termo veio em português mesmo
    # pedindo inglês) - filtra qualquer termo com diacrítico claramente
    # português (á, ã, ç, õ etc, que não aparecem em inglês) antes de usar
    # pra buscar (a API da NASA/ESA é indexada em inglês - termo em
    # português não acha nada mesmo) ou pra medir relevância (o modelo de
    # embeddings só entende inglês de verdade - ver comentário abaixo).
    raw_keywords = (generated.get("image_keywords") or []) + [image_query]
    english_keywords = [k for k in raw_keywords if not _PT_DIACRITICS_RE.search(k)]
    # Se TUDO tiver caído (até o image_query veio com acento), melhor buscar
    # com o que tem do que não buscar nada - mas prioriza sempre os termos
    # que parecem inglês primeiro.
    search_queries = list(dict.fromkeys(english_keywords)) or list(dict.fromkeys(raw_keywords))

    # Âncora de relevância ESTÁVEL pro vídeo inteiro, EM INGLÊS - 2 bugs reais
    # encontrados aqui, em sequência:
    # 1) Comparar contra o termo de busca da iteração atual deixava passar
    #    imagem sem relação real quando esse termo era genérico (ex.: título
    #    de APOD "NASA Science" batendo com fotos de um evento de relações
    #    públicas da NASA) - corrigido comparando contra o conteúdo real do
    #    vídeo, não o termo que achou a imagem.
    # 2) Esse "conteúdo real" estava em PORTUGUÊS (título/fatos do roteiro),
    #    mas o modelo de embeddings usado (bge-small-en-v1.5) é SÓ EM INGLÊS -
    #    a pontuação de relevância contra título de imagem em inglês virava
    #    praticamente ruído (uma foto de "Meeting of Brazil Participation
    #    Group" pontuou MAIS alto que "Hubble Deep Field" num caso real).
    #    Testado e confirmado: usando as palavras-chave em inglês que o
    #    próprio LLM já extrai pra busca (`search_queries`, sempre em inglês
    #    por instrução do prompt) como referência, a separação fica nítida
    #    (~0.5 pra foto irrelevante vs ~0.7-0.8 pra imagem real de
    #    astronomia). NUNCA usar texto em português aqui enquanto o modelo
    #    for só-inglês.
    relevance_reference = " ".join(search_queries) or (generated.get("title") or topic)

    found_assets = _search_relevant_images(
        search_queries, relevance_reference, target_count=target_count - len(assets), seen_paths=seen_paths
    )
    assets.extend(found_assets)

    # Regra do dono: NUNCA completar o vídeo com imagem genérica/sem relação
    # real ao tema - antes causava vídeos com fotos completamente
    # desconectadas do que estava sendo narrado. Em vez de um pool genérico
    # de último recurso, se a busca específica (keywords do roteiro + termo
    # da APOD/notícia, em 4 fontes reais) não trouxe o mínimo de imagens
    # relevantes, troca de tema (só quando o tema não foi pedido explicitamente
    # pelo dono - ver docstring) e tenta de novo do zero, em vez de publicar
    # algo sem relação.
    MIN_REAL_IMAGES = 3
    if len(assets) < MIN_REAL_IMAGES:
        if user_forced:
            raise RuntimeError(
                f"Não encontrei imagens reais o bastante relacionadas a \"{topic}\" (achei só {len(assets)}, "
                f"preciso de pelo menos {MIN_REAL_IMAGES}) - o pipeline não usa imagem genérica/sem relação "
                "pra completar o vídeo. Tente outro tema ou termo de busca."
            )
        exclude = (_exclude_topics or set()) | {topic}
        all_topics = channels.topics_for(channel)
        candidates = [t for t in all_topics if t[0] not in exclude]
        if not candidates:
            raise RuntimeError(
                f"Não encontrei imagens reais o bastante pra nenhum tema tentado hoje no canal "
                f"'{channel['name']}' (tentados: {sorted(exclude)}) - pulando a geração hoje em vez de "
                "publicar vídeo com imagem genérica/sem relação."
            )
        retry_topic = random.choice(candidates)
        notify.log(
            f"[{channel['name']}] \"{topic}\" não teve imagens específicas suficientes "
            f"({len(assets)}/{MIN_REAL_IMAGES}) - trocando pro tema \"{retry_topic[0]}\" em vez de usar "
            "imagem genérica/sem relação."
        )
        return build_daily_script(channel, forced_topic=retry_topic, _exclude_topics=exclude, _is_retry=True)

    # Ordena por resolução (maior primeiro) para as imagens de melhor qualidade
    # aparecerem nos primeiros segundos do vídeo. A imagem da APOD é mantida
    # como âncora inicial quando presente, pois é a base factual real do
    # roteiro - trocá-la de posição quebraria a ligação entre o que é dito no
    # gancho inicial e o que é mostrado na tela.
    has_apod_anchor = bool(apod and apod.get("asset"))
    anchor, rest = (assets[0], assets[1:]) if has_apod_anchor else (None, assets)
    rest.sort(key=_image_resolution, reverse=True)
    assets = ([anchor] if anchor else []) + rest

    return {
        "title": generated["title"],
        "script": generated["script"],
        "topic": topic,
        "visual_assets": assets,
        "fact_check": fact_check,
        "fact_check_details": fact_check_details,
        "series": series,
        # Termos em inglês usados pra achar/filtrar as imagens - expostos pra
        # quem for medir relevância de imagem (compute_quality_score) também
        # comparar em inglês, pelo mesmo motivo do fix acima (modelo de
        # embeddings é só-inglês; comparar com `topic` em português não
        # funciona de verdade).
        "image_search_terms": relevance_reference,
    }


def compute_quality_score(fact_check: str, clarity_review: str | None, assets: list, topic: str,
                           repetition_score: float | None = None) -> tuple[int, str]:
    """Score agregado (0-100) pra dar ao revisor um resumo rápido de quão
    confiável e original esse vídeo específico tende a ser, ANTES de
    assistir tudo - cruza os quatro sinais de qualidade automática que o
    pipeline já calcula separadamente (precisão factual, clareza pra leigo,
    relevância real das imagens, e agora diversidade em relação aos vídeos
    recentes do canal - o YouTube penaliza reciclagem de hook/formato, ver
    ROADMAP.md), que antes só apareciam badges soltos sem resumo único. Não
    bloqueia nada - é só um resumo pro revisor priorizar onde olhar com mais
    atenção; a decisão final continua sendo humana."""
    notes = []

    fact_points = {"ok": 30, "sem_fonte": 22, "indisponivel": 22, "atencao": 8}.get(fact_check, 17)
    notes.append(f"Fatos: {fact_points}/30 ({fact_check})")

    if not clarity_review or clarity_review.lower().startswith("nenhum"):
        clarity_points = 30
        notes.append("Clareza: 30/30 (sem risco sinalizado)")
    else:
        clarity_points = 12
        notes.append("Clareza: 12/30 (revisão apontou trecho(s) confuso(s)/redundante(s))")

    image_points = 17  # neutro se não der pra medir (modelo indisponível, sem assets)
    avg_relevance = semantic.average_visual_relevance(topic, assets) if assets else None
    if avg_relevance is not None:
        # Score de similaridade do CLIP (0-1 teórico, mas pares relacionados
        # de verdade ficam numa faixa bem mais estreita que isso - calibrado
        # empiricamente em 03/10/2026: ~0.03-0.19 pra imagem sem relação,
        # ~0.21-0.35 pra imagem realmente relacionada). Remapeia linearmente
        # esse intervalo pra 0-25 pontos em vez de usar a pontuação crua
        # (que deixaria até imagem boa parecendo "nota baixa" pro revisor).
        image_points = round(max(0.0, min((avg_relevance - 0.10) / 0.25, 1.0)) * 25)
        notes.append(f"Imagens: {image_points}/25 (relevância visual média {avg_relevance:.2f})")
    else:
        notes.append(f"Imagens: {image_points}/25 (não foi possível medir)")

    diversity_points = 10  # neutro se não der pra medir (canal sem histórico ainda, ou modelo indisponível)
    if repetition_score is not None:
        if repetition_score >= semantic.REPETITION_THRESHOLD:
            diversity_points = 3
            notes.append(f"Diversidade: 3/15 (parecido demais com vídeo recente, similaridade {repetition_score:.2f})")
        else:
            diversity_points = 15
            notes.append(f"Diversidade: 15/15 (tema/gancho distinto dos recentes, similaridade {repetition_score:.2f})")
    else:
        notes.append("Diversidade: 10/15 (sem histórico suficiente pra comparar)")

    score = min(fact_points + clarity_points + image_points + diversity_points, 100)
    return score, " | ".join(notes)
