"""Busca conteúdo visual real e com licença clara para os vídeos:

- NASA Images API (images-api.nasa.gov): pública, sem chave, busca por
  palavra-chave. Uso: domínio público nos EUA (não usar para implicar endosso
  da NASA, não usar o logo/insígnia oficial).
- NASA APOD (api.nasa.gov): precisa de chave gratuita (NASA_API_KEY), retorna
  a imagem do dia + uma explicação em texto que serve de base factual real
  para o roteiro - não é só imagem, é também fonte de conteúdo.
- ESA/Hubble (esahubble.org/images/json/): endpoint JSON não documentado
  oficialmente, mas público e funcional, sem chave. Licença CC BY 4.0 (uso
  comercial ok, exige crédito visível, não pode insinuar endosso da ESA).

Não encontrei API pública equivalente (busca por palavra-chave, JSON) para
outras agências espaciais (JAXA, ISRO, Roscosmos, CSA etc.) - se isso mudar,
dá pra adicionar aqui do mesmo jeito.

Toda imagem baixada é registrada com seu crédito (obrigatório por licença),
para ser exibido no vídeo/descrição.
"""

import time
from dataclasses import dataclass
from pathlib import Path

import requests

import config

NASA_IMAGES_SEARCH_URL = "https://images-api.nasa.gov/search"
NASA_APOD_URL = "https://api.nasa.gov/planetary/apod"
ESA_HUBBLE_SEARCH_URL = "https://esahubble.org/images/json/"

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
    dest.parent.mkdir(parents=True, exist_ok=True)
    response = _get_with_retry(url, timeout=60)
    dest.write_bytes(response.content)
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
    """A API JSON do ESA/Hubble retorna alguns campos de texto como repr de
    bytes Python (ex.: "b'ESA/Hubble'"). Remove esse envoltório quando presente."""
    if isinstance(value, str) and value.startswith("b'") and value.endswith("'"):
        return value[2:-1]
    return value


def fetch_esa_hubble_images_for_topic(query: str, count: int = 6) -> list[VisualAsset]:
    response = _get_with_retry(
        ESA_HUBBLE_SEARCH_URL,
        params={"search": query},
        timeout=30,
    )
    items = response.json()[:count]

    assets = []
    for item in items:
        image_url = item.get("formats_url", {}).get("screen")
        image_id = item.get("ID")
        if not image_url or not image_id:
            continue
        dest = config.IMAGE_CACHE_DIR / f"esahubble_{image_id}.jpg"
        if not dest.exists():
            _download(image_url, dest)
        credit = _clean_esa_string(item.get("Credit") or "ESA/Hubble")
        title = _clean_esa_string(item.get("Title") or query)
        assets.append(VisualAsset(local_path=dest, credit=credit, title=title))
    return assets


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
