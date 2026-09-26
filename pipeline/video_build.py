"""Monta o vídeo final: sequência de imagens (NASA/APOD) com efeito Ken Burns
(pan/zoom com aceleração suave) + crossfade entre cortes + narração + legendas
dinâmicas sincronizadas por palavra + crédito da fonte na tela (exigido pela
licença CC BY / uso da NASA) + título + chamada para inscrição nos segundos
finais.

Reaproveita a mesma paleta de cor do thumbnail (pipeline.thumbnail.palette_for,
por hash do título) nas legendas/crédito/flash/CTA para dar uma assinatura
visual consistente entre thumbnail e vídeo.
"""

from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont, ImageOps

from moviepy import (
    AudioFileClip,
    ColorClip,
    ImageClip,
    TextClip,
    CompositeVideoClip,
    concatenate_videoclips,
)
from moviepy.video.fx import CrossFadeIn, CrossFadeOut

import config
from pipeline.thumbnail import palette_for
from pipeline.visual_source import VisualAsset

CROSSFADE_DURATION = 0.35
TEXT_LINE_HEIGHT_FACTOR = 1.35  # ver _safe_text_clip: altura de canvas por linha de texto
OVERSIZE_FACTOR = 1.2  # margem extra pro Ken Burns não expor borda ao dar zoom
MAX_ZOOM = 0.12
MIN_ACCEPTABLE_SIDE = 1280  # abaixo disso a imagem não deve ocupar o quadro inteiro esticada
ASPECT_TOLERANCE = 0.35  # desvio relativo aceitável entre proporção da imagem e do quadro
FLASH_EVERY_N_CUTS = 3
CTA_DURATION = 3.5
CAPTION_MAX_WORDS = 4
CAPTION_MAX_CHARS = 28


def _text_line_width(text: str, font_path: str, font_size: int, stroke_width: int) -> int:
    img = Image.new("RGB", (1, 1))
    draw = ImageDraw.Draw(img)
    pil_font = ImageFont.truetype(font_path, font_size)
    left, _, right, _ = draw.textbbox((0, 0), text, font=pil_font, stroke_width=stroke_width)
    return right - left


def _safe_text_clip(text: str, font_path: str, font_size: int, stroke_width: int = 0,
                     max_width: int | None = None, align: str = "center", **kwargs):
    """TextClip com altura de canvas calculada na mão.

    O cálculo automático de altura do MoviePy 2.1.2 (method="caption" com
    size=(largura, None), e também method="label") subestima a altura
    necessária tanto pra texto com múltiplas linhas quanto pra uma linha só
    com stroke, cortando a parte de baixo/cima do texto renderizado - bug
    confirmado testando manualmente contra o pacote instalado. Em vez de
    confiar nesse cálculo, quebramos o texto nós mesmos (reaproveitando o
    quebrador de linha interno do MoviePy, que É confiável) e definimos uma
    altura generosa por linha.
    """
    if max_width is not None:
        lines = TextClip._TextClip__break_text(
            None, width=max_width, text=text, font=font_path, font_size=font_size,
            stroke_width=stroke_width, align=align, spacing=4,
        )
        canvas_width = max_width
    else:
        lines = [text]
        canvas_width = _text_line_width(text, font_path, font_size, stroke_width) + stroke_width * 4 + 8

    canvas_height = len(lines) * int(font_size * TEXT_LINE_HEIGHT_FACTOR) + stroke_width * 4 + 24

    return TextClip(text=text, font=font_path, font_size=font_size, method="caption",
                     size=(canvas_width, canvas_height), stroke_width=stroke_width,
                     text_align=align, **kwargs)


def _short_credit(credit: str, max_len: int = 40) -> str:
    # Créditos do ESA/Hubble às vezes incluem lista de pesquisadores e ficam
    # longos demais pra sobrepor no vídeo - trunca só para exibição na tela;
    # o crédito completo continua indo pra descrição do vídeo (orchestrator.py).
    return credit if len(credit) <= max_len else credit[:max_len - 1].rstrip() + "…"


def _needs_blur_fill(img_size: tuple[int, int], resolution: tuple[int, int]) -> bool:
    iw, ih = img_size
    w, h = resolution
    img_ratio = iw / ih
    target_ratio = w / h
    ratio_diff = abs(img_ratio - target_ratio) / target_ratio
    too_small = min(iw, ih) < MIN_ACCEPTABLE_SIDE
    return ratio_diff > ASPECT_TOLERANCE or too_small


