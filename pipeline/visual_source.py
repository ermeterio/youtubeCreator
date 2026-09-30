"""Busca conteúdo visual real e com licença clara para os vídeos:

- NASA Images API (images-api.nasa.gov): pública, sem chave, busca por
  palavra-chave. Uso: domínio público nos EUA (não usar para implicar endosso
  da NASA, não usar o logo/insígnia oficial).
- NASA APOD (api.nasa.gov): precisa de chave gratuita (NASA_API_KEY), retorna
  a imagem do dia + uma explicação em texto que serve de base factual real
  para o roteiro - não é só imagem, é também fonte de conteúdo.
- ESA/Hubble (esahubble.org/images/json/), ESO (eso.org/public/images/json/)
  e NOIRLab (noirlab.edu/public/images/json/): mesmo endpoint JSON não
  documentado oficialmente (mesma plataforma de divulgação compartilhada
  entre esses observatórios), público e funcional, sem chave. Licença CC BY
  4.0 nas três (uso comercial ok, exige crédito visível, não pode insinuar
  endosso do observatório). Confirmado por consulta real aos três endpoints
  em 30/09/2026 - todos devolvem o mesmo formato (`formats_url.screen`,
  `ID`, `Credit`, `Title`), então usam o mesmo código de busca.

Não encontrei API pública equivalente (busca por palavra-chave, JSON) para
outras agências espaciais (JAXA, ISRO, Roscosmos, CSA etc.) - se isso mudar,
dá pra adicionar aqui do mesmo jeito.

Toda imagem baixada é registrada com seu crédito (obrigatório por licença),
para ser exibido no vídeo/descrição.
"""

import ast
import time
from dataclasses import dataclass
from pathlib import Path

import requests

import config
from pipeline.atomic_io import atomic_write_bytes

NASA_IMAGES_SEARCH_URL = "https://images-api.nasa.gov/search"
NASA_APOD_URL = "https://api.nasa.gov/planetary/apod"
ESA_HUBBLE_SEARCH_URL = "https://esahubble.org/images/json/"
ESO_SEARCH_URL = "https://www.eso.org/public/images/json/"
NOIRLAB_SEARCH_URL = "https://noirlab.edu/public/images/json/"
SPACEFLIGHT_NEWS_URL = "https://api.spaceflightnewsapi.net/v4/articles/"

_RETRY_BACKOFF_SECONDS = (2, 8, 20)


def _get_with_retry(url: str, **kwargs) -> requests.Response:
    """GET com retry/backoff curto - o pipeline roda 1x/dia, não é sistema de
    missão crítica, então não vale esperar muito: 3 tentativas, backoff
    exponencial curto, cobre falhas transitórias de rede sem atrasar o dia."""
    last_exc = None
    for attempt, wait in enumerate((0, *_RETRY_BACKOFF_SECONDS)):
        if wait:
            time.sleep(wait)
        try:
            response = requests.get(url, **kwargs)
            response.raise_for_status()
            return response
        except Exception as exc:
            last_exc = exc
    raise last_exc


@dataclass
class VisualAsset:
    local_path: Path
    credit: str
    title: str


def search_nasa_images(query: str, media_type: str = "image", limit: int = 8) -> list[dict]:
    response = _get_with_retry(
        NASA_IMAGES_SEARCH_URL,
        params={"q": query, "media_type": media_type},
        timeout=30,
    )
    items = response.json()["collection"]["items"]
    return items[:limit]


def _download(url: str, dest: Path) -> Path:
    response = _get_with_retry(url, timeout=60)
    # Escrita atômica - o cache dessa imagem é considerado "pronto" só por
    # `dest.exists()` (ver fetch_nasa_images_for_topic/fetch_esa_hubble_
    # images_for_topic); um arquivo truncado por interrupção no meio da
    # escrita ficaria "cacheado" como válido pra sempre, e quebraria toda vez
    # que o PIL tentasse abrir essa imagem depois.
    atomic_write_bytes(dest, response.content)
    return dest


def fetch_nasa_images_for_topic(topic: str, count: int = 6) -> list[VisualAsset]:
    items = search_nasa_images(topic, media_type="image", limit=count)
    assets = []
    for item in items:
        data = item["data"][0]
        nasa_id = data["nasa_id"]
        title = data.get("title", topic)
        # cada item tem um "href" pra um manifesto JSON com as URLs dos arquivos
        manifest = _get_with_retry(item["href"], timeout=30).json()
        image_url = next((u for u in manifest if u.lower().endswith((".jpg", ".png"))), None)
        if not image_url:
            continue
        dest = config.IMAGE_CACHE_DIR / f"{nasa_id}.jpg"
        if not dest.exists():
            _download(image_url, dest)
        assets.append(VisualAsset(local_path=dest, credit="NASA", title=title))
    return assets


