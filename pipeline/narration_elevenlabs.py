"""Narração via API paga da ElevenLabs - qualidade bem mais natural que o
motor gratuito (edge-tts), usada só quando o canal tem `tts_provider` =
'elevenlabs' configurado com a própria chave do dono. Qualquer falha aqui
(cota do plano grátis estourada, chave inválida/expirada, API fora do ar)
deve ser tratada pelo chamador (narration.py) como sinal pra cair de volta
pro edge-tts - a geração diária automática nunca pode travar esperando um
provedor pago responder.
"""

import base64
from pathlib import Path

import requests

from pipeline import text_normalize
from pipeline.atomic_io import atomic_write_bytes

API_BASE = "https://api.elevenlabs.io/v1"
DEFAULT_MODEL = "eleven_multilingual_v2"


def _words_from_alignment(alignment: dict) -> list[dict]:
    """A ElevenLabs devolve timestamp POR CARACTERE, não por palavra (ao
    contrário do WordBoundary do edge-tts) - agrupa por espaço em branco.
    Como o texto já é exatamente o que foi enviado (normalizado, com
    pontuação), as palavras já saem "prontas" - sem precisar da lógica de
    realinhamento de pontuação que o caminho do edge-tts usa."""
    chars = alignment["characters"]
    starts = alignment["character_start_times_seconds"]
    ends = alignment["character_end_times_seconds"]

    words = []
    buf_chars: list[str] = []
    buf_start = None
    buf_end = None
    for ch, start, end in zip(chars, starts, ends):
        if ch.isspace():
            if buf_chars:
                words.append({"text": "".join(buf_chars), "start": buf_start, "duration": buf_end - buf_start})
                buf_chars = []
                buf_start = None
        else:
            if buf_start is None:
                buf_start = start
            buf_chars.append(ch)
            buf_end = end
    if buf_chars:
        words.append({"text": "".join(buf_chars), "start": buf_start, "duration": buf_end - buf_start})
    return words


def synthesize_with_boundaries(text: str, output_path: Path, api_key: str, voice_id: str,
                                model_id: str = DEFAULT_MODEL) -> tuple[Path, list[dict]]:
    text = text_normalize.normalize_for_speech(text)
    response = requests.post(
        f"{API_BASE}/text-to-speech/{voice_id}/with-timestamps",
        headers={"xi-api-key": api_key, "Content-Type": "application/json"},
        json={"text": text, "model_id": model_id},
        timeout=90,
    )
    response.raise_for_status()
    data = response.json()
    audio_bytes = base64.b64decode(data["audio_base64"])
    atomic_write_bytes(output_path, audio_bytes)
    boundaries = _words_from_alignment(data["alignment"])
    return output_path, boundaries


def list_voices(api_key: str) -> list[dict]:
    """Vozes disponíveis na conta do dono - usada pra montar o seletor na
    interface. Qualquer voz "multilingual" fala português (o idioma vem do
    TEXTO/modelo, não da voz em si); prioriza aqui as que a própria
    ElevenLabs já confirmou soarem bem em pt no catálogo dessa conta."""
    # /v2/voices é um endpoint de topo, fora do prefixo /v1 usado no resto
    # desse módulo (confirmado por teste real contra a API).
    response = requests.get(
        "https://api.elevenlabs.io/v2/voices",
        headers={"xi-api-key": api_key},
        params={"page_size": 100},
        timeout=30,
    )
    response.raise_for_status()
    voices = response.json().get("voices", [])

    def _has_pt(voice: dict) -> bool:
        return any(lang.get("language") == "pt" for lang in voice.get("verified_languages") or [])

    voices.sort(key=lambda v: not _has_pt(v))
    return voices


def check_key_valid(api_key: str) -> bool:
    try:
        response = requests.get(
            f"{API_BASE}/user/subscription", headers={"xi-api-key": api_key}, timeout=15
        )
        return response.status_code == 200
    except requests.RequestException:
        return False


def remaining_quota(api_key: str) -> tuple[int, int] | None:
    """(caracteres usados, limite do ciclo) do plano ElevenLabs - consulta
    `/v1/user`, que NÃO consome cota de texto-pra-fala (diferente de uma
    chamada de síntese real). Usado pra decidir ANTES de tentar sintetizar
    se vale a pena gastar uma chamada - achado real (09/10/2026): toda
    narração tentava a ElevenLabs primeiro, levava 401 porque a cota mensal
    do plano grátis (10.000 caracteres) já tinha estourado, e só então caía
    pro edge-tts - desperdiçando uma chamada de API (e alguns segundos) em
    TODA narração do mês, com um erro genérico no log que não dizia que era
    só cota, não chave quebrada. Retorna None se a consulta falhar (fail-
    open: deixa o chamador tentar a síntese normalmente, que vai falhar e
    cair pro edge-tts do jeito de sempre, só sem o diagnóstico extra)."""
    try:
        response = requests.get(f"{API_BASE}/user", headers={"xi-api-key": api_key}, timeout=15)
        response.raise_for_status()
        data = response.json().get("subscription", {})
        return data["character_count"], data["character_limit"]
    except Exception:
        return None
