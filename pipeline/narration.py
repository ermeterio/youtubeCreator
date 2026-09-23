"""Narração via edge-tts (voz neural gratuita da Microsoft, sem GPU e sem
custo). Roda de forma assíncrona por baixo dos panos; a função pública aqui é
síncrona pra simplificar o uso no orquestrador.
"""

import asyncio
import re
from pathlib import Path

import edge_tts

import config


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


async def _synthesize(text: str, output_path: Path, voice: str) -> list[dict]:
    """Sintetiza e, ao mesmo tempo, coleta os eventos WordBoundary que o
    edge-tts já emite durante a geração - dão o timestamp exato (em segundos)
    de cada palavra narrada, sem precisar de transcrição/alinhamento à parte.
    Usado para sincronizar as legendas dinâmicas no vídeo."""
    communicate = edge_tts.Communicate(text, voice, boundary="WordBoundary")
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


def generate_narration(text: str, output_path: Path, voice: str | None = None) -> Path:
    asyncio.run(_synthesize(text, output_path, voice or config.NARRATION_VOICE))
    return output_path


def generate_narration_with_boundaries(text: str, output_path: Path,
                                        voice: str | None = None) -> tuple[Path, list[dict]]:
    boundaries = asyncio.run(_synthesize(text, output_path, voice or config.NARRATION_VOICE))
    return output_path, boundaries
