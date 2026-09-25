"""Gera uma thumbnail estática (YouTube não aceita thumbnail animada custom,
só imagem estática) a partir da melhor imagem NASA do vídeo + título + crédito.

A paleta do overlay varia por título (hash) para as thumbnails não ficarem
idênticas entre vídeos.
"""

import hashlib
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

import config
from pipeline.visual_source import VisualAsset

THUMB_SIZE = (1280, 720)

PALETTES = [
    ((200, 30, 30), (255, 255, 255)),
    ((30, 60, 200), (255, 255, 255)),
    ((20, 20, 20), (255, 200, 0)),
    ((120, 20, 140), (255, 255, 255)),
    ((30, 130, 90), (255, 255, 255)),
]


def palette_for(title: str):
    """Escolhe uma das paletas fixas a partir de um hash do título - determinístico
    (o mesmo título sempre cai na mesma paleta) e usado também no vídeo (legendas,
    caixa de crédito, flash de transição) para dar uma assinatura visual consistente
    entre thumbnail e vídeo."""
    idx = int(hashlib.sha256(title.encode("utf-8")).hexdigest(), 16) % len(PALETTES)
    return PALETTES[idx]


def build_thumbnail(main_asset: VisualAsset, title: str, output_path: Path,
                     font_path: str | None = None, credit_label: str = "Crédito",
                     palette_offset: int = 0) -> Path:
    bg_color, text_color = palette_for(title)
    if palette_offset:
        idx = (PALETTES.index((bg_color, text_color)) + palette_offset) % len(PALETTES)
        bg_color, text_color = PALETTES[idx]

    base = Image.open(main_asset.local_path).convert("RGBA").resize(THUMB_SIZE)
    overlay = Image.new("RGBA", THUMB_SIZE, bg_color + (90,))
    base = Image.alpha_composite(base, overlay)

    draw = ImageDraw.Draw(base)
    try:
        font = ImageFont.truetype(font_path or config.FONT_TITLE, 80)
        credit_font = ImageFont.truetype(config.FONT_CREDIT, 30)
    except OSError:
        font = ImageFont.load_default()
        credit_font = font

    # título quebrado em linhas simples para caber na largura
    words = title.split()
    lines, current = [], ""
    for word in words:
        trial = f"{current} {word}".strip()
        if draw.textlength(trial, font=font) > THUMB_SIZE[0] - 80:
            lines.append(current)
            current = word
        else:
            current = trial
    lines.append(current)

    total_h = sum(draw.textbbox((0, 0), line, font=font)[3] for line in lines) + 20 * len(lines)
    y = (THUMB_SIZE[1] - total_h) / 2
    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=font)
        w = bbox[2] - bbox[0]
        draw.text(((THUMB_SIZE[0] - w) / 2, y), line, font=font, fill=text_color)
        y += (bbox[3] - bbox[1]) + 20

    credit_display = main_asset.credit if len(main_asset.credit) <= 45 else main_asset.credit[:44].rstrip() + "…"
    draw.text((20, THUMB_SIZE[1] - 45), f"{credit_label}: {credit_display}",
              font=credit_font, fill=(255, 255, 255))

    output_path.parent.mkdir(parents=True, exist_ok=True)
    base.convert("RGB").save(output_path, "JPEG", quality=90)
    return output_path
