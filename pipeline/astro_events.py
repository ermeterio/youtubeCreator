"""Calendário de eventos astronômicos reais (eclipses, chuvas de meteoro,
superluas, conjunções) - usado pra disparar o tema do dia ANTES do evento
acontecer, capturando o pico de busca real que esses eventos geram (prática
validada: ver space.com/seasky.org, recomendação de publicar guia de
observação antes do evento, não depois).

Datas verificadas por pesquisa real em 07/10/2026 (starwalk.space,
nationalgeographic.com, seasky.org, space.com) - não são estimativas. Cobre
2026; precisa ser estendido com datas de 2027 quando o ano virar (ver
EVENTS abaixo). Enquanto não houver evento na janela de antecedência, o
pipeline segue com a fonte de conteúdo normal (APOD/rotação) - essa função
nunca bloqueia nem força nada sozinha.
"""

from dataclasses import dataclass
from datetime import date


@dataclass
class AstroEvent:
    event_date: date
    label: str  # rótulo em português pro roteiro
    image_query: str  # termo de busca em inglês
    facts: str  # base factual real pro roteirista usar
    lookahead_days: int  # quantos dias ANTES do evento já vale cobrir


EVENTS: list[AstroEvent] = [
    AstroEvent(
        date(2026, 1, 3), "A chuva de meteoros Quadrantidas",
        "Quadrantids meteor shower",
        "A chuva de meteoros Quadrantidas tem pico na noite de 3 para 4 de janeiro de 2026, "
        "com até 40 meteoros por hora em céu limpo - acima da média das chuvas de meteoro do ano.",
        3,
    ),
    AstroEvent(
        date(2026, 1, 10), "Júpiter em oposição",
        "Jupiter opposition brightest",
        "Em 10 de janeiro de 2026, Júpiter está em oposição - mais próximo da Terra e no ponto "
        "mais brilhante e visível de todo o ano, visível a olho nu a noite toda.",
        3,
    ),
    AstroEvent(
        date(2026, 2, 17), "Eclipse solar anular",
        "annular solar eclipse",
        "Em 17 de fevereiro de 2026 ocorre um eclipse solar anular, com trajetória cruzando a "
        "Antártida e a ponta sul da América do Sul.",
        5,
    ),
    AstroEvent(
        date(2026, 4, 22), "A chuva de meteoros Líridas",
        "Lyrids meteor shower",
        "A chuva de meteoros Líridas tem pico em 22 de abril de 2026, com cerca de 18 meteoros "
        "por hora em céu limpo.",
        3,
    ),
    AstroEvent(
        date(2026, 5, 6), "A chuva de meteoros Eta Aquáridas",
        "Eta Aquarids meteor shower",
        "A chuva de meteoros Eta Aquáridas, originada de detritos do cometa Halley, tem pico em "
        "5-6 de maio de 2026, com até 50 meteoros por hora.",
        3,
    ),
    AstroEvent(
        date(2026, 8, 12), "Eclipse solar total",
        "total solar eclipse 2026",
        "Em 12 de agosto de 2026 ocorre um eclipse solar total, com trajetória cruzando a "
        "Islândia, Espanha e uma pequena faixa de Portugal - um dos eventos astronômicos mais "
        "aguardados do ano.",
        7,
    ),
    AstroEvent(
        date(2026, 8, 13), "A chuva de meteoros Perseidas",
        "Perseids meteor shower",
        "A chuva de meteoros Perseidas, uma das mais populares do ano, tem pico na madrugada de "
        "12 para 13 de agosto de 2026 - o período completo da chuva vai de 14 de julho a 1º de "
        "setembro.",
        4,
    ),
    AstroEvent(
        date(2026, 8, 28), "Eclipse lunar parcial",
        "partial lunar eclipse 2026",
        "Em 28 de agosto de 2026 ocorre um eclipse lunar parcial, visível das Américas, da maior "
        "parte da África e da Europa.",
        5,
    ),
    AstroEvent(
        date(2026, 10, 22), "A chuva de meteoros Oriônidas",
        "Orionids meteor shower",
        "A chuva de meteoros Oriônidas, formada por detritos do cometa Halley, tem pico em "
        "21-22 de outubro de 2026, com até 20 meteoros por hora.",
        3,
    ),
    AstroEvent(
        date(2026, 10, 26), "A superlua Lua do Caçador",
        "Hunter's supermoon",
        "Em 26 de outubro de 2026 ocorre a superlua conhecida como Lua do Caçador (Hunter's Moon) "
        "- cheia e mais próxima da Terra que o normal, parecendo maior e mais brilhante no céu.",
        2,
    ),
    AstroEvent(
        date(2026, 11, 17), "A chuva de meteoros Leônidas",
        "Leonids meteor shower",
        "A chuva de meteoros Leônidas tem pico em meados de novembro de 2026, produzindo entre "
        "10 e 15 meteoros por hora, tipicamente rápidos e brilhantes.",
        3,
    ),
    AstroEvent(
        date(2026, 11, 16), "A conjunção entre Marte e Júpiter",
        "Mars Jupiter conjunction",
        "Em 16 de novembro de 2026, Marte e Júpiter ficam a cerca de 1 grau de distância um do "
        "outro no céu - a conjunção planetária mais bem posicionada do ano pra observação.",
        3,
    ),
    AstroEvent(
        date(2026, 11, 24), "A superlua Lua do Castor",
        "Beaver supermoon",
        "Em 24 de novembro de 2026 ocorre a superlua conhecida como Lua do Castor (Beaver Moon), "
        "cheia e mais próxima da Terra que o normal.",
        2,
    ),
    AstroEvent(
        date(2026, 12, 14), "A chuva de meteoros Gemínidas",
        "Geminids meteor shower",
        "A chuva de meteoros Gemínidas, considerada uma das melhores do ano, tem pico na "
        "madrugada de 13 para 14 de dezembro de 2026, com até 150 meteoros por hora vindos dos "
        "detritos do asteroide 3200 Phaethon.",
        4,
    ),
    AstroEvent(
        date(2026, 12, 24), "A superlua Lua Fria",
        "Cold supermoon December",
        "Em 24 de dezembro de 2026 ocorre a Lua Fria (Cold Moon) - a lua cheia mais próxima da "
        "Terra do ano, a maior e mais brilhante superlua de 2026.",
        2,
    ),
]


def upcoming_event(today: date | None = None) -> AstroEvent | None:
    """Evento cuja janela de antecedência (lookahead_days) inclui hoje - ou
    None se nenhum evento estiver próximo. Se mais de um evento qualificar
    (raro, mas aconteceu em 2026: eclipse solar e Perseidas quase juntos),
    prioriza o mais PRÓXIMO no tempo."""
    today = today or date.today()
    candidates = [
        e for e in EVENTS
        if 0 <= (e.event_date - today).days <= e.lookahead_days
    ]
    if not candidates:
        return None
    return min(candidates, key=lambda e: e.event_date)
