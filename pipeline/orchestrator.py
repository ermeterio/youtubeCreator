"""Pipeline de canais automatizados (multi-conta - ver pipeline.channels).

Dividido em duas etapas propositalmente:

1. `prepare_daily_video(channel_id)` - roda sozinho (agendado 1x/dia por
   canal): busca tema real (APOD ou tema rotativo do canal), gera roteiro,
   narra, monta vídeo e thumbnail. Termina com o vídeo em status
   'pending_review', NÃO publica.

2. `approve_and_upload(track_id)` - você roda manualmente depois de ler o
   roteiro/assistir o vídeo gerado. É essa revisão humana curta (ler o texto,
   confirmar que os fatos citados batem com a fonte, opcionalmente editar)
   que caracteriza "decisão editorial humana" perante a política de conteúdo
   do YouTube - pular essa etapa tira exatamente a proteção que ela existe
   para dar. Vídeos com fact_check_flag='atencao' merecem uma conferida
   extra antes de aprovar.
"""

import json
from datetime import datetime, timezone
from pathlib import Path

import config
from pipeline import audio_post, backup, catalog, channels, narration, notify, script_gen, thumbnail, video_build, visual_source, youtube_upload

# Status em que o track já passou por roteiro+imagens+narração (a parte cara:
# chamadas ao Ollama, busca de imagem, TTS) mas ainda não terminou a
# montagem de vídeo - se o processo cair no meio (falha de render, queda de
# energia, etc.), a próxima execução retoma daqui em vez de regerar tudo.
_RESUMABLE_STATUSES = ("narration_ready", "video_ready")


def _checkpoint_path(work_dir: Path) -> Path:
    return work_dir / "checkpoint.json"


def _save_checkpoint(work_dir: Path, assets: list, boundaries: list[dict]) -> None:
    data = {
        "assets": [{"local_path": str(a.local_path), "credit": a.credit, "title": a.title} for a in assets],
        "boundaries": boundaries,
    }
    _checkpoint_path(work_dir).write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def _load_checkpoint(work_dir: Path) -> dict | None:
    path = _checkpoint_path(work_dir)
    if not path.exists():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    assets = [
        visual_source.VisualAsset(local_path=Path(a["local_path"]), credit=a["credit"], title=a["title"])
        for a in data["assets"]
    ]
    return {"assets": assets, "boundaries": data["boundaries"]}


def _find_resumable_track(channel_id: int):
    """Track mais recente desse canal que já tem roteiro+narração prontos
    mas não chegou a 'pending_review' - candidato a retomar em vez de
    recomeçar do zero. None se não houver nenhum (caso normal)."""
    for track in catalog.list_tracks(channel_id=channel_id, limit=5):
        if track["status"] in _RESUMABLE_STATUSES and track["narration_path"]:
            work_dir = Path(track["narration_path"]).parent
            if _checkpoint_path(work_dir).exists():
                return track
    return None


def _build_tags(channel, track) -> list[str]:
    niche_words = [w.strip().lower() for w in (channel["niche"] or "").replace("/", ",").split(",") if w.strip()]
    topic_words = [w for w in track["topic"].lower().replace("-", " ").split() if len(w) > 3]
    series_tag = (track["series"] or "").lower().replace(" ", "")
    tags = niche_words + topic_words[:6] + ([series_tag] if series_tag else [])
    # remove duplicados preservando ordem, YouTube aceita até 500 caracteres somados
    seen = set()
    unique_tags = []
    for tag in tags:
        if tag and tag not in seen:
            seen.add(tag)
            unique_tags.append(tag)
    return unique_tags[:15]


def _build_description(topic: str, script: str, credits: list[str]) -> str:
    credit_line = ", ".join(sorted(set(credits))) or "NASA"
    return (
        f"Vídeo original sobre {topic}, com narração e roteiro gerados com apoio de IA "
        f"a partir de dados públicos da NASA, com revisão humana antes da publicação.\n\n"
        f"Imagens: {credit_line}.\n\n"
        f"Conteúdo alterado/sintético: roteiro e narração gerados por inteligência artificial."
    )


