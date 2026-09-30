"""Narração via edge-tts (voz neural gratuita da Microsoft, sem GPU e sem
custo). Roda de forma assíncrona por baixo dos panos; a função pública aqui é
síncrona pra simplificar o uso no orquestrador.
"""

import asyncio
import re
from pathlib import Path

import edge_tts

import config
from pipeline import notify, text_normalize


def _strip_punct(word: str) -> str:
    return re.sub(r"^\W+|\W+$", "", word, flags=re.UNICODE)


def _align_punctuation(script: str, boundaries: list[dict]) -> list[dict]:
    """Os eventos WordBoundary do edge-tts vêm SEM pontuação (nem "?", nem
    ",", nem nada) - o TTS descarta isso ao emitir o texto de cada palavra,
    mesmo lendo a pontuação em voz alta (entonação de pergunta etc.). Isso
    deixava as legendas na tela sem pontuação, o que fica estranho/mal lido
    (ex.: uma pergunta sem "?"). Aqui a gente re-casa cada palavra do
    boundary com o token correspondente no roteiro ORIGINAL (que tem a
    pontuação), avançando sequencialmente pelo texto - os boundaries chegam
    na mesma ordem em que aparecem no roteiro, então o casamento por posição
    é confiável na grande maioria dos casos."""
    tokens = script.split()
    aligned = []
    ti = 0
    for boundary in boundaries:
        target = boundary["text"].strip().lower()
        matched = None
        # procura o próximo token cujo "miolo" (sem pontuação) bate com a
        # palavra do boundary - pula tokens que não batem (ex.: diferenças
        # de tokenização entre o TTS e o split por espaço)
        while ti < len(tokens):
            token = tokens[ti]
            ti += 1
            if _strip_punct(token).lower() == target:
                matched = token
                break
        aligned.append({**boundary, "text": matched or boundary["text"]})
    return aligned


async def _synthesize(text: str, output_path: Path, voice: str,
                       rate: str = "+0%", pitch: str = "+0Hz") -> list[dict]:
    """Sintetiza e, ao mesmo tempo, coleta os eventos WordBoundary que o
    edge-tts já emite durante a geração - dão o timestamp exato (em segundos)
    de cada palavra narrada, sem precisar de transcrição/alinhamento à parte.
    Usado para sincronizar as legendas dinâmicas no vídeo.

    `rate`/`pitch` ajustam ritmo e tom da voz neural (ex.: "-10%", "-5Hz") -
    reduzem a sensação robótica sem trocar de voz nem custar nada."""
    text = text_normalize.normalize_for_speech(text)
    communicate = edge_tts.Communicate(text, voice, rate=rate, pitch=pitch, boundary="WordBoundary")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    boundaries = []
    with open(output_path, "wb") as f:
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                f.write(chunk["data"])
            elif chunk["type"] == "WordBoundary":
                boundaries.append({
                    "text": chunk["text"],
                    "start": chunk["offset"] / 10_000_000,
                    "duration": chunk["duration"] / 10_000_000,
                })
    return _align_punctuation(text, boundaries)


def generate_narration(text: str, output_path: Path, voice: str | None = None,
                        rate: str = "+0%", pitch: str = "+0Hz") -> Path:
    asyncio.run(_synthesize(text, output_path, voice or config.NARRATION_VOICE, rate, pitch))
    return output_path


def generate_narration_with_boundaries(text: str, output_path: Path, voice: str | None = None,
                                        rate: str = "+0%", pitch: str = "+0Hz") -> tuple[Path, list[dict]]:
    boundaries = asyncio.run(_synthesize(text, output_path, voice or config.NARRATION_VOICE, rate, pitch))
    return output_path, boundaries


def generate_narration_for_channel(text: str, output_path: Path, channel,
                                    voice: str | None = None, rate: str = "+0%",
                                    pitch: str = "+0Hz") -> tuple[Path, list[dict]]:
    """Ponto de entrada usado pelo orquestrador: decide o provedor (edge-tts
    grátis, ou ElevenLabs se o canal tiver chave configurada) e SEMPRE cai de
    volta pro edge-tts se a ElevenLabs falhar por qualquer motivo (cota do
    plano grátis estourada, chave inválida, API fora do ar) - a geração
    diária automática não pode travar esperando um provedor pago responder."""
    provider = channel["tts_provider"] if "tts_provider" in channel.keys() else "edge"
    api_key = channel["elevenlabs_api_key"] if "elevenlabs_api_key" in channel.keys() else None
    voice_id = channel["elevenlabs_voice_id"] if "elevenlabs_voice_id" in channel.keys() else None

    if provider == "elevenlabs" and api_key and voice_id:
        try:
            from pipeline import narration_elevenlabs
            return narration_elevenlabs.synthesize_with_boundaries(text, output_path, api_key, voice_id)
        except Exception as exc:
            notify.log(
                f"[narração] ElevenLabs falhou ({exc}) - usando edge-tts gratuito pra não travar a geração."
            )

    return generate_narration_with_boundaries(text, output_path, voice=voice, rate=rate, pitch=pitch)


PREVIEW_DIR = config.ASSETS_DIR / "voice_previews"


def get_or_build_voice_preview(voice: str, text: str, rate: str = "+0%", pitch: str = "+0Hz") -> Path:
    """Prévia curta de uma voz específica (+ ritmo/tom), gerada uma vez e
    cacheada em disco (mesma combinação = mesmo arquivo sempre) - usada na
    interface pra ouvir a voz ANTES de escolher, em vez de só ver o nome e
    ter que gerar um vídeo inteiro pra descobrir como ela soa."""
    PREVIEW_DIR.mkdir(parents=True, exist_ok=True)
    suffix = "" if rate == "+0%" and pitch == "+0Hz" else f"_{rate}_{pitch}".replace("%", "pct")
    dest = PREVIEW_DIR / f"{voice}{suffix}.mp3"
    if not dest.exists():
        generate_narration(text, dest, voice=voice, rate=rate, pitch=pitch)
    return dest
