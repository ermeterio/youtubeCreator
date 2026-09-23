from pathlib import Path

from pydub import AudioSegment
from pydub.effects import normalize


def postprocess_audio(input_path: Path, output_path: Path,
                       fade_in_ms: int = 1500, fade_out_ms: int = 3000) -> Path:
    audio = AudioSegment.from_file(input_path)
    audio = normalize(audio)
    audio = audio.fade_in(fade_in_ms).fade_out(fade_out_ms)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    audio.export(output_path, format="mp3", bitrate="192k")
    return output_path
