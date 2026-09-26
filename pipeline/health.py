"""Monitoramento de saúde do canal - o que é honestamente possível de checar
via API pública: a API do YouTube NÃO expõe strikes nem status de
monetização pra apps de terceiros (isso só existe dentro do YouTube Studio,
visível só pro dono logado ali). O que dá pra detectar de verdade:

- Queda na contagem de vídeos do canal (sinal de remoção/strike por parte do
  YouTube - um vídeo que sumiu não é algo que o pipeline decidiu, é externo).
- Canal ficou inacessível pela API (token revogado, conta suspensa, etc.).

Roda junto com a geração diária e avisa (mesmo mecanismo de notify.py) se
algo mudou de um jeito que merece atenção humana.
"""

from datetime import date, datetime, timedelta, timezone

import config
from pipeline import catalog, channels, notify, semantic, youtube_analytics, youtube_upload

# Fração de vídeos com alta similaridade estrutural entre si acima da qual
# alertamos - a política de "inauthentic content" do YouTube (2026) pune no
# nível do CANAL quando uma fração alta do watch time vem de conteúdo
# template-based, não só vídeo a vídeo (ver ROADMAP.md).
SAMENESS_ALERT_FRACTION = 0.5


def _stored_video_count_key(channel_id: int) -> str:
    return f"health_video_count_channel_{channel_id}"


def check_channels_health() -> list[str]:
    """Retorna a lista de avisos gerados (vazia se tudo normal)."""
    warnings = []
    for channel in channels.list_channels(active_only=True):
        secret_path = channels.client_secret_path(channel["slug"])
        token_path = channels.token_path(channel["slug"])
        if not token_path.exists():
            continue  # canal ainda não autorizado - nada pra checar

        key = _stored_video_count_key(channel["id"])
        previous_count = catalog.get_setting(key)

        try:
            info = youtube_upload.get_channel_info(secret_path, token_path)
        except Exception as exc:
            if "expirou" in str(exc) and "reautorize" in str(exc).lower():
                # Falha de token é o ponto de falha mais citado em automações
                # solo do YouTube (ver ROADMAP.md) - alerta destacado (toast,
                # não só log em arquivo que ninguém vai ler até dar problema
                # de verdade), porque toda geração futura desse canal vai
                # falhar até reautorizar.
                msg = f"[{channel['name']}] Token expirado - reautorize esse canal antes da próxima geração."
                notify.notify_result(False, msg)
            else:
                msg = f"[{channel['name']}] Canal inacessível pela API do YouTube: {exc}"
                notify.log(msg)
            warnings.append(msg)
            continue

        if not info:
            continue

        current_count = info.get("video_count")
        if current_count is None:
            continue

        if previous_count is not None and int(current_count) < int(previous_count):
            diff = int(previous_count) - int(current_count)
            msg = (
                f"[{channel['name']}] O número de vídeos no canal CAIU de {previous_count} para "
                f"{current_count} ({diff} a menos) desde a última checagem - pode ser remoção pelo "
                "YouTube (direitos autorais, política de conteúdo) ou exclusão manual. Confira o canal."
            )
            warnings.append(msg)
            notify.notify_result(False, msg)

        catalog.set_setting(key, str(current_count))

    return warnings


def _ctr_pct(metrics: dict) -> float | None:
    ctr = metrics.get("videoThumbnailImpressionsClickRate")
    impressions = metrics.get("videoThumbnailImpressions")
    if ctr is None or impressions is None or float(impressions) < config.THUMBNAIL_AB_MIN_IMPRESSIONS:
        return None
    return float(ctr) * 100


