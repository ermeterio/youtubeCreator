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

from pipeline import catalog, channels, notify, youtube_upload


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
            msg = f"[{channel['name']}] Canal inacessível pela API do YouTube: {exc}"
            warnings.append(msg)
            notify.log(msg)
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
