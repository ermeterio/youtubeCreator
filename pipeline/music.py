"""Trilha sonora de fundo com ducking automático - antes o vídeo era
literalmente mudo fora da narração (identificado como a lacuna de maior
impacto de qualidade percebida pelo menor esforço, numa avaliação de dois
agentes especialistas em 05/10/2026).

Faixas validadas de verdade (download real testado, não só citadas como
"deveria existir") de Kevin MacLeod via incompetech.com, licença CC BY 3.0
(uso comercial/monetizado permitido, exige só atribuição textual - ver
ATTRIBUTION_TEMPLATE) - guardadas localmente em data/assets/music/ (ver
scripts/download_music.py pra re-baixar numa instalação nova, já que esses
arquivos binários não vão pro git).

Ducking real (não só volume baixo fixo): detecta os trechos de FALA da
narração (detect_nonsilent) e abaixa a música especificamente nesses
trechos, voltando ao volume normal nas pausas - efeito de mixagem básico
mas real, sem precisar de nenhuma biblioteca nova (só pydub, já usado em
audio_post.py).
"""

import random
from pathlib import Path

from pydub import AudioSegment
from pydub.silence import detect_nonsilent

import config

MUSIC_DIR = config.ASSETS_DIR / "music"

ATTRIBUTION_TEMPLATE = (
    '"{name}" by Kevin MacLeod (incompetech.com)\n'
    "Licensed under Creative Commons: By Attribution 3.0\n"
    "https://creativecommons.org/licenses/by/3.0/"
)

# Catálogo validado em 05/10/2026 (ver pipeline/music.py docstring). "mood"
# agrupa por clima pra casar com o tom do roteiro (ver _pick_mood) - dentro
# de cada grupo, sorteia pra variar entre vídeos.
MUSIC_CATALOG = {
    "contemplative": [
        {"file": "ambiment.mp3", "name": "Ambiment"},
        {"file": "atlantean_twilight.mp3", "name": "Atlantean Twilight"},
        {"file": "airship_serenity.mp3", "name": "Airship Serenity"},
        {"file": "at_launch.mp3", "name": "At Launch"},
    ],
    "tense": [
        {"file": "arcane.mp3", "name": "Arcane"},
        {"file": "anxiety.mp3", "name": "Anxiety"},
    ],
}

# Termos (português, já que o roteiro é gerado nesse idioma na maioria dos
# canais) que indicam um tema mais intenso/extremo - cai pro grupo "tense"
# em vez do padrão "contemplative". Lista curta e deliberadamente
# conservadora: na dúvida, contemplativo combina com mais temas de ciência
# no geral do que uma trilha tensa.
_TENSE_KEYWORDS = [
    "buraco negro", "colisão", "colisao", "explosão", "explosao", "catástrofe",
    "catastrofe", "violento", "violenta", "destruição", "destruicao", "supernova",
    "apocalipse", "extremo", "extrema", "caos", "colapso",
]


def _pick_mood(topic: str, script: str) -> str:
    text = f"{topic} {script}".lower()
    return "tense" if any(kw in text for kw in _TENSE_KEYWORDS) else "contemplative"


def pick_track(topic: str, script: str) -> dict | None:
    """Escolhe uma faixa pro clima do roteiro. Retorna None se o catálogo
    local não tiver nenhum arquivo baixado (ex.: instalação nova que ainda
    não rodou scripts/download_music.py) - nesse caso o chamador segue sem
    música, igual ao comportamento de sempre antes dessa funcionalidade
    existir."""
    mood = _pick_mood(topic, script)
    candidates = [
        {**t, "path": MUSIC_DIR / t["file"]}
        for t in MUSIC_CATALOG.get(mood, [])
        if (MUSIC_DIR / t["file"]).exists()
    ]
    if not candidates:
        # Fallback pro outro grupo, caso só um dos dois tenha arquivos
        # presentes localmente.
        other_mood = "contemplative" if mood == "tense" else "tense"
        candidates = [
            {**t, "path": MUSIC_DIR / t["file"]}
            for t in MUSIC_CATALOG.get(other_mood, [])
            if (MUSIC_DIR / t["file"]).exists()
        ]
    if not candidates:
        return None
    return random.choice(candidates)


def _duck_to_narration(narration: AudioSegment, music: AudioSegment, duck_db: float) -> AudioSegment:
    """Abaixa `music` (já do mesmo tamanho de `narration`) especificamente
    nos trechos onde a narração está falando - detectados por
    detect_nonsilent, relativo ao volume médio da própria narração (robusto
    a vozes mais baixas/altas entre canais/vozes diferentes)."""
    speech_regions = detect_nonsilent(
        narration, min_silence_len=400, silence_thresh=narration.dBFS - 16
    )
    if not speech_regions:
        return music

    ducked = AudioSegment.silent(duration=0)
    pos = 0
    for start, end in speech_regions:
        if start > pos:
            ducked += music[pos:start]
        ducked += music[start:end] + duck_db
        pos = end
    if pos < len(music):
        ducked += music[pos:]
    return ducked


def add_background_music(narration_path: Path, output_path: Path, topic: str, script: str,
                          base_volume_db: float = -16, duck_db: float = -9) -> tuple[Path, str | None]:
    """Mistura a narração (inalterada, sempre em primeiro plano) com uma
    trilha de fundo com ducking automático. Se não achar nenhuma faixa
    local (catálogo vazio), devolve o áudio original sem alteração - nunca
    bloqueia a geração do vídeo por causa de música.

    Retorna (caminho_do_audio_final, texto_de_atribuição_ou_None) - a
    atribuição (quando houver) precisa ir pra descrição do vídeo, exigida
    pela licença CC BY das faixas do Kevin MacLeod."""
    track = pick_track(topic, script)
    if not track:
        return narration_path, None

    narration = AudioSegment.from_file(narration_path)
    music = AudioSegment.from_file(track["path"])

    if len(music) < len(narration):
        loops = len(narration) // len(music) + 1
        music = music * loops
    music = music[: len(narration)]
    music = (music + base_volume_db).fade_in(2000).fade_out(3000)

    ducked_music = _duck_to_narration(narration, music, duck_db)
    mixed = narration.overlay(ducked_music)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    mixed.export(output_path, format="mp3", bitrate="192k")

    attribution = ATTRIBUTION_TEMPLATE.format(name=track["name"])
    return output_path, attribution