def run_thumbnail_ab_tests() -> list[str]:
    """Teste A/B de thumbnail automático, rodado junto com a checagem diária:

    1. Vídeo publicado há >= THUMBNAIL_AB_TEST_WAIT_DAYS, ainda na thumbnail
       original (variante A) e nunca testado -> troca pra variante B e marca
       a data da troca (CTR de A até aqui vira o "baseline" implícito pelo
       período antes da troca).
    2. Vídeo já rodou com a variante B por >= THUMBNAIL_AB_TEST_WAIT_DAYS ->
       compara CTR do período COM A (antes da troca) contra o período COM B
       (depois da troca); se B for pior, volta pra A. Se A tiver poucas
       impressões (< THUMBNAIL_AB_MIN_IMPRESSIONS) pra comparar direito,
       adia a decisão e tenta de novo no próximo dia (mais dados acumulam).
    Tudo logado via notify.log - nenhuma decisão fica silenciosa."""
    results = []
    now = datetime.now(timezone.utc)

    for channel in channels.list_channels(active_only=True):
        secret_path = channels.client_secret_path(channel["slug"])
        token_path = channels.token_path(channel["slug"])
        if not token_path.exists():
            continue

        for track in catalog.list_tracks(channel_id=channel["id"], limit=50):
            if track["status"] != "uploaded" or not track["youtube_video_id"] or not track["thumbnail_b_path"]:
                continue
            if not track["published_at"]:
                continue

            published_at = datetime.fromisoformat(track["published_at"])
            days_live = (now - published_at).days

            if track["active_thumbnail"] == "a" and not track["thumbnail_rotated_at"]:
                if days_live < config.THUMBNAIL_AB_TEST_WAIT_DAYS:
                    continue
                try:
                    youtube_upload.set_thumbnail(
                        track["youtube_video_id"], track["thumbnail_b_path"], secret_path, token_path
                    )
                    catalog.update_track(track["id"], active_thumbnail="b", thumbnail_rotated_at=now.isoformat())
                    msg = (f"[{channel['name']}] Teste A/B: trocou a thumbnail do vídeo "
                           f"\"{track['title']}\" pra variante B após {days_live} dia(s).")
                    notify.log(msg)
                    results.append(msg)
                except Exception as exc:
                    notify.log(f"[{channel['name']}] Teste A/B: falha ao trocar thumbnail - {exc}")
                continue

            if track["active_thumbnail"] == "b" and track["thumbnail_rotated_at"]:
                rotated_at = datetime.fromisoformat(track["thumbnail_rotated_at"])
                if (now - rotated_at).days < config.THUMBNAIL_AB_TEST_WAIT_DAYS:
                    continue
                try:
                    metrics_a = youtube_analytics.video_metrics_single_range(
                        secret_path, token_path, track["youtube_video_id"],
                        published_at.date(), rotated_at.date(),
                    )
                    metrics_b = youtube_analytics.video_metrics_single_range(
                        secret_path, token_path, track["youtube_video_id"],
                        rotated_at.date(), date.today(),
                    )
                    ctr_a, ctr_b = _ctr_pct(metrics_a), _ctr_pct(metrics_b)
                    if ctr_a is None or ctr_b is None:
                        notify.log(
                            f"[{channel['name']}] Teste A/B: dados insuficientes ainda pra comparar "
                            f"\"{track['title']}\" (impressões abaixo do mínimo de "
                            f"{config.THUMBNAIL_AB_MIN_IMPRESSIONS}) - tenta de novo amanhã."
                        )
                        continue

                    if ctr_b >= ctr_a:
                        msg = (f"[{channel['name']}] Teste A/B: variante B venceu em \"{track['title']}\" "
                               f"(CTR A={ctr_a:.2f}% vs B={ctr_b:.2f}%) - mantendo B.")
                        catalog.update_track(track["id"], active_thumbnail="b_confirmed")
                    else:
                        youtube_upload.set_thumbnail(
                            track["youtube_video_id"], track["thumbnail_path"], secret_path, token_path
                        )
                        catalog.update_track(track["id"], active_thumbnail="a_confirmed")
                        msg = (f"[{channel['name']}] Teste A/B: variante A venceu em \"{track['title']}\" "
                               f"(CTR A={ctr_a:.2f}% vs B={ctr_b:.2f}%) - voltou pra A.")
                    notify.log(msg)
                    results.append(msg)
                except Exception as exc:
                    notify.log(f"[{channel['name']}] Teste A/B: falha ao comparar/decidir - {exc}")

    return results


def audit_channel_sameness(limit_per_channel: int = 25) -> list[str]:
    """"Channel Sameness Audit" - a política de "inauthentic content" do
    YouTube (2026) pune no nível do CANAL quando uma fração alta do watch
    time vem de vídeos com pouca variação estrutural entre si (roteiro
    "template-based"), não só título/hook repetido individualmente (esse
    caso já é pego por script_gen.compute_quality_score por vídeo). Reusa o
    fastembed já validado em produção pra comparar o roteiro de cada vídeo
    recente contra todos os outros e alertar se uma fração grande demais se
    parece entre si - sinal cedo de risco de desmonetização, não uma
    decisão automática de nada."""
    warnings = []
    for channel in channels.list_channels(active_only=True):
        tracks = [t for t in catalog.list_tracks(channel_id=channel["id"], limit=limit_per_channel) if t["script"]]
        texts = [f"{t['title']} {t['script'][:400]}" for t in tracks]
        result = semantic.pairwise_high_similarity_fraction(texts)
        if not result:
            continue  # amostra pequena demais ainda - nada a avaliar

        if result["fraction"] >= SAMENESS_ALERT_FRACTION:
            pct = round(result["fraction"] * 100)
            msg = (
                f"[{channel['name']}] Auditoria de similaridade: {pct}% dos últimos "
                f"{result['sample_size']} vídeos são muito parecidos entre si (roteiro/gancho) - "
                f"risco real de ser lido como conteúdo 'template-based' pela política do YouTube. "
                f"Varie mais o ângulo/estrutura dos próximos roteiros."
            )
            notify.notify_result(False, msg)
            warnings.append(msg)
        else:
            notify.log(
                f"[{channel['name']}] Auditoria de similaridade: {round(result['fraction'] * 100)}% "
                f"de {result['sample_size']} vídeos parecidos entre si - dentro do esperado."
            )

    return warnings
