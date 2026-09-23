"""Painel de métricas do canal no YouTube - YouTube Analytics API v2, só
leitura (escopo yt-analytics.readonly). Dá o resumo agregado do canal e o
desempenho por vídeo (views, retenção, likes, comentários, inscritos
ganhos), pra decisão informada de qual tema/série/formato está funcionando
de verdade, em vez de só suposição.
"""

from datetime import date, timedelta
from pathlib import Path

from googleapiclient.discovery import build

from pipeline.youtube_upload import _get_credentials

METRICS = "views,estimatedMinutesWatched,averageViewDuration,averageViewPercentage,likes,comments,subscribersGained"

METRIC_LABELS = {
    "views": "Visualizações",
    "estimatedMinutesWatched": "Minutos assistidos",
    "averageViewDuration": "Duração média assistida (s)",
    "averageViewPercentage": "% média assistida",
    "likes": "Likes",
    "comments": "Comentários",
    "subscribersGained": "Inscritos ganhos",
}


def _build_service(client_secret_path: Path, token_path: Path):
    creds = _get_credentials(client_secret_path, token_path)
    return build("youtubeAnalytics", "v2", credentials=creds)


def channel_summary(client_secret_path: Path, token_path: Path, days: int = 28) -> dict:
    """Totais agregados do canal nos últimos `days` dias."""
    service = _build_service(client_secret_path, token_path)
    end = date.today()
    start = end - timedelta(days=days)
    response = service.reports().query(
        ids="channel==MINE",
        startDate=start.isoformat(),
        endDate=end.isoformat(),
        metrics=METRICS,
    ).execute()
    rows = response.get("rows")
    if not rows:
        return {}
    headers = [h["name"] for h in response["columnHeaders"]]
    return dict(zip(headers, rows[0]))


def video_metrics(client_secret_path: Path, token_path: Path, days: int = 28, max_results: int = 25) -> dict[str, dict]:
    """Métricas por vídeo nos últimos `days` dias, indexado por video_id -
    uma chamada só cobre todos os vídeos do canal no período (não precisa
    de 1 request por vídeo)."""
    service = _build_service(client_secret_path, token_path)
    end = date.today()
    start = end - timedelta(days=days)
    response = service.reports().query(
        ids="channel==MINE",
        startDate=start.isoformat(),
        endDate=end.isoformat(),
        metrics=METRICS,
        dimensions="video",
        sort="-views",
        maxResults=max_results,
    ).execute()
    headers = [h["name"] for h in response.get("columnHeaders", [])]
    rows = response.get("rows", [])
    result = {}
    for row in rows:
        data = dict(zip(headers, row))
        result[data["video"]] = data
    return result


def video_metrics_single(client_secret_path: Path, token_path: Path, video_id: str, days: int = 28) -> dict:
    service = _build_service(client_secret_path, token_path)
    end = date.today()
    start = end - timedelta(days=days)
    response = service.reports().query(
        ids="channel==MINE",
        startDate=start.isoformat(),
        endDate=end.isoformat(),
        metrics=METRICS,
        filters=f"video=={video_id}",
    ).execute()
    rows = response.get("rows")
    if not rows:
        return {}
    headers = [h["name"] for h in response["columnHeaders"]]
    return dict(zip(headers, rows[0]))