def prepare_daily_video(channel_id: int | None = None, forced_topic: tuple[str, str] | None = None) -> int:
    catalog.init_db()
    channel = channels.get_channel(channel_id) if channel_id else channels.ensure_default_channel()

    # Pedido sob demanda com tema específico é sempre uma execução nova - não
    # faz sentido "retomar" um outro track incompleto e ignorar o tema pedido.
    resumable = None if forced_topic else _find_resumable_track(channel["id"])
    if resumable:
        track_id = resumable["id"]
        title, script, topic, fact_check = resumable["title"], resumable["script"], resumable["topic"], resumable["fact_check_flag"]
        work_dir = Path(resumable["narration_path"]).parent
        checkpoint = _load_checkpoint(work_dir)
        assets, boundaries = checkpoint["assets"], checkpoint["boundaries"]
        narration_path = Path(resumable["narration_path"])
        print(f"[canal {channel['name']} | track {track_id}] retomando execução incompleta (estava em '{resumable['status']}').")
    else:
        result = script_gen.build_daily_script(channel, forced_topic=forced_topic)
        script, topic, assets = result["script"], result["topic"], result["visual_assets"]
        fact_check, series = result["fact_check"], result["series"]
        title = f"{series} | {result['title']}"

        if not assets:
            raise RuntimeError(
                f"Nenhuma imagem encontrada para o tema '{topic}'. Ajuste os temas do canal "
                f"'{channel['name']}' ou tente novamente (a API da NASA pode falhar às vezes)."
            )

        credits = [asset.credit for asset in assets]
        track_id = catalog.create_track(title, topic, script, ", ".join(credits), channel_id=channel["id"])
        catalog.update_track(track_id, fact_check_flag=fact_check, series=series)

        # Segunda passada do LLM simulando um espectador leigo - sinaliza
        # trechos confusos/redundantes ANTES da revisão humana, sem travar o
        # pipeline se o Ollama não responder.
        try:
            clarity = script_gen.clarity_review(script, channel["niche"] or "ciência")
            if clarity:
                catalog.update_track(track_id, clarity_review=clarity)
        except Exception:
            pass

        stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        work_dir = channels.output_dir(channel["slug"]) / f"{stamp}_{track_id}"

        raw_narration_path = work_dir / "narration_raw.mp3"
        narration_path = work_dir / "narration.mp3"
        voice = channels.narration_voice_for(channel)
        _, boundaries = narration.generate_narration_with_boundaries(script, raw_narration_path, voice=voice)
        audio_post.postprocess_audio(raw_narration_path, narration_path)
        catalog.update_track(track_id, narration_path=str(narration_path), status="narration_ready")
        # Guarda imagens+legendas em disco ANTES de montar vídeo - é a parte
        # cara (Ollama, busca de imagem, TTS) que não vale a pena regerar se
        # a montagem falhar no meio; a próxima execução retoma daqui.
        _save_checkpoint(work_dir, assets, boundaries)

    language = channels.language_for(channel)

    video_path = work_dir / "video.mp4"
    if not video_path.exists():
        video_build.build_video(narration_path, title, assets, video_path, captions=boundaries,
                                 credit_label=language["credit_label"], cta_text=language["cta_text"])
        catalog.update_track(track_id, video_path=str(video_path), status="video_ready")

    # Short = RECORTE do vídeo longo (mesmo roteiro/narração/Ken Burns até o
    # ponto de corte, reenquadrado em 9:16), não uma renderização paralela
    # desconectada - relação editorial clara com o vídeo longo, que é o que a
    # política do YouTube (2026) trata como uso legítimo de Shorts (ver
    # ROADMAP.md). O gate de revisão humana continua valendo, ver
    # approve_and_upload_short().
    short_path = work_dir / "short.mp4"
    if not short_path.exists():
        video_build.build_video(narration_path, title, assets, short_path, vertical=True, captions=boundaries,
                                 credit_label=language["credit_label"], cta_text=language["cta_text"],
                                 max_duration=config.SHORT_MAX_DURATION_SECONDS)
        catalog.update_track(track_id, video_vertical_path=str(short_path))

    thumb_path = work_dir / "thumbnail.jpg"
    if not thumb_path.exists():
        thumbnail.build_thumbnail(assets[0], title, thumb_path, credit_label=language["credit_label"])
    catalog.update_track(track_id, thumbnail_path=str(thumb_path), status="pending_review")

    print(f"[canal {channel['name']} | track {track_id}] pronto para revisão.")
    print(f"  Título: {title}")
    if fact_check == "atencao":
        print("  ATENCAO: fact-check automático sinalizou afirmação(oes) sem fonte rastreável - revise com cuidado.")
    print(f"  Roteiro:\n{script}\n")
    print(f"  Vídeo: {video_path}")
    print(f"  Short (vertical): {short_path}")
    print(f"  Thumbnail: {thumb_path}")
    print(f"Revise e rode: approve_and_upload({track_id}) para publicar o vídeo,")
    print(f"e approve_and_upload_short({track_id}) para publicar o Short.")

    return track_id


