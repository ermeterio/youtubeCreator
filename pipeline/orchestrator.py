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
from datetime import date, datetime, timezone
from pathlib import Path

import config
from pipeline import atomic_io, audio_post, backup, captions_export, catalog, chapters, channels, music, narration, notify, script_gen, semantic, thumbnail, video_build, visual_source, youtube_upload

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
    atomic_io.atomic_write_text(_checkpoint_path(work_dir), json.dumps(data, ensure_ascii=False))


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


def _build_description(topic: str, script: str, credits: list[str], music_credit: str | None = None,
                        related_video_url: str | None = None, related_label: str | None = None,
                        chapters_text: str | None = None) -> str:
    credit_line = ", ".join(sorted(set(credits))) or "NASA"
    description = (
        f"Vídeo original sobre {topic}, com narração e roteiro gerados com apoio de IA "
        f"a partir de dados públicos da NASA, com revisão humana antes da publicação."
    )
    # Capítulos (YouTube Chapters) - logo após a 1ª linha, ANTES de qualquer
    # outro texto com formato de timestamp (não que exista aqui, mas por
    # segurança): a regra do YouTube é que o PRIMEIRO timestamp encontrado
    # na descrição precisa ser "0:00" pra ativar os capítulos - colocar
    # cedo evita qualquer ambiguidade (ver pipeline/chapters.py).
    if chapters_text:
        description += f"\n\n{chapters_text}"
    description += (
        f"\n\nImagens: {credit_line}.\n\n"
        f"Conteúdo alterado/sintético: roteiro e narração gerados por inteligência artificial."
    )
    if music_credit:
        description += f"\n\nMúsica:\n{music_credit}"
    # Cross-link Short<->vídeo longo (prática validada: YouTube distribui
    # melhor quando os dois formatos do mesmo conteúdo se referenciam -
    # ver orchestrator.approve_and_upload/approve_and_upload_short).
    if related_video_url and related_label:
        description += f"\n\n{related_label}: {related_video_url}"
    return description


