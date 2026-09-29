"""Escrita atômica de arquivo (escreve num .partial, troca pro nome final só
depois de terminar com sucesso) - usado em todo lugar do pipeline que
escreve um arquivo cuja EXISTÊNCIA é depois usada como sinal de "já está
pronto" (checkpoint.json, cache de imagem, token OAuth, vídeo/thumbnail
final). Sem isso, uma interrupção no meio da escrita (queda de luz, processo
morto, rede caindo no meio de um download) deixa um arquivo truncado mas
EXISTENTE - o código que só checa `.exists()` trata isso como "válido" e
seguiria usando/resumindo com um arquivo corrompido, silenciosamente. Achado
via revisão de código real neste projeto (ver ROADMAP.md) - já corrigido
individualmente em video_build.py/thumbnail.py antes deste helper existir.
"""

from pathlib import Path


def _tmp_path(path: Path) -> Path:
    # Preserva a extensão real no final do nome temporário (ex.: "video.mp4"
    # -> "video.tmp.mp4", não "video.mp4.partial") - algumas bibliotecas
    # (ffmpeg/moviepy, entre outras) escolhem o formato de saída pela
    # extensão do NOME DO ARQUIVO, não por um parâmetro explícito; um nome
    # tipo "video.mp4.partial" quebra essa inferência. Bug real encontrado
    # em produção numa retomada de geração após reinício da máquina.
    return path.with_name(path.stem + ".tmp" + path.suffix)


def atomic_write_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = _tmp_path(path)
    tmp_path.write_bytes(data)
    tmp_path.replace(path)


def atomic_write_text(path: Path, text: str, encoding: str = "utf-8") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = _tmp_path(path)
    tmp_path.write_text(text, encoding=encoding)
    tmp_path.replace(path)
