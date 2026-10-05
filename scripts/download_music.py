"""Baixa o catálogo de trilhas sonoras de fundo (ver pipeline/music.py) pra
data/assets/music/ - roda uma vez por instalação (os arquivos de áudio não
vão pro git, só esse script de setup). Sem internet/falha de download, o
pipeline segue funcionando normalmente sem música (ver music.add_background_
music - fail-open quando o catálogo local está vazio).

Faixas de Kevin MacLeod (incompetech.com), licença CC BY 3.0 - uso
comercial/monetizado permitido, exige atribuição (já incluída
automaticamente na descrição do vídeo quando a faixa é usada, ver
pipeline/music.ATTRIBUTION_TEMPLATE). URLs validadas por download real em
05/10/2026.

Uso: .venv\\Scripts\\python.exe scripts\\download_music.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import requests  # noqa: E402

import config  # noqa: E402

TRACKS = {
    "ambiment.mp3": "https://incompetech.com/music/royalty-free/mp3-royaltyfree/Ambiment.mp3",
    "atlantean_twilight.mp3": "https://incompetech.com/music/royalty-free/mp3-royaltyfree/Atlantean%20Twilight.mp3",
    "airship_serenity.mp3": "https://incompetech.com/music/royalty-free/mp3-royaltyfree/Airship%20Serenity.mp3",
    "at_launch.mp3": "https://incompetech.com/music/royalty-free/mp3-royaltyfree/At%20Launch.mp3",
    "arcane.mp3": "https://incompetech.com/music/royalty-free/mp3-royaltyfree/Arcane.mp3",
    "anxiety.mp3": "https://incompetech.com/music/royalty-free/mp3-royaltyfree/Anxiety.mp3",
}


def main() -> None:
    music_dir = config.ASSETS_DIR / "music"
    music_dir.mkdir(parents=True, exist_ok=True)

    for filename, url in TRACKS.items():
        dest = music_dir / filename
        if dest.exists():
            print(f"já existe: {filename}")
            continue
        try:
            response = requests.get(url, timeout=120, headers={"User-Agent": "Mozilla/5.0"})
            response.raise_for_status()
            if len(response.content) < 10_000:
                print(f"FALHOU (resposta pequena demais, provável erro): {filename}")
                continue
            dest.write_bytes(response.content)
            print(f"baixado: {filename} ({len(response.content) // 1024} KB)")
        except Exception as exc:
            print(f"FALHOU: {filename} - {exc}")

    print("\nPronto. O pipeline usa automaticamente o que estiver em data/assets/music/.")


if __name__ == "__main__":
    main()