def _blur_fill_canvas(img: Image.Image, size: tuple[int, int]) -> Image.Image:
    """Fundo desfocado/escurecido feito a partir da própria imagem (cobre o
    quadro todo sem cortar nada relevante) + a imagem original nítida,
    centralizada, em seu tamanho/proporção nativa. Evita tanto o upscaling
    borrado (imagem pequena esticada pro quadro) quanto o crop agressivo
    (imagem com proporção muito diferente do quadro, ex.: panorâmicas)."""
    bg = ImageOps.fit(img, size, method=Image.LANCZOS)
    bg = bg.filter(ImageFilter.GaussianBlur(40))
    bg = ImageEnhance.Brightness(bg).enhance(0.45)

    fg = ImageOps.contain(img, size, method=Image.LANCZOS)
    canvas = bg.copy()
    canvas.paste(fg, ((size[0] - fg.width) // 2, (size[1] - fg.height) // 2))
    return canvas


def _compose_canvas(asset: VisualAsset, resolution: tuple[int, int]) -> np.ndarray:
    w, h = resolution
    canvas_size = (int(w * OVERSIZE_FACTOR), int(h * OVERSIZE_FACTOR))
    img = Image.open(asset.local_path).convert("RGB")

    if _needs_blur_fill(img.size, resolution):
        canvas = _blur_fill_canvas(img, canvas_size)
    else:
        canvas = ImageOps.fit(img, canvas_size, method=Image.LANCZOS)

    return np.array(canvas)


def _ease_in_out(t: float) -> float:
    return t * t * (3 - 2 * t)


def _ken_burns_clip(asset: VisualAsset, duration: float, resolution: tuple[int, int],
                     zoom_in: bool, credit_color: tuple[int, int, int], credit_label: str = "Crédito"):
    w, h = resolution
    frame = _compose_canvas(asset, resolution)

    def scale_at(t):
        progress = _ease_in_out(min(t / duration, 1.0))
        return (1 + MAX_ZOOM * progress) if zoom_in else (1 + MAX_ZOOM * (1 - progress))

    clip = (
        ImageClip(frame)
        .resized(scale_at)
        .with_duration(duration)
        .with_position(("center", "center"))
    )

    credit = (
        _safe_text_clip(f"{credit_label}: {_short_credit(asset.credit)}", config.FONT_CREDIT, 28,
                        stroke_width=1, color="white", stroke_color="black",
                        bg_color=credit_color + (120,))
        .with_position((0.02, 0.94), relative=True)
        .with_duration(duration)
    )

    return CompositeVideoClip([clip, credit], size=(w, h))


def _group_captions(boundaries: list[dict], max_words: int = CAPTION_MAX_WORDS,
                     max_chars: int = CAPTION_MAX_CHARS) -> list[dict]:
    """Agrupa os eventos WordBoundary do TTS em blocos curtos de legenda
    (estilo Shorts: texto grande, poucas palavras por vez, sincronizado)."""
    groups: list[list[dict]] = []
    current: list[dict] = []
    for word in boundaries:
        current.append(word)
        joined = " ".join(w["text"] for w in current)
        ends_sentence = word["text"].rstrip().endswith((".", "?", "!", ","))
        if len(current) >= max_words or len(joined) >= max_chars or ends_sentence:
            groups.append(current)
            current = []
    if current:
        groups.append(current)

    captions = []
    for group in groups:
        captions.append({
            "text": " ".join(w["text"] for w in group),
            "start": group[0]["start"],
            "end": group[-1]["start"] + group[-1]["duration"],
        })
    return captions


def _caption_clips(boundaries: list[dict], resolution: tuple[int, int],
                    accent_color: tuple[int, int, int]):
    w, h = resolution
    clips = []
    for cap in _group_captions(boundaries):
        cap_duration = max(cap["end"] - cap["start"], 0.05)
        clip = (
            _safe_text_clip(cap["text"].upper(), config.FONT_CAPTION, int(h * 0.045),
                            stroke_width=2, max_width=int(w * 0.9), color="white",
                            stroke_color="black", bg_color=(0, 0, 0, 110))
            .with_position(("center", 0.76), relative=True)
            .with_start(cap["start"])
            .with_duration(cap_duration)
        )
        clips.append(clip)
    return clips


def _flash_clips(cut_times: list[float], resolution: tuple[int, int],
                  flash_color: tuple[int, int, int]):
    flashes = []
    for idx, t in enumerate(cut_times):
        if (idx + 1) % FLASH_EVERY_N_CUTS != 0:
            continue
        flash = (
            ColorClip(size=resolution, color=flash_color)
            .with_duration(0.09)
            .with_start(max(0.0, t - 0.045))
            .with_effects([CrossFadeIn(0.03), CrossFadeOut(0.03)])
            .with_opacity(0.5)
        )
        flashes.append(flash)
    return flashes


def _cta_clip(total_duration: float, resolution: tuple[int, int],
              accent_color: tuple[int, int, int], cta_text: str = "Inscreva-se no canal →"):
    w, h = resolution
    cta_duration = min(CTA_DURATION, total_duration)
    start = max(0.0, total_duration - cta_duration)

    def pulse(t):
        return 1 + 0.05 * abs(((t * 2) % 1) - 0.5)

    return (
        _safe_text_clip(cta_text, config.FONT_CTA, int(h * 0.032),
                        color="white", bg_color=accent_color + (210,))
        .resized(pulse)
        .with_position(("center", 0.90), relative=True)
        .with_start(start)
        .with_duration(cta_duration)
        .with_effects([CrossFadeIn(0.4)])
    )


def build_video(narration_path: Path, title: str, assets: list[VisualAsset], output_path: Path,
                 vertical: bool = False, captions: list[dict] | None = None,
                 credit_label: str = "Crédito", cta_text: str = "Inscreva-se no canal →") -> Path:
    """Monta o vídeo (horizontal ou vertical/Short) cobrindo a narração
    INTEIRA, sempre - nunca corta o roteiro pra caber num tempo fixo
    (relatado como problema real: um Short com duração limitada cortava o
    fim do texto). Se o roteiro for longo, o vídeo fica mais longo; a
    prioridade é manter o conteúdo completo e informativo."""
    if not assets:
        raise ValueError("Nenhuma imagem disponível para montar o vídeo.")

    resolution = (1080, 1920) if vertical else config.VIDEO_RESOLUTION
    w, h = resolution
    bg_color, accent_color = palette_for(title)

    audio = AudioFileClip(str(narration_path))
    duration = audio.duration
    n = len(assets)
    # cada crossfade "come" CROSSFADE_DURATION da duração total da sequência
    # (os clipes se sobrepõem); compensa aqui pra sequência final bater com o
    # áudio exatamente quando não bate no piso mínimo de 4s por imagem.
    per_image_duration = max((duration + (n - 1) * CROSSFADE_DURATION) / n, 4.0)

    clips = []
    for i, asset in enumerate(assets):
        clip = _ken_burns_clip(asset, per_image_duration, resolution, zoom_in=(i % 2 == 0),
                                credit_color=bg_color, credit_label=credit_label)
        effects = []
        if i > 0:
            effects.append(CrossFadeIn(CROSSFADE_DURATION))
        if i < len(assets) - 1:
            effects.append(CrossFadeOut(CROSSFADE_DURATION))
        if effects:
            clip = clip.with_effects(effects)
        clips.append(clip)

    sequence = concatenate_videoclips(clips, method="compose", padding=-CROSSFADE_DURATION)
    sequence = sequence.subclipped(0, duration).with_audio(audio)

    title_clip = (
        _safe_text_clip(title, config.FONT_TITLE, 54 if vertical else 60, stroke_width=2,
                        max_width=int(w * 0.85), color="white", stroke_color="black")
        .with_position(("center", 0.08), relative=True)
        .with_duration(min(6, duration))
    )

    step = per_image_duration - CROSSFADE_DURATION
    cut_times = [i * step for i in range(1, len(assets))]

    layers = [sequence, title_clip]
    layers += _flash_clips(cut_times, resolution, bg_color)
    if captions:
        layers += _caption_clips(captions, resolution, accent_color)
    layers.append(_cta_clip(duration, resolution, bg_color, cta_text=cta_text))

    final = CompositeVideoClip(layers, size=(w, h)).subclipped(0, duration)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    # Escreve num arquivo temporário e só troca pro nome final DEPOIS do
    # encode terminar com sucesso - orchestrator.py decide se retoma ou pula
    # uma etapa só checando se o arquivo final existe, então uma escrita
    # direta no nome final deixaria um vídeo TRUNCADO mas EXISTENTE se o
    # processo morresse no meio do encode (queda de luz, restart, OOM do
    # ffmpeg) - a próxima execução acharia "já pronto" e seguiria pro upload
    # de um vídeo corrompido, sem erro nenhum. Rename é atômico no mesmo
    # sistema de arquivos (mesma pasta aqui), então video.mp4 só existe de
    # verdade quando está 100% completo.
    tmp_path = output_path.with_suffix(output_path.suffix + ".partial")
    final.write_videofile(
        str(tmp_path),
        fps=config.VIDEO_FPS,
        codec="libx264",
        audio_codec="aac",
        threads=4,
    )
    tmp_path.replace(output_path)
    return output_path
