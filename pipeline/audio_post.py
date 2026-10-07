import subprocess
from pathlib import Path

import imageio_ffmpeg
from pydub import AudioSegment
from pydub.effects import normalize

# Alvo padrão do YouTube pra normalização interna de loudness - usado como
# referência em várias fontes de 2026 (vidIQ, guias de mixagem pra
# streaming). Se o áudio chegar muito diferente disso, o YouTube aplica seu
# PRÓPRIO ganho depois do upload, o que pode mascarar a trilha de fundo com
# ducking cuidadoso (ver pipeline/music.py) de um jeito imprevisível - daí
# a normalização de loudness (não só de pico) ser o alvo certo.
YOUTUBE_TARGET_LUFS = -14.0


def postprocess_audio(input_path: Path, output_path: Path,
                       fade_in_ms: int = 1500, fade_out_ms: int = 0) -> Path:
    """Preparo da narração SECA, antes de qualquer trilha de fundo ser
    misturada - normalização de PICO aqui é só segurança contra clipping
    quando a música for somada por cima depois, não é a normalização que
    importa pro resultado final (ver normalize_loudness, que mede/ajusta
    a MISTURA final, depois do ducking)."""
    audio = AudioSegment.from_file(input_path)
    audio = normalize(audio)
    audio = audio.fade_in(fade_in_ms)
    if fade_out_ms:
        audio = audio.fade_out(fade_out_ms)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    audio.export(output_path, format="mp3", bitrate="192k")
    return output_path


def normalize_loudness(input_path: Path, output_path: Path,
                        target_lufs: float = YOUTUBE_TARGET_LUFS,
                        true_peak: float = -1.5, lra: float = 11.0) -> Path:
    """Normaliza pra loudness PERCEBIDA (EBU R128/LUFS, filtro `loudnorm`
    do ffmpeg), não só o pico mais alto não clipar (que é tudo que
    pydub.effects.normalize faz). Rodar isso DEPOIS da trilha de fundo
    misturada (não antes) é o que importa - é a mistura final que o
    YouTube vai medir e possivelmente re-normalizar.

    Usa o MESMO binário ffmpeg que o moviepy já usa (via imageio_ffmpeg) -
    zero dependência nova. single-pass (não mede antes de aplicar) - menos
    preciso que two-pass, mas significativamente mais simples e rápido, e
    já corrige o desvio que importa aqui (pico vs. loudness percebida)."""
    ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        ffmpeg_exe, "-y", "-i", str(input_path),
        "-af", f"loudnorm=I={target_lufs}:TP={true_peak}:LRA={lra}",
        "-ar", "44100", "-b:a", "192k", str(output_path),
    ]
    subprocess.run(cmd, check=True, capture_output=True)
    return output_path
