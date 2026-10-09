"""Busca conteúdo visual real e com licença clara para os vídeos:

- NASA Images API (images-api.nasa.gov): pública, sem chave, busca por
  palavra-chave. Uso: domínio público nos EUA (não usar para implicar endosso
  da NASA, não usar o logo/insígnia oficial). A mesma API também indexa VÍDEO
  real (media_type="video") - clipes reais de telescópio/simulação, não só
  fotos - usado como alternativa ocasional ao Ken Burns sintético pra elevar
  a produção (ver fetch_nasa_videos_for_topic).
- NASA APOD (api.nasa.gov): precisa de chave gratuita (NASA_API_KEY), retorna
  a imagem do dia + uma explicação em texto que serve de base factual real
  para o roteiro - não é só imagem, é também fonte de conteúdo.
- ESA/Hubble (esahubble.org/images/json/), ESA/Webb (esawebb.org/images/json/),
  ESO (eso.org/public/images/json/) e NOIRLab (noirlab.edu/public/images/json/):
  mesmo endpoint JSON não documentado oficialmente (mesma plataforma de
  divulgação compartilhada entre esses observatórios), público e funcional,
  sem chave. Licença CC BY 4.0 nas quatro (uso comercial ok, exige crédito
  visível, não pode insinuar endosso do observatório). Confirmado por consulta
  real aos endpoints em 30/09/2026 (Hubble/ESO/NOIRLab) e 09/10/2026 (Webb) -
  todos devolvem o mesmo formato (`formats_url.screen`, `ID`, `Credit`,
  `Title`), então usam o mesmo código de busca. Webb adicionado por render
  conteúdo genuinamente DIFERENTE do Hubble (infravermelho, alvos/
  processamento distintos), não um espelho - vale como 5ª fonte, não
  redundância.

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
ESA_WEBB_SEARCH_URL = "https://esawebb.org/images/json/"
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
    # video_path preenchido só pra assets de VÍDEO real (ver
    # fetch_nasa_videos_for_topic) - nesse caso, `local_path` aponta pra um
    # FRAME extraído (usado pra checagem de relevância/tipo via CLIP, que só
    # processa imagem) enquanto `video_path` aponta pro .mp4 de verdade, usado
    # na montagem final (ver video_build._ken_burns_clip). Pra um asset de
    # foto normal, fica None e tudo funciona como sempre funcionou.
    video_path: Path | None = None


def search_nasa_images(query: str, media_type: str = "image", limit: int = 8) -> list[dict]:
    response = _get_with_retry(
        NASA_IMAGES_SEARCH_URL,
        params={"q": query, "media_type": media_type},
        timeout=30,
    )
    items = response.json()["collection"]["items"]
    return items[:limit]


# Causa raiz REAL investigada a fundo em 08/10/2026 (dono relatou repetidas
# vezes imagem sem relação com o roteiro, mesmo depois do filtro CLIP já
# existir): a NASA Images API é um arquivo histórico GIGANTE, não um banco
# só de astronomia - qualquer termo de busca minimamente genérico também
# devolve décadas de fotos institucionais (processamento de espaçonave,
# emblema de missão, evento de imprensa, memorial de desastre) que SÃO fotos
# reais do "espaço"/"NASA" o bastante pra passar no filtro visual CLIP (que
# só checa "isso parece foto real de astronomia", não "isso é SOBRE o tema
# certo"). Caso real confirmado: busca por "Columbia Memories" devolveu como
# 1º resultado o memorial do desastre do ônibus espacial Columbia (STS-107) -
# tecnicamente uma "foto real da NASA", nada a ver com o roteiro, e um
# conteúdo sensível demais pra aparecer sem contexto num vídeo que não é
# sobre isso.
#
# Esse tipo de foto SEMPRE vem com metadado textual que entrega a categoria
# (a API devolve `keywords`/`description` além do título, mas o código só
# usava o título) - filtra pela CATEGORIA do conteúdo (administrativo/
# institucional/histórico), não pelo tema buscado, então funciona pra
# QUALQUER termo de busca, não só os já vistos. Validado contra 7 buscas
# reais que causaram imagem errada (Columbia Memories, Pathfinder Journey,
# Pioneer Spirit, Challenger Mindset etc.) e 10 buscas boas conhecidas
# (black hole, Orion nebula, Voyager, Hubble Deep Field etc.) - zero falso
# positivo nas boas, maioria das ruins bloqueada.
_NON_ASTRONOMY_CONTENT_MARKERS = (
    "patch", "insignia", "logo", "memorial", "disaster", "tragedy",
    "processing facilit", "spacecraft processing", "media event",
    "press conference", "crew portrait", "faces of nasa", "clean room",
    "mission patch",
)


def _is_non_astronomy_content(data: dict) -> bool:
    text = " ".join([
        data.get("title") or "",
        " ".join(data.get("keywords") or []),
        (data.get("description") or "")[:300],
    ]).lower()
    return any(marker in text for marker in _NON_ASTRONOMY_CONTENT_MARKERS)


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
    # Pede mais candidatos do que `count` - uma fração vai ser descartada
    # pelo filtro de categoria (_is_non_astronomy_content) antes de virar
    # asset, então pedir exatamente `count` deixaria o vídeo com menos
    # imagens do que devia sempre que a busca tiver ruído institucional.
    items = search_nasa_images(topic, media_type="image", limit=min(count * 3, 20))
    assets = []
    for item in items:
        if len(assets) >= count:
            break
        data = item["data"][0]
        if _is_non_astronomy_content(data):
            continue
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


VIDEO_CACHE_DIR = config.ASSETS_DIR / "nasa_video_cache"


def fetch_nasa_videos_for_topic(topic: str, count: int = 2) -> list[VisualAsset]:
    """Vídeo real (não foto) da NASA Images API pro mesmo tema - usado como
    alternativa ocasional ao Ken Burns sintético (ver video_build.py), pra
    dar movimento de verdade em vez de só pan/zoom sobre foto parada.

    Baixa o tier "medium" (~1280x720, no teste real feito em 05/10/2026) -
    "large"/"orig" ficam grandes demais (75-175MB) pra baixar todo dia sem
    necessidade, "small"/"mobile" ficam baixos demais de resolução pro vídeo
    final em 1080p. Extrai um frame do meio do clipe como thumbnail - é o
    que entra em `local_path` (usado só pra checagem de relevância/tipo via
    CLIP, que não processa vídeo); o .mp4 de verdade fica em `video_path`,
    usado na montagem final."""
    items = search_nasa_images(topic, media_type="video", limit=min(count * 3, 20))
    assets = []
    for item in items:
        if len(assets) >= count:
            break
        data = item["data"][0]
        if _is_non_astronomy_content(data):
            continue
        nasa_id = data["nasa_id"]
        title = data.get("title", topic)
        try:
            manifest = _get_with_retry(item["href"], timeout=30).json()
        except Exception:
            continue
        video_url = next((u for u in manifest if u.lower().endswith("~medium.mp4")), None) or next(
            (u for u in manifest if u.lower().endswith("~small.mp4")), None
        )
        if not video_url:
            continue

        safe_id = "".join(c if c.isalnum() or c in "-_" else "_" for c in nasa_id)
        video_dest = VIDEO_CACHE_DIR / f"{safe_id}.mp4"
        thumb_dest = VIDEO_CACHE_DIR / f"{safe_id}_frame.jpg"
        try:
            if not video_dest.exists():
                _download(video_url, video_dest)
            if not thumb_dest.exists():
                _extract_frame(video_dest, thumb_dest)
        except Exception:
            continue
        assets.append(VisualAsset(local_path=thumb_dest, credit="NASA", title=title, video_path=video_dest))
    return assets


def _extract_frame(video_path: Path, dest: Path) -> Path:
    """Frame do meio do vídeo (evita abertura/fechamento em preto que alguns
    clipes têm no início/fim), salvo como jpg - usado só pra checagem de
    relevância via CLIP (que processa imagem, não vídeo)."""
    from moviepy import VideoFileClip
    from PIL import Image

    with VideoFileClip(str(video_path)) as clip:
        frame = clip.get_frame(clip.duration / 2)
    Image.fromarray(frame).convert("RGB").save(dest, "JPEG", quality=90)
    return dest


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


def fetch_esa_webb_images_for_topic(query: str, count: int = 6) -> list[VisualAsset]:
    return _fetch_avm_images_for_topic(ESA_WEBB_SEARCH_URL, "esawebb", "ESA/Webb", query, count)


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
