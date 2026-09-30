"""Expande abreviações/unidades pra narração TTS - sem isso o edge-tts lê
"km/s" soletrando "ká-eme-barra-esse" em vez de "quilômetros por segundo",
o que é uma das causas mais perceptíveis de a narração soar robótica.

Aplicado só no texto que vai pro sintetizador (e por consequência nas legendas,
que são derivadas dos WordBoundary devolvidos pelo TTS) - o roteiro salvo no
banco continua com a forma abreviada original, mais compacta pra leitura na
tela de revisão.
"""

import re

# Ordem importa: unidades compostas (km/s) precisam vir ANTES da unidade
# simples que é prefixo delas (km), senão o regex mais curto casa primeiro e
# sobra um "/s" solto. Match sempre em \b...\b (unidade como token isolado),
# case-insensitive exceto onde indicado.
_COMPOUND_UNITS: list[tuple[str, str]] = [
    (r"km/s", "quilômetros por segundo"),
    (r"km/h", "quilômetros por hora"),
    (r"m/s", "metros por segundo"),
    (r"km\s*/\s*s", "quilômetros por segundo"),
    (r"km\s*/\s*h", "quilômetros por hora"),
    (r"km2|km²", "quilômetros quadrados"),
    (r"m2|m²", "metros quadrados"),
    (r"km3|km³", "quilômetros cúbicos"),
]

_SIMPLE_UNITS: list[tuple[str, str]] = [
    (r"GHz", "gigahertz"),
    (r"MHz", "megahertz"),
    (r"kHz", "quilohertz"),
    (r"Hz", "hertz"),
    (r"kg", "quilogramas"),
    (r"km", "quilômetros"),
    (r"cm", "centímetros"),
    (r"mm", "milímetros"),
    (r"ton", "toneladas"),
    (r"ly", "anos-luz"),
]

# Só casam em maiúsculas exatas - "ua"/"au" minúsculos são comuns demais
# dentro de palavras/ditongos do português pra arriscar um falso positivo.
_CASE_SENSITIVE_UNITS: list[tuple[str, str]] = [
    (r"UA", "unidades astronômicas"),
    (r"AU", "unidades astronômicas"),
]

_COMPOUND_RE = [
    (re.compile(rf"\b{pattern}\b", re.IGNORECASE), repl) for pattern, repl in _COMPOUND_UNITS
]
_SIMPLE_RE = [
    (re.compile(rf"\b{pattern}\b", re.IGNORECASE), repl) for pattern, repl in _SIMPLE_UNITS
]
_CASE_SENSITIVE_RE = [
    (re.compile(rf"\b{pattern}\b"), repl) for pattern, repl in _CASE_SENSITIVE_UNITS
]

# "°" e "%" são símbolos, não caracteres de palavra - \b não marca fronteira
# entre eles e um espaço anterior (os dois são "não-palavra"), por isso
# tratados à parte, sempre consumindo o espaço opcional antes do símbolo.
_PERCENT_RE = re.compile(r"\s?%")
_CELSIUS_RE = re.compile(r"\s?°\s?C\b", re.IGNORECASE)
_FAHRENHEIT_RE = re.compile(r"\s?°\s?F\b", re.IGNORECASE)


def normalize_for_speech(text: str) -> str:
    """Expande unidades abreviadas em texto por extenso, pra narração e
    legendas (derivadas da mesma leitura) soarem naturais em vez de
    soletradas."""
    for pattern, repl in _COMPOUND_RE:
        text = pattern.sub(repl, text)
    for pattern, repl in _SIMPLE_RE:
        text = pattern.sub(repl, text)
    for pattern, repl in _CASE_SENSITIVE_RE:
        text = pattern.sub(repl, text)
    text = _CELSIUS_RE.sub(" graus Celsius", text)
    text = _FAHRENHEIT_RE.sub(" graus Fahrenheit", text)
    text = _PERCENT_RE.sub(" por cento", text)
    return re.sub(r" {2,}", " ", text)