def _clean_esa_string(value: str) -> str:
    """A API JSON do ESA/Hubble/ESO/NOIRLab retorna alguns campos de texto
    como repr de bytes Python (ex.: "b'NSF\\xe2\\x80\\x93DOE...'", um
    travessão UTF-8 escapado dentro do repr) - usar ast.literal_eval pra
    reconstruir os bytes de verdade e decodificar, em vez de só cortar o
    "b'"/"'" (que deixava os \\xNN literais no crédito exibido)."""
    if isinstance(value, str) and value.startswith("b'") and value.endswith("'"):
        try:
            return ast.literal_eval(value).decode("utf-8")
        except (ValueError, SyntaxError, UnicodeDecodeError):
            return value[2:-1]
    return value


def _fetch_avm_images_for_topic(search_url: str, prefix: str, default_credit: str,
                                 query: str, count: int = 6) -> list[VisualAsset]:
    """Busca genérica nos observatórios que compartilham a mesma plataforma
    de divulgação (ESA/Hubble, ESO, NOIRLab) - todos devolvem o mesmo formato
    JSON, só muda a URL base e o crédito default."""
    response = _get_with_retry(
        search_url,
        params={"search": query},
        timeout=45,
    )
    items = response.json()[:count]

    assets = []
    for item in items:
        image_url = item.get("formats_url", {}).get("screen")
        image_id = item.get("ID")
        if not image_url or not image_id:
            continue
        dest = config.IMAGE_CACHE_DIR / f"{prefix}_{image_id}.jpg"
        if not dest.exists():
            _download(image_url, dest)
        credit = _clean_esa_string(item.get("Credit") or default_credit)
        title = _clean_esa_string(item.get("Title") or query)
        assets.append(VisualAsset(local_path=dest, credit=credit, title=title))
    return assets


def fetch_esa_hubble_images_for_topic(query: str, count: int = 6) -> list[VisualAsset]:
    return _fetch_avm_images_for_topic(ESA_HUBBLE_SEARCH_URL, "esahubble", "ESA/Hubble", query, count)


def fetch_eso_images_for_topic(query: str, count: int = 6) -> list[VisualAsset]:
    return _fetch_avm_images_for_topic(ESO_SEARCH_URL, "eso", "ESO", query, count)


def fetch_noirlab_images_for_topic(query: str, count: int = 6) -> list[VisualAsset]:
    return _fetch_avm_images_for_topic(NOIRLAB_SEARCH_URL, "noirlab", "NSF NOIRLab", query, count)


def fetch_recent_space_news(limit: int = 10) -> list[dict]:
    """Notícias reais e recentes de espaço/astronomia (Spaceflight News API -
    api.spaceflightnewsapi.net, pública, sem chave, agrega fontes como
    NASA/ESA/SpaceX). Usada como fallback de conteúdo quando a APOD do dia
    não rende um bom tema: cobre lançamentos, descobertas e missões reais e
    atuais, em vez de cair direto pro tema genérico fixo da rotação."""
    response = _get_with_retry(
        SPACEFLIGHT_NEWS_URL,
        params={"limit": limit, "ordering": "-published_at"},
        timeout=20,
    )
    return response.json().get("results", [])


def fetch_apod(api_key: str | None = None) -> dict:
    """Retorna a imagem + explicação do dia da NASA APOD. `api_key` normalmente
    vem do canal (pipeline.channels.nasa_api_key_for); sem chave configurada,
    cai para DEMO_KEY (limite baixo, compartilhado - trocar assim que possível
    por uma chave própria gratuita em https://api.nasa.gov/)."""
    response = _get_with_retry(
        NASA_APOD_URL,
        params={"api_key": api_key or config.NASA_API_KEY},
        timeout=30,
    )
    data = response.json()

    dest = None
    image_url = data.get("hdurl") or data.get("url")
    if image_url and data.get("media_type") == "image":
        dest = config.IMAGE_CACHE_DIR / f"apod_{data['date']}.jpg"
        if not dest.exists():
            _download(image_url, dest)

    return {
        "title": data.get("title", ""),
        "explanation": data.get("explanation", ""),
        "asset": VisualAsset(local_path=dest, credit="NASA", title=data.get("title", "")) if dest else None,
    }