def prepare_daily_video(channel_id: int | None = None, forced_topic: tuple[str, str] | None = None,
                         forced_voice: str | None = None) -> int:
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
        fact_check_details = result.get("fact_check_details")
        title = f"{series} | {result['title']}"

        if not assets:
            raise RuntimeError(
                f"Nenhuma imagem encontrada para o tema '{topic}'. Ajuste os temas do canal "
                f"'{channel['name']}' ou tente novamente (a API da NASA pode falhar às vezes)."
            )

        credits = [asset.credit for asset in assets]
        track_id = catalog.create_track(title, topic, script, ", ".join(credits), channel_id=channel["id"])
        catalog.update_track(track_id, fact_check_flag=fact_check, fact_check_details=fact_check_details, series=series)

        # Segunda passada do LLM simulando um espectador leigo - sinaliza
        # trechos confusos/redundantes ANTES da revisão humana, sem travar o
        # pipeline se o Ollama não responder.
        clarity = None
        try:
            clarity = script_gen.clarity_review(script, channel["niche"] or "ciência")
            if clarity:
                catalog.update_track(track_id, clarity_review=clarity)
        except Exception:
            pass

        # Score agregado (fatos + clareza + relevância de imagem + diversidade
        # vs vídeos recentes do canal) - resumo rápido pro revisor, calculado
        # após os outros sinais estarem prontos. Não bloqueia se falhar.
        try:
            recent_titles = [t for t in catalog.recent_titles(channel["id"], limit=20) if t != title]
            repetition_score = semantic.max_similarity(title, recent_titles)
            score, breakdown = script_gen.compute_quality_score(
                fact_check, clarity, assets, result.get("image_search_terms") or topic,
                repetition_score=repetition_score
            )
            catalog.update_track(track_id, quality_score=score, quality_breakdown=breakdown)
        except Exception:
            pass

        stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        work_dir = channels.output_dir(channel["slug"]) / f"{stamp}_{track_id}"

        raw_narration_path = work_dir / "narration_raw.mp3"
        narration_path = work_dir / "narration.mp3"
        voice = forced_voice or channels.narration_voice_for(channel)
        rate = channels.narration_rate_for(channel)
        pitch = channels.narration_pitch_for(channel)
        _, boundaries = narration.generate_narration_for_channel(
            script, raw_narration_path, channel, voice=voice, rate=rate, pitch=pitch
        )
        audio_post.postprocess_audio(raw_narration_path, narration_path)

        # Trilha sonora de fundo com ducking automático (ver pipeline/music.py)
        # - só muda algo se houver faixas locais baixadas (scripts/
        # download_music.py); senão segue sem música, como sempre funcionou.
        # Sobrescreve narration_path com a versão mixada, que é o que de fato
        # vira a trilha de áudio do vídeo final.
        music_credit = None
        try:
            narration_with_music_path = work_dir / "narration_with_music.mp3"
            narration_path, music_credit = music.add_background_music(
                narration_path, narration_with_music_path, topic, script
            )
        except Exception as exc:
            notify.log(f"[{channel['name']}] Trilha sonora falhou (não bloqueia a geração): {exc}")

        # Normalização de LOUDNESS (não só pico) na mistura FINAL - depois
        # da música/ducking, que é o que importa pro YouTube não re-
        # normalizar o áudio do jeito dele depois do upload (ver
        # audio_post.normalize_loudness). Best-effort: se o ffmpeg falhar
        # por qualquer motivo, segue com o áudio de antes (música+ducking,
        # ou só a narração se a música também tiver falhado).
        try:
            loudness_path = work_dir / "narration_loudnorm.mp3"
            audio_post.normalize_loudness(narration_path, loudness_path)
            narration_path = loudness_path
        except Exception as exc:
            notify.log(f"[{channel['name']}] Normalização de loudness falhou (não bloqueia a geração): {exc}")

        # Capítulos (YouTube Chapters) - calculados aqui, com o timing por
        # palavra fresco, e guardados prontos pra descrição (ver
        # pipeline/chapters.py). Sem LLM novo, só formatação; None se o
        # roteiro não render capítulos válidos (curto demais etc.).
        built_chapters = chapters.build_chapters(script, boundaries)
        chapters_text = chapters.format_chapters_for_description(built_chapters) if built_chapters else None

        catalog.update_track(
            track_id, narration_path=str(narration_path), status="narration_ready",
            music_attribution=music_credit, chapters_text=chapters_text,
        )
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

    # Short = mesma narração/roteiro/Ken Burns completos, só reenquadrado em
    # 9:16 - NUNCA corta o texto/narração pra caber num tempo fixo (relatado
    # como problema real: um roteiro de 94s ficava com o fim cortado quando
    # o Short era limitado a 58s). Prioridade é manter o conteúdo completo e
    # informativo mesmo que isso deixe o Short mais longo que o "padrão" de
    # Shorts curtos - correto é o vídeo caber o conteúdo, não o contrário.
    short_path = work_dir / "short.mp4"
    if not short_path.exists():
        video_build.build_video(narration_path, title, assets, short_path, vertical=True, captions=boundaries,
                                 credit_label=language["credit_label"], cta_text=language["cta_text"])
        catalog.update_track(track_id, video_vertical_path=str(short_path))

    thumb_path = work_dir / "thumbnail.jpg"
    if not thumb_path.exists():
        thumbnail.build_thumbnail(assets[0], title, thumb_path, credit_label=language["credit_label"])
    # Variante B pro teste A/B de thumbnail (ver health.run_thumbnail_ab_tests):
    # imagem diferente (a 2ª melhor, se houver) + paleta deslocada, pra ser
    # visualmente distinta de verdade, não só um filtro sutil.
    thumb_b_path = work_dir / "thumbnail_b.jpg"
    if not thumb_b_path.exists():
        alt_asset = assets[1] if len(assets) > 1 else assets[0]
        thumbnail.build_thumbnail(alt_asset, title, thumb_b_path, credit_label=language["credit_label"],
                                   palette_offset=1)
    catalog.update_track(track_id, thumbnail_path=str(thumb_path), thumbnail_b_path=str(thumb_b_path),
                          status="pending_review")

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
    backup.run_all()

    try:
        from pipeline import health
        health.check_channels_health()
        health.run_thumbnail_ab_tests()
        health.audit_channel_sameness()
    except Exception as exc:
        notify.log(f"Checagem de saúde dos canais falhou (não bloqueia a geração): {exc}")

    today_weekday = date.today().weekday()
    weekday_names = ["segunda-feira", "terça-feira", "quarta-feira", "quinta-feira",
                      "sexta-feira", "sábado", "domingo"]

    track_ids = []
    for channel in channels.list_channels(active_only=True):
        schedule = {row["weekday"]: row for row in catalog.get_channel_schedule(channel["id"])}
        today = schedule.get(today_weekday)

        if today and not today["enabled"]:
            notify.log(f"[{channel['name']}] Agenda: hoje ({weekday_names[today_weekday]}) está desativado nessa agenda - pulado.")
            continue

        forced_topic = None
        if today and today["topic_mode"] == "custom" and today["topic_label"] and today["topic_query"]:
            forced_topic = (today["topic_label"], today["topic_query"])
        forced_voice = today["voice"] if today and "voice" in today.keys() and today["voice"] else None

        try:
            track_id = prepare_daily_video(channel["id"], forced_topic=forced_topic, forced_voice=forced_voice)
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
    music_credit = track["music_attribution"] if "music_attribution" in track.keys() else None

    # Cross-link Short<->longo: se o Short deste mesmo track já foi
    # publicado antes, linka pra ele na descrição do vídeo longo que está
    # subindo agora.
    short_id = track["youtube_short_video_id"] if "youtube_short_video_id" in track.keys() else None
    related_url = f"https://youtube.com/shorts/{short_id}" if short_id else None
    chapters_text = track["chapters_text"] if "chapters_text" in track.keys() else None
    description = _build_description(
        track["topic"], track["script"], credits, music_credit,
        related_video_url=related_url, related_label="Versão curta (Short)" if related_url else None,
        chapters_text=chapters_text,
    )
    tags = _build_tags(channel, track)

    video_id = youtube_upload.upload_video(
        track["video_path"], track["title"], description, tags,
        client_secret_path=channels.client_secret_path(channel["slug"]),
        token_path=channels.token_path(channel["slug"]),
        thumbnail_path=track["thumbnail_path"], privacy_status=privacy_status,
        category_id=channel["video_category_id"] if "video_category_id" in channel.keys() else "28",
        made_for_kids=bool(channel["made_for_kids"]) if "made_for_kids" in channel.keys() else False,
    )
    catalog.update_track(
        track_id, youtube_video_id=video_id, status="uploaded",
        published_at=datetime.now(timezone.utc).isoformat(),
    )

    # Legenda real (.srt) - reaproveita o timing por palavra salvo no
    # checkpoint.json da geração (nunca é apagado) pra subir uma legenda
    # de verdade, não a auto-gerada do YouTube (ver pipeline/
    # captions_export.py). Indexação de busca melhor é o ganho; best-
    # effort, nunca bloqueia a publicação se o checkpoint já não existir
    # (instalação antiga) ou a API recusar.
    try:
        checkpoint = _load_checkpoint(Path(track["narration_path"]).parent)
        srt_content = captions_export.build_srt(checkpoint["boundaries"]) if checkpoint else None
        if srt_content:
            language_code = (channel["language"] or "pt-BR").split("-")[0]
            youtube_upload.upload_captions(
                video_id, srt_content,
                client_secret_path=channels.client_secret_path(channel["slug"]),
                token_path=channels.token_path(channel["slug"]),
                language=language_code,
            )
    except Exception as exc:
        notify.log(f"[{channel['name']}] Falha ao subir legenda .srt (não bloqueia a publicação): {exc}")

    # Playlist automática por série - cria sob demanda na primeira vez que a
    # série publica, reaproveitada nas próximas (ver pipeline/catalog.
    # get_series_playlist). Fila com autoplay em vez de vídeo isolado -
    # best-effort, nunca bloqueia a publicação se falhar.
    if track["series"]:
        try:
            playlist_id = catalog.get_series_playlist(channel["id"], track["series"])
            if not playlist_id:
                playlist_id = youtube_upload.get_or_create_playlist(
                    track["series"],
                    f"Vídeos da série \"{track['series']}\" do canal {channel['name']}.",
                    client_secret_path=channels.client_secret_path(channel["slug"]),
                    token_path=channels.token_path(channel["slug"]),
                )
                catalog.set_series_playlist(channel["id"], track["series"], playlist_id)
            youtube_upload.add_video_to_playlist(
                playlist_id, video_id,
                client_secret_path=channels.client_secret_path(channel["slug"]),
                token_path=channels.token_path(channel["slug"]),
            )
        except Exception as exc:
            notify.log(f"[{channel['name']}] Falha ao adicionar vídeo à playlist da série: {exc}")

    # Se o Short JÁ estava no ar, ele não tinha como linkar de volta pro
    # vídeo longo (que não existia ainda) - atualiza a descrição dele agora
    # que o longo também está publicado, deixando o link nos dois sentidos.
    if short_id:
        try:
            short_desc = _build_description(
                track["topic"], track["script"], credits, music_credit,
                related_video_url=f"https://youtube.com/watch?v={video_id}", related_label="Vídeo completo",
            )
            youtube_upload.update_video_description(
                short_id, short_desc,
                client_secret_path=channels.client_secret_path(channel["slug"]),
                token_path=channels.token_path(channel["slug"]),
            )
        except Exception as exc:
            notify.log(f"[{channel['name']}] Falha ao atualizar link cruzado no Short já publicado: {exc}")

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
    music_credit = track["music_attribution"] if "music_attribution" in track.keys() else None

    # Cross-link Short<->longo (ver approve_and_upload): se o vídeo longo
    # já foi publicado, linka pra ele na descrição do Short.
    video_id_existing = track["youtube_video_id"] if "youtube_video_id" in track.keys() else None
    related_url = f"https://youtube.com/watch?v={video_id_existing}" if video_id_existing else None
    description = _build_description(
        track["topic"], track["script"], credits, music_credit,
        related_video_url=related_url, related_label="Vídeo completo" if related_url else None,
    )
    tags = _build_tags(channel, track) + ["shorts"]
    short_title = track["title"] if "#shorts" in track["title"].lower() else f"{track['title']} #Shorts"

    video_id = youtube_upload.upload_video(
        track["video_vertical_path"], short_title, description, tags,
        client_secret_path=channels.client_secret_path(channel["slug"]),
        token_path=channels.token_path(channel["slug"]),
        thumbnail_path=None, privacy_status=privacy_status,
        category_id=channel["video_category_id"] if "video_category_id" in channel.keys() else "28",
        made_for_kids=bool(channel["made_for_kids"]) if "made_for_kids" in channel.keys() else False,
    )
    catalog.update_track(track_id, youtube_short_video_id=video_id)

    # Se o vídeo longo já estava no ar, atualiza a descrição dele agora pra
    # linkar de volta pro Short que acabou de subir.
    if video_id_existing:
        try:
            long_desc = _build_description(
                track["topic"], track["script"], credits, music_credit,
                related_video_url=f"https://youtube.com/shorts/{video_id}", related_label="Versão curta (Short)",
            )
            youtube_upload.update_video_description(
                video_id_existing, long_desc,
                client_secret_path=channels.client_secret_path(channel["slug"]),
                token_path=channels.token_path(channel["slug"]),
            )
        except Exception as exc:
            notify.log(f"[{channel['name']}] Falha ao atualizar link cruzado no vídeo longo já publicado: {exc}")

    return video_id


if __name__ == "__main__":
    run_all_active_channels()
