"""Relatório agregado de desempenho por série/tema, cruzando todos os
canais - fecha o loop entre "o que o pipeline produz" e "o que realmente
performa", em vez de decidir formato/série só por palpite (ver roadmap de
conteúdo - Fase 3/5: loop de aprendizado).
"""

from pipeline import catalog, channels, youtube_analytics


def series_performance(days: int = 28, channel_id: int | None = None) -> list[dict]:
    """Agrega views/retenção/likes por (canal, série) nos últimos `days`
    dias, cruzando a YouTube Analytics API com o catálogo local (que sabe
    qual série cada vídeo pertence). Só considera canais já autorizados -
    pula silenciosamente os que ainda não têm token ou não têm permissão de
    analytics (não derruba o relatório inteiro por causa de 1 canal).
    `channel_id` restringe a 1 canal só - cada canal deve ver o próprio
    relatório, não um agregado misturando todos."""
    rows = []
    all_channels = [channels.get_channel(channel_id)] if channel_id else channels.list_channels()
    for channel in all_channels:
        secret_path = channels.client_secret_path(channel["slug"])
        token_path = channels.token_path(channel["slug"])
        if not token_path.exists():
            continue

        try:
            per_video = youtube_analytics.video_metrics(secret_path, token_path, days=days, max_results=50)
        except Exception:
            continue
        if not per_video:
            continue

        local_by_youtube_id = {
            t["youtube_video_id"]: t
            for t in catalog.list_tracks(channel_id=channel["id"], limit=500)
            if t["youtube_video_id"]
        }

        by_series: dict[str, dict] = {}
        for video_id, metrics in per_video.items():
            local = local_by_youtube_id.get(video_id)
            series = (local["series"] if local and local["series"] else "(sem série / publicado fora do pipeline)")
            bucket = by_series.setdefault(series, {
                "channel": channel["name"], "series": series, "videos": 0,
                "views": 0, "likes": 0, "watch_minutes": 0.0, "avg_pct_sum": 0.0,
            })
            bucket["videos"] += 1
            bucket["views"] += int(metrics.get("views") or 0)
            bucket["likes"] += int(metrics.get("likes") or 0)
            bucket["watch_minutes"] += float(metrics.get("estimatedMinutesWatched") or 0)
            bucket["avg_pct_sum"] += float(metrics.get("averageViewPercentage") or 0)

        for bucket in by_series.values():
            bucket["avg_view_pct"] = bucket["avg_pct_sum"] / bucket["videos"] if bucket["videos"] else 0
            del bucket["avg_pct_sum"]
            rows.append(bucket)

    rows.sort(key=lambda r: r["views"], reverse=True)
    return rows