def run_all_active_channels() -> list[int]:
    """Roda prepare_daily_video() para todos os canais ativos - usado pelo
    agendamento diário (ver scripts/run_daily.py) pra gerar o vídeo do dia de
    cada canal cadastrado em sequência."""
    catalog.init_db()
    backup.backup_catalog()

    try:
        from pipeline import health
        health.check_channels_health()
    except Exception as exc:
        notify.log(f"Checagem de saúde dos canais falhou (não bloqueia a geração): {exc}")

    track_ids = []
    for channel in channels.list_channels(active_only=True):
        try:
            track_id = prepare_daily_video(channel["id"])
            track_ids.append(track_id)
            notify.log(f"[{channel['name']}] track {track_id} pronto para revisão.")
        except Exception as exc:
            print(f"[canal {channel['name']}] FALHOU: {exc}")
            notify.log(f"[{channel['name']}] FALHOU: {exc}")
    return track_ids


def approve_and_upload(track_id: int, privacy_status: str = "private") -> str:
    track = catalog.get_track(track_id)
    if track["status"] != "pending_review":
        raise RuntimeError(f"Track {track_id} não está com status 'pending_review' (está '{track['status']}').")

    channel = channels.get_channel(track["channel_id"])
    credits = track["image_credits"].split(", ") if track["image_credits"] else ["NASA"]
    description = _build_description(track["topic"], track["script"], credits)
    tags = _build_tags(channel, track)

    video_id = youtube_upload.upload_video(
        track["video_path"], track["title"], description, tags,
        client_secret_path=channels.client_secret_path(channel["slug"]),
        token_path=channels.token_path(channel["slug"]),
        thumbnail_path=track["thumbnail_path"], privacy_status=privacy_status,
    )
    catalog.update_track(track_id, youtube_video_id=video_id, status="uploaded")
    return video_id


def approve_and_upload_short(track_id: int, privacy_status: str = "private") -> str:
    """Publica a versão vertical (Shorts) do mesmo track. Independente de
    approve_and_upload() - pode ser chamada antes, depois, ou nunca, sem
    afetar o status do vídeo horizontal."""
    track = catalog.get_track(track_id)
    if not track["video_vertical_path"]:
        raise RuntimeError(f"Track {track_id} não tem versão vertical (Shorts) gerada.")
    if track["status"] not in ("pending_review", "video_ready", "uploaded"):
        raise RuntimeError(f"Track {track_id} ainda não passou pela etapa de montagem (status '{track['status']}').")

    channel = channels.get_channel(track["channel_id"])
    credits = track["image_credits"].split(", ") if track["image_credits"] else ["NASA"]
    description = _build_description(track["topic"], track["script"], credits)
    tags = _build_tags(channel, track) + ["shorts"]
    short_title = track["title"] if "#shorts" in track["title"].lower() else f"{track['title']} #Shorts"

    video_id = youtube_upload.upload_video(
        track["video_vertical_path"], short_title, description, tags,
        client_secret_path=channels.client_secret_path(channel["slug"]),
        token_path=channels.token_path(channel["slug"]),
        thumbnail_path=None, privacy_status=privacy_status,
    )
    catalog.update_track(track_id, youtube_short_video_id=video_id)
    return video_id


if __name__ == "__main__":
    run_all_active_channels()
