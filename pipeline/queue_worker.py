"""Worker da fila de geração sob demanda - processa os temas marcados no
estúdio (ver settings_ui.channel_studio) 1 de cada vez, em segundo plano.

Processa sequencialmente (não em paralelo) de propósito: Ollama, render de
vídeo e narração já competem por CPU/GPU numa geração só - rodar várias ao
mesmo tempo derrubaria a máquina em vez de acelerar de verdade.
"""

import threading
import time

from pipeline import catalog, channels, notify, orchestrator

_worker_started = False
_lock = threading.Lock()


def _process_one(item) -> None:
    channel = channels.get_channel(item["channel_id"])
    catalog.update_queue_item(item["id"], status="running", started_at=_now())
    try:
        track_id = orchestrator.prepare_daily_video(
            item["channel_id"], forced_topic=(item["topic_label"], item["topic_query"])
        )
        catalog.update_queue_item(item["id"], status="done", track_id=track_id, finished_at=_now())
        notify.log(f"[{channel['name']}] Fila: vídeo sobre \"{item['topic_label']}\" pronto (track {track_id}).")
    except Exception as exc:
        catalog.update_queue_item(item["id"], status="failed", error=str(exc), finished_at=_now())
        notify.log(f"[{channel['name']}] Fila: falhou ao gerar \"{item['topic_label']}\": {exc}")


def _now() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()


def _loop() -> None:
    while True:
        item = catalog.next_pending_queue_item()
        if item:
            _process_one(item)
        else:
            time.sleep(5)


def _recover_stale_running_items() -> None:
    """Se o processo anterior morreu (restart do servidor, queda, etc.) no
    meio de um item da fila, ele fica preso em status='running' pra sempre -
    o worker só busca 'pending', nunca reclama 'running' travado. Como isso
    roda ANTES da própria thread desse processo começar a processar, todo
    'running' encontrado aqui é necessariamente órfão de um processo
    anterior (não pode ser um item que ESTE processo está processando agora,
    porque a thread ainda nem começou). Aconteceu de verdade num restart
    seguido de outro - 2 itens ficaram presos até serem resetados na mão."""
    with catalog.get_conn() as conn:
        stale = conn.execute("SELECT id, topic_label FROM generation_queue WHERE status = 'running'").fetchall()
        for row in stale:
            conn.execute(
                "UPDATE generation_queue SET status = 'pending', started_at = NULL WHERE id = ?", (row["id"],)
            )
    for row in stale:
        notify.log(f"Fila: item \"{row['topic_label']}\" estava travado em 'running' de um processo "
                   "anterior - resetado pra 'pending', será reprocessado do zero.")


def ensure_worker_started() -> None:
    """Garante que a thread da fila está rodando - idempotente, chamar
    quantas vezes quiser (ex.: a cada request que mexe na fila) sem criar
    threads duplicadas."""
    global _worker_started
    with _lock:
        if _worker_started:
            return
        _recover_stale_running_items()
        threading.Thread(target=_loop, daemon=True).start()
        _worker_started = True
